# ── What this file IS ─────────────────────────────────────────────────────────
# The synchronous client: the ONLY file a sync user imports from.
# It exists to (a) collect the user's settings, (b) validate the key at startup,
# and (c) expose one friendly method per captcha type. It contains NO solve logic
# — every method builds a params dict, looks up the registry row, and runs the
# shared orchestrator engine. The only sync-specific code here is the tiny driver
# loop `_drive_engine`, which is exactly "the transport difference" and nothing more.

from __future__ import annotations

import dataclasses
import threading
import time

from .core import orchestrator
from .core.config import Config
from .core.orchestrator import ApiCall, Sleep
from .core.registry import get_entry
from .core.result import SolveResult
from .exceptions import APIError, InvalidKeyError, ThreadLimitError, ValidationError
from .helpers.validation import validate_proxy_options
from .transport.sync_http import SyncTransport


class CaptchaAI:
    """Synchronous CaptchaAI client.

    Create once with your API key (and optional proxy / retry preference). The
    constructor validates the key and learns the account's thread cap in a single
    startup call. Then call one method per captcha type, e.g. recaptcha_v2(...).
    """

    def __init__(
        self,
        api_key: str,
        proxy: str | None = None,
        proxytype: str | None = None,
        auto_retry: bool = True,
        base_url: str = "https://ocr.captchaai.com",
        thread_busy_timeout: float = 120.0,
        max_retries: int | None = None,
    ) -> None:
        """Create the client, validate the key, and store the thread cap.

        Parameters:
            api_key: 32-character CaptchaAI key.
            proxy: optional "user:pass@host:port" applied to every solve.
            proxytype: required when proxy is set (HTTP or HTTPS).
            auto_retry: True (default) = SDK retries transient errors with
                exponential backoff; False = raise immediately so you control
                the retry loop. Ignored when max_retries is set.
            base_url: API host serving in.php and res.php.
            thread_busy_timeout: seconds to keep retrying when all threads are
                busy. Default 120s covers reCAPTCHA v2 (60-80s) solve time.
            max_retries: when provided, sets the maximum number of submit retry
                attempts and also controls auto_retry (0 disables retries,
                N > 0 enables them with N attempts). Supersedes the auto_retry
                boolean when set.

        Raises:
            ValidationError: if a proxy is given without a proxytype.
            InvalidKeyError: if the startup threadsinfo call rejects the key.
        """
        # Catch None, empty string, and wrong-length keys before any HTTP call.
        if not api_key or not isinstance(api_key, str) or len(api_key.strip()) != 32:
            raise InvalidKeyError("Key must be 32 characters")

        # A proxy with no type or unsupported protocol cannot be forwarded — fail fast.
        proxytype = validate_proxy_options(proxy, proxytype)

        # max_retries, when given, overrides both auto_retry and the retry count.
        # max_retries=0  → auto_retry=False (raise immediately)
        # max_retries=N  → auto_retry=True with N attempts
        if max_retries is not None:
            effective_auto_retry = max_retries > 0
            effective_max_retries = max_retries
        else:
            effective_auto_retry = auto_retry
            effective_max_retries = 5  # Config default

        # All settings live in one Config object passed down to the engine.
        self._config = Config(
            api_key=api_key,
            proxy=proxy,
            proxytype=proxytype,
            auto_retry=effective_auto_retry,
            base_url=base_url,
            thread_busy_timeout=thread_busy_timeout,
            max_retries=effective_max_retries,
        )
        # One reused transport for this client's lifetime.
        self._transport = SyncTransport(timeout=self._config.network_timeout)

        # Startup: one threadsinfo call validates the key AND returns the cap.
        info = self._drive_engine(orchestrator.get_thread_usage(self._config))
        self._thread_cap: int = info["threads"]
        # Track concurrent in-flight solves for auto_retry=False fast-fail.
        # The API queues excess tasks silently, so local counting is the only
        # reliable way to detect cap overflow before tasks enter the server queue.
        self._inflight = 0
        self._inflight_lock = threading.Lock()

    # ── The sync driver: the ONLY sync-specific glue in the whole SDK ──────────
    def _drive_engine(self, engine):
        """Run an orchestrator step-by-step, doing each thing it asks for (sync).

        The engine pauses and hands us small requests: ApiCall means "send this
        HTTP request", Sleep means "wait this long". We perform each one and feed
        the outcome back. The engine makes all the decisions; this loop just acts.
        """
        try:
            effect = next(engine)  # prime the generator to its first effect
            while True:
                if isinstance(effect, ApiCall):
                    # Perform the request and hand the response back to the engine.
                    response = self._transport.request_raw(
                        effect.method, effect.url, effect.data
                    )
                    effect = engine.send(response)
                elif isinstance(effect, Sleep):
                    # Block for the requested time, then resume the engine.
                    time.sleep(effect.seconds)
                    effect = engine.send(None)
                else:
                    raise APIError(f"Unknown engine effect: {effect!r}")
        except StopIteration as stop:
            # The generator's return value is the final result.
            return stop.value

    # ── Internal: run any type by name + params dict ───────────────────────────
    def _solve_type(
        self,
        type_name: str,
        params: dict,
        *,
        proxy: str | None = None,
        proxytype: str | None = None,
    ) -> SolveResult:
        """Look up the registry row for a type and solve it.

        When proxy/proxytype are given they override the client-level proxy for
        this call only, without mutating the shared config.
        """
        entry = get_entry(type_name)

        # Build a per-call config when a proxy override was provided.
        if proxy is not None:
            normalized_proxytype = validate_proxy_options(proxy, proxytype)
            cfg = dataclasses.replace(
                self._config, proxy=proxy, proxytype=normalized_proxytype
            )
        else:
            cfg = self._config

        # Client-level cap check: the API queues excess tasks silently, so local
        # counting is the only reliable way to fail fast when auto_retry=False.
        # Tests that bypass __init__ (make_sync) won't have _inflight_lock, so
        # getattr falls back to None and the check is skipped for them — the
        # orchestrator-level proactive check still covers those test cases.
        lock = getattr(self, "_inflight_lock", None)
        if not cfg.auto_retry and lock is not None:
            with lock:
                if self._inflight >= self._thread_cap:
                    raise ThreadLimitError(
                        f"Thread cap reached ({self._thread_cap} concurrent solves active)"
                    )
                self._inflight += 1
            try:
                return self._drive_engine(
                    orchestrator.solve_captcha(cfg, entry, params)
                )
            finally:
                with lock:
                    self._inflight -= 1
        return self._drive_engine(orchestrator.solve_captcha(cfg, entry, params))

    # ── Image captcha types ────────────────────────────────────────────────────
    def normal(
        self,
        image: str | bytes,
        *,
        numeric: int | None = None,
        min_len: int | None = None,
        max_len: int | None = None,
        phrase: int | None = None,
        case_sensitive: int | None = None,
        lang: str | None = None,
        instructions: str | None = None,
        proxy: str | None = None,
        proxytype: str | None = None,
    ) -> SolveResult:
        """Solve a normal image captcha.

        Parameters:
            image: file path, URL, data-URI, raw base64, or bytes of the image.
            numeric: digit hint — 0=any, 1=digits only, 2=letters only,
                3=digits+letters, 4=no digits.
            min_len: minimum expected answer length.
            max_len: maximum expected answer length.
            phrase: 0=single word (default), 1=multi-word answer expected.
            case_sensitive: 0=case-insensitive (default), 1=case-sensitive.
            lang: ISO language code hint, e.g. "en", "ru".
            instructions: custom text shown to the solver.
            proxy: per-call proxy override "user:pass@host:port".
            proxytype: required when proxy is set (HTTP or HTTPS).

        Returns:
            SolveResult whose `solution` is the recognised text.
        """
        params: dict = {"image": image}
        if numeric is not None:
            params["numeric"] = numeric
        if min_len is not None:
            params["min_len"] = min_len
        if max_len is not None:
            params["max_len"] = max_len
        if phrase is not None:
            params["phrase"] = phrase
        if case_sensitive is not None:
            params["caseSensitive"] = case_sensitive
        if lang is not None:
            params["lang"] = lang
        if instructions is not None:
            params["textinstructions"] = instructions
        return self._solve_type("normal", params, proxy=proxy, proxytype=proxytype)

    def grid(
        self,
        image: str | bytes,
        instructions: str,
        grid_size: str,
        *,
        proxy: str | None = None,
        proxytype: str | None = None,
    ) -> SolveResult:
        """Solve a grid / tile-selection captcha.

        Parameters:
            image: the grid image (path/URL/base64/bytes).
            instructions: what to click, e.g. "crosswalks", "traffic lights".
            grid_size: grid dimensions — "3x3" or "4x4" (required by the API).
            proxy: per-call proxy override "user:pass@host:port".
            proxytype: required when proxy is set (HTTP or HTTPS).

        Returns:
            SolveResult whose `solution` is a list of cell indices to click.
        """
        return self._solve_type(
            "grid",
            {
                "image": image,
                "instructions": instructions,
                "grid_size": grid_size,
                "img_type": "recaptcha",
            },
            proxy=proxy,
            proxytype=proxytype,
        )

    def bls(
        self,
        images: list,
        instructions: str,
        *,
        proxy: str | None = None,
        proxytype: str | None = None,
    ) -> SolveResult:
        """Solve a BLS captcha made of multiple images.

        Parameters:
            images: a non-empty list of images (each path/URL/base64/bytes).
            instructions: what the solver should do with the images.
            proxy: per-call proxy override "user:pass@host:port".
            proxytype: required when proxy is set (HTTP or HTTPS).

        Returns:
            SolveResult with the BLS answer.
        """
        return self._solve_type(
            "bls",
            {"images": images, "instructions": instructions},
            proxy=proxy,
            proxytype=proxytype,
        )

    # ── reCAPTCHA types ─────────────────────────────────────────────────────────
    def recaptcha_v2(
        self,
        sitekey: str,
        url: str,
        invisible: bool = False,
        enterprise: bool = False,
        action: str | None = None,
        *,
        cookies: str | None = None,
        user_agent: str | None = None,
        proxy: str | None = None,
        proxytype: str | None = None,
    ) -> SolveResult:
        """Solve a reCAPTCHA v2 challenge (normal, invisible, or enterprise).

        Parameters:
            sitekey: the site's reCAPTCHA key (the API calls this googlekey).
            url: the page URL where the captcha appears.
            invisible: True for invisible reCAPTCHA v2.
            enterprise: True for reCAPTCHA v2 Enterprise (result includes user_agent).
            action: optional enterprise action string (the `sa=` value from the
                anchor URL). Applies to the enterprise variant; ignored for
                standard/invisible v2 by the solver.
            cookies: optional cookie string forwarded to the solver browser.
            user_agent: optional User-Agent header for the solver browser.
            proxy: per-call proxy override "user:pass@host:port".
            proxytype: required when proxy is set (HTTP or HTTPS).

        Returns:
            SolveResult whose `solution` is the g-recaptcha-response token.
        """
        # Flags pick the registry row; enterprise wins if both are set.
        if enterprise:
            type_name = "recaptcha_v2_enterprise"
        elif invisible:
            type_name = "recaptcha_v2_invisible"
        else:
            type_name = "recaptcha_v2"
        params: dict = {"googlekey": sitekey, "pageurl": url}
        # Pass the matching API flags so the service solves the right variant.
        if invisible:
            params["invisible"] = 1
        if enterprise:
            params["enterprise"] = 1
        if action is not None:
            params["action"] = action
        if cookies is not None:
            params["cookies"] = cookies
        if user_agent is not None:
            params["user_agent"] = user_agent
        return self._solve_type(type_name, params, proxy=proxy, proxytype=proxytype)

    def recaptcha_v3(
        self,
        sitekey: str,
        url: str,
        action: str | None = None,
        enterprise: bool = False,
        min_score: float | None = None,
        *,
        cookies: str | None = None,
        user_agent: str | None = None,
        proxy: str | None = None,
        proxytype: str | None = None,
    ) -> SolveResult:
        """Solve a reCAPTCHA v3 challenge (standard or enterprise).

        Parameters:
            sitekey: the site's reCAPTCHA key (the API calls this googlekey).
            url: the page URL where the captcha appears.
            action: the v3 action name (required for standard v3; required for
                enterprise v3 as scoring is tied to the action name).
            enterprise: True for reCAPTCHA v3 Enterprise (result includes user_agent).
            min_score: optional minimum score target (0.1–0.9).
            cookies: optional cookie string forwarded to the solver browser.
            user_agent: optional User-Agent header for the solver browser.
            proxy: per-call proxy override "user:pass@host:port".
            proxytype: required when proxy is set (HTTP or HTTPS).

        Returns:
            SolveResult whose `solution` is the v3 token.
        """
        type_name = "recaptcha_v3_enterprise" if enterprise else "recaptcha_v3"
        # version=v3 tells the API which reCAPTCHA flavour to run.
        params: dict = {"googlekey": sitekey, "pageurl": url, "version": "v3"}
        if action is not None:
            params["action"] = action
        if enterprise:
            params["enterprise"] = 1
        if min_score is not None:
            params["min_score"] = min_score
        if cookies is not None:
            params["cookies"] = cookies
        if user_agent is not None:
            params["user_agent"] = user_agent
        return self._solve_type(type_name, params, proxy=proxy, proxytype=proxytype)

    # ── Cloudflare types ────────────────────────────────────────────────────────
    def turnstile(
        self,
        sitekey: str,
        url: str,
        *,
        cookies: str | None = None,
        user_agent: str | None = None,
        proxy: str | None = None,
        proxytype: str | None = None,
    ) -> SolveResult:
        """Solve a Cloudflare Turnstile challenge.

        Parameters:
            sitekey: the Turnstile site key.
            url: the page URL where the widget appears.
            cookies: optional cookie string forwarded to the solver browser.
            user_agent: optional User-Agent header for the solver browser.
            proxy: per-call proxy override "user:pass@host:port".
            proxytype: required when proxy is set (HTTP or HTTPS).

        Returns:
            SolveResult whose `solution` is the Turnstile token (plus user_agent).
        """
        params: dict = {"sitekey": sitekey, "pageurl": url}
        if cookies is not None:
            params["cookies"] = cookies
        if user_agent is not None:
            params["user_agent"] = user_agent
        return self._solve_type("turnstile", params, proxy=proxy, proxytype=proxytype)

    def cloudflare_challenge(
        self,
        url: str,
        *,
        cookies: str | None = None,
        user_agent: str | None = None,
        proxy: str | None = None,
        proxytype: str | None = None,
    ) -> SolveResult:
        """Solve a Cloudflare interstitial challenge page.

        A proxy is mandatory for this type (either the client-level proxy or the
        per-call proxy argument). The solver browses the page through the proxy to
        obtain the cf_clearance cookie.

        Parameters:
            url: the page URL showing the Cloudflare challenge.
            cookies: optional cookie string forwarded to the solver browser.
            user_agent: optional User-Agent header for the solver browser.
            proxy: per-call proxy override "user:pass@host:port". One of this or
                the client-level proxy must be set.
            proxytype: required when proxy is set (HTTP or HTTPS).

        Returns:
            SolveResult with the challenge token (plus user_agent).
        """
        params: dict = {"pageurl": url}
        if cookies is not None:
            params["cookies"] = cookies
        if user_agent is not None:
            params["user_agent"] = user_agent
        return self._solve_type(
            "cloudflare_challenge", params, proxy=proxy, proxytype=proxytype
        )

    # ── GeeTest ─────────────────────────────────────────────────────────────────
    def geetest(
        self,
        gt: str,
        challenge: str,
        url: str,
        *,
        cookies: str | None = None,
        user_agent: str | None = None,
        proxy: str | None = None,
        proxytype: str | None = None,
    ) -> SolveResult:
        """Solve a GeeTest v3 challenge.

        Parameters:
            gt: the static `gt` value from the target site.
            challenge: the dynamic `challenge` value from the target site.
            url: the page URL where GeeTest appears.
            cookies: optional cookie string forwarded to the solver browser.
            user_agent: optional User-Agent header for the solver browser.
            proxy: per-call proxy override "user:pass@host:port".
            proxytype: required when proxy is set (HTTP or HTTPS).

        Returns:
            SolveResult whose `solution` is a dict {challenge, validate, seccode}.
        """
        params: dict = {"gt": gt, "challenge": challenge, "pageurl": url}
        if cookies is not None:
            params["cookies"] = cookies
        if user_agent is not None:
            params["user_agent"] = user_agent
        return self._solve_type("geetest", params, proxy=proxy, proxytype=proxytype)

    # ── New token-based solvers ─────────────────────────────────────────────────
    def captchafox(
        self,
        sitekey: str,
        url: str,
        *,
        cookies: str | None = None,
        user_agent: str | None = None,
        proxy: str | None = None,
        proxytype: str | None = None,
    ) -> SolveResult:
        """Solve a CaptchaFox slider challenge.

        CaptchaFox is a browser-interactive, token-based verification challenge.
        A proxy is mandatory — the solver loads the target page through the proxy
        to perform the interactive solve. The result includes a token and a
        user_agent that MUST be reused when submitting the token to the target site.

        Parameters:
            sitekey: the CaptchaFox sitekey (data-sitekey attribute or network req).
            url: the full page URL where the challenge appears.
            cookies: optional cookie string forwarded to the solver browser.
            user_agent: optional User-Agent header for the solver browser.
            proxy: per-call proxy override "user:pass@host:port". One of this or
                the client-level proxy must be set (proxy is mandatory for this type).
            proxytype: required when proxy is set (HTTP or HTTPS).

        Returns:
            SolveResult whose `solution` is the token string and `user_agent` is
            the solver's browser UA (must be reused on the target site).
        """
        params: dict = {"sitekey": sitekey, "pageurl": url}
        if cookies is not None:
            params["cookies"] = cookies
        if user_agent is not None:
            params["user_agent"] = user_agent
        return self._solve_type("captchafox", params, proxy=proxy, proxytype=proxytype)

    def friendly_captcha(
        self,
        sitekey: str,
        url: str,
        *,
        version: str | None = None,
        proxy: str | None = None,
        proxytype: str | None = None,
    ) -> SolveResult:
        """Solve a Friendly Captcha PoW challenge.

        Friendly Captcha uses a Proof-of-Work scheme — no user interaction is
        required and no proxy is needed. The solver runs the computation
        server-side and returns a verification token.

        Parameters:
            sitekey: the value of the data-sitekey attribute on the captcha widget.
            url: the full page URL where the challenge appears.
            version: Friendly Captcha version — "v1" (default) or "v2".
            proxy: per-call proxy override "user:pass@host:port" (optional).
            proxytype: required when proxy is set (HTTP or HTTPS).

        Returns:
            SolveResult whose `solution` is the verification token string.
        """
        params: dict = {"sitekey": sitekey, "pageurl": url}
        if version is not None:
            params["version"] = version
        return self._solve_type("friendly_captcha", params, proxy=proxy, proxytype=proxytype)

    def lemin(
        self,
        captcha_id: str,
        div_id: str,
        url: str,
        *,
        api_server: str | None = None,
        proxy: str | None = None,
        proxytype: str | None = None,
    ) -> SolveResult:
        """Solve a Lemin puzzle challenge.

        Lemin is a drag-or-rotate puzzle-based CAPTCHA. It requires a captchaId
        (unique per site) and the DOM id of the parent div element that hosts
        the widget. The answer is a structured dict with `answer` and
        `challenge_uuid` fields.

        Parameters:
            captcha_id: the Lemin captchaId value (e.g. "CROPPED_d3d4d56_...").
            div_id: the id of the captcha parent div element
                (e.g. "lemin-cropped-captcha").
            url: the full page URL where the challenge appears.
            api_server: optional Lemin API subdomain override
                (default: "api.leminnow.com").
            proxy: per-call proxy override "user:pass@host:port" (optional).
            proxytype: required when proxy is set (HTTP or HTTPS).

        Returns:
            SolveResult whose `solution` is a dict {"answer": "...",
            "challenge_uuid": "..."}.
        """
        params: dict = {"captcha_id": captcha_id, "div_id": div_id, "pageurl": url}
        if api_server is not None:
            params["api_server"] = api_server
        return self._solve_type("lemin", params, proxy=proxy, proxytype=proxytype)

    # ── Account utilities ───────────────────────────────────────────────────────
    def threads_info(self) -> dict:
        """Return current thread usage: {"threads": int, "working_threads": int}.

        Live thread-usage check (see get_balance() for the account balance).
        """
        return self._drive_engine(orchestrator.get_thread_usage(self._config))

    def get_balance(self) -> str:
        """Return the raw account balance string (res.php action=getbalance)."""
        return self._drive_engine(orchestrator.get_balance(self._config))

    # ── Manual two-step API (submit now, fetch later) ──────────────────────────
    def send(self, captcha_type: str, **params) -> str:
        """Submit a task and return its task_id WITHOUT waiting for the answer.

        Lower-level access for callers who want to manage polling themselves.

        Parameters:
            captcha_type: a registry type name, e.g. "recaptcha_v2".
            **params: API-named params for that type (e.g. googlekey=, pageurl=).

        Returns:
            The task_id string. Fetch the result later with get_result().
        """
        entry = get_entry(captcha_type)
        return self._drive_engine(orchestrator.submit_task(self._config, entry, params))

    def get_result(self, captcha_type: str, task_id: str) -> SolveResult:
        """Poll for and return the result of a previously sent task.

        Parameters:
            captcha_type: the same registry type name used in send().
            task_id: the task_id returned by send().

        Returns:
            The SolveResult once the answer is ready.
        """
        entry = get_entry(captcha_type)
        return self._drive_engine(orchestrator.fetch_result(self._config, entry, task_id))

    def close(self) -> None:
        """Close the underlying transport and release its connections."""
        self._transport.close()
