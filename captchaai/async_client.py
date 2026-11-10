# ── What this file IS ─────────────────────────────────────────────────────────
# The asynchronous client: the ONLY file an async user imports from.
# It mirrors CaptchaAI's public surface but with `async def` methods. It is NOT a
# copy of the solve logic — every method drives the SAME shared orchestrator
# engine as the sync client. The only differences here are an async transport and
# an `await`-based driver loop.
#
# Construction: because the API key must be validated AT creation (and a normal
# __init__ cannot await), this client is built via an async factory:
#     solver = await AsyncCaptchaAI.create(api_key=...)
# Direct instantiation (AsyncCaptchaAI(...)) is blocked by __new__.

from __future__ import annotations

import asyncio
import dataclasses

from .core import orchestrator
from .core.config import Config
from .core.orchestrator import ApiCall, Sleep
from .core.registry import get_entry
from .core.result import SolveResult
from .exceptions import APIError, ThreadLimitError, ValidationError
from .helpers.validation import validate_proxy_options
from .transport.async_http import AsyncTransport


class AsyncCaptchaAI:
    """Asynchronous CaptchaAI client.

    Same methods as the sync CaptchaAI, but awaitable. The API key is validated at
    construction time via the `create()` async factory — once `create()` returns,
    the client is fully ready and the thread cap is known. Direct instantiation is
    not allowed; use `solver = await AsyncCaptchaAI.create(api_key=...)`.
    """

    def __new__(cls, *args, **kwargs):
        """Block direct instantiation — construction must go through `create()`.

        A normal constructor cannot `await`, so the key-validation call cannot run
        here. Raising guides users to the async factory instead.
        """
        raise TypeError(
            "AsyncCaptchaAI cannot be instantiated directly. "
            "Use: solver = await AsyncCaptchaAI.create(api_key=...)"
        )

    @classmethod
    async def create(
        cls,
        api_key: str,
        proxy: str | None = None,
        proxytype: str | None = None,
        auto_retry: bool = True,
        base_url: str = "https://ocr.captchaai.com",
        thread_busy_timeout: float = 120.0,
        max_retries: int | None = None,
    ) -> "AsyncCaptchaAI":
        """Async constructor — build a fully validated, ready-to-use client.

        This is the one place an awaited call happens at construction. It performs a
        single `threadsinfo` call which both validates the API key and learns the
        account's thread cap, before the client is handed back to the caller.

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

        Returns:
            A ready AsyncCaptchaAI instance with its thread cap stored.

        Raises:
            ValidationError: if a proxy is given without a proxytype.
            InvalidKeyError: immediately if the key is wrong or does not exist.
        """
        # A proxy with no type or unsupported protocol cannot be forwarded — fail fast.
        proxytype = validate_proxy_options(proxy, proxytype)

        # max_retries, when given, overrides both auto_retry and the retry count.
        if max_retries is not None:
            effective_auto_retry = max_retries > 0
            effective_max_retries = max_retries
        else:
            effective_auto_retry = auto_retry
            effective_max_retries = 5  # Config default

        # Bypass the __new__ guard to actually build the instance.
        self = object.__new__(cls)

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
        # One reused async transport for this client's lifetime.
        self._transport = AsyncTransport(timeout=self._config.network_timeout)

        # The ONE awaited call at construction: validate the key AND learn the cap.
        info = await self._drive_engine(orchestrator.get_thread_usage(self._config))
        self._thread_cap: int = info["threads"]
        # Track concurrent in-flight solves for auto_retry=False fast-fail.
        self._inflight = 0
        self._inflight_lock = asyncio.Lock()

        return self

    # ── The async driver: the ONLY async-specific glue in the whole SDK ────────
    async def _drive_engine(self, engine):
        """Run an orchestrator step-by-step, doing each thing it asks for (async).

        Exactly the same decisions as the sync driver, but ApiCall awaits the async
        transport and Sleep awaits asyncio.sleep. The engine makes all the
        decisions; this loop just performs each request/wait and feeds results back.
        """
        try:
            effect = next(engine)  # prime the generator to its first effect
            while True:
                if isinstance(effect, ApiCall):
                    response = await self._transport.request_raw(
                        effect.method, effect.url, effect.data
                    )
                    effect = engine.send(response)
                elif isinstance(effect, Sleep):
                    await asyncio.sleep(effect.seconds)
                    effect = engine.send(None)
                else:
                    raise APIError(f"Unknown engine effect: {effect!r}")
        except StopIteration as stop:
            return stop.value

    # ── Internal: run any type by name + params dict ───────────────────────────
    async def _solve_type(
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
        lock = getattr(self, "_inflight_lock", None)
        if not cfg.auto_retry and lock is not None:
            async with lock:
                if self._inflight >= self._thread_cap:
                    raise ThreadLimitError(
                        f"Thread cap reached ({self._thread_cap} concurrent solves active)"
                    )
                self._inflight += 1
            try:
                return await self._drive_engine(
                    orchestrator.solve_captcha(cfg, entry, params)
                )
            finally:
                async with lock:
                    self._inflight -= 1
        return await self._drive_engine(orchestrator.solve_captcha(cfg, entry, params))

    # ── Image captcha types ────────────────────────────────────────────────────
    async def normal(
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
        """Solve a normal image captcha. See CaptchaAI.normal for full docs."""
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
        return await self._solve_type("normal", params, proxy=proxy, proxytype=proxytype)

    async def grid(
        self,
        image: str | bytes,
        instructions: str,
        grid_size: str,
        *,
        proxy: str | None = None,
        proxytype: str | None = None,
    ) -> SolveResult:
        """Solve a grid / tile-selection captcha. See CaptchaAI.grid for full docs."""
        return await self._solve_type(
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

    async def bls(
        self,
        images: list,
        instructions: str,
        *,
        proxy: str | None = None,
        proxytype: str | None = None,
    ) -> SolveResult:
        """Solve a BLS multi-image captcha. See CaptchaAI.bls for full docs."""
        return await self._solve_type(
            "bls",
            {"images": images, "instructions": instructions},
            proxy=proxy,
            proxytype=proxytype,
        )

    # ── reCAPTCHA types ─────────────────────────────────────────────────────────
    async def recaptcha_v2(
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
        """Solve reCAPTCHA v2 (normal/invisible/enterprise). See CaptchaAI.recaptcha_v2."""
        if enterprise:
            type_name = "recaptcha_v2_enterprise"
        elif invisible:
            type_name = "recaptcha_v2_invisible"
        else:
            type_name = "recaptcha_v2"
        params: dict = {"googlekey": sitekey, "pageurl": url}
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
        return await self._solve_type(type_name, params, proxy=proxy, proxytype=proxytype)

    async def recaptcha_v3(
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
        """Solve reCAPTCHA v3 (standard/enterprise). See CaptchaAI.recaptcha_v3."""
        type_name = "recaptcha_v3_enterprise" if enterprise else "recaptcha_v3"
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
        return await self._solve_type(type_name, params, proxy=proxy, proxytype=proxytype)

    # ── Cloudflare types ────────────────────────────────────────────────────────
    async def turnstile(
        self,
        sitekey: str,
        url: str,
        *,
        cookies: str | None = None,
        user_agent: str | None = None,
        proxy: str | None = None,
        proxytype: str | None = None,
    ) -> SolveResult:
        """Solve a Cloudflare Turnstile challenge. See CaptchaAI.turnstile."""
        params: dict = {"sitekey": sitekey, "pageurl": url}
        if cookies is not None:
            params["cookies"] = cookies
        if user_agent is not None:
            params["user_agent"] = user_agent
        return await self._solve_type("turnstile", params, proxy=proxy, proxytype=proxytype)

    async def cloudflare_challenge(
        self,
        url: str,
        *,
        cookies: str | None = None,
        user_agent: str | None = None,
        proxy: str | None = None,
        proxytype: str | None = None,
    ) -> SolveResult:
        """Solve a Cloudflare challenge page. See CaptchaAI.cloudflare_challenge."""
        params: dict = {"pageurl": url}
        if cookies is not None:
            params["cookies"] = cookies
        if user_agent is not None:
            params["user_agent"] = user_agent
        return await self._solve_type(
            "cloudflare_challenge", params, proxy=proxy, proxytype=proxytype
        )

    # ── GeeTest ─────────────────────────────────────────────────────────────────
    async def geetest(
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
        """Solve a GeeTest v3 challenge. See CaptchaAI.geetest."""
        params: dict = {"gt": gt, "challenge": challenge, "pageurl": url}
        if cookies is not None:
            params["cookies"] = cookies
        if user_agent is not None:
            params["user_agent"] = user_agent
        return await self._solve_type("geetest", params, proxy=proxy, proxytype=proxytype)

    # ── New token-based solvers ─────────────────────────────────────────────────
    async def captchafox(
        self,
        sitekey: str,
        url: str,
        *,
        cookies: str | None = None,
        user_agent: str | None = None,
        proxy: str | None = None,
        proxytype: str | None = None,
    ) -> SolveResult:
        """Solve a CaptchaFox slider challenge. See CaptchaAI.captchafox for full docs."""
        params: dict = {"sitekey": sitekey, "pageurl": url}
        if cookies is not None:
            params["cookies"] = cookies
        if user_agent is not None:
            params["user_agent"] = user_agent
        return await self._solve_type("captchafox", params, proxy=proxy, proxytype=proxytype)

    async def friendly_captcha(
        self,
        sitekey: str,
        url: str,
        *,
        version: str | None = None,
        proxy: str | None = None,
        proxytype: str | None = None,
    ) -> SolveResult:
        """Solve a Friendly Captcha PoW challenge. See CaptchaAI.friendly_captcha for full docs."""
        params: dict = {"sitekey": sitekey, "pageurl": url}
        if version is not None:
            params["version"] = version
        return await self._solve_type("friendly_captcha", params, proxy=proxy, proxytype=proxytype)

    async def lemin(
        self,
        captcha_id: str,
        div_id: str,
        url: str,
        *,
        api_server: str | None = None,
        proxy: str | None = None,
        proxytype: str | None = None,
    ) -> SolveResult:
        """Solve a Lemin puzzle challenge. See CaptchaAI.lemin for full docs."""
        params: dict = {"captcha_id": captcha_id, "div_id": div_id, "pageurl": url}
        if api_server is not None:
            params["api_server"] = api_server
        return await self._solve_type("lemin", params, proxy=proxy, proxytype=proxytype)

    # ── Account utilities ───────────────────────────────────────────────────────
    async def threads_info(self) -> dict:
        """Return {"threads": int, "working_threads": int}. See CaptchaAI.threads_info."""
        return await self._drive_engine(orchestrator.get_thread_usage(self._config))

    async def get_balance(self) -> str:
        """Return the raw account balance string (res.php action=getbalance)."""
        return await self._drive_engine(orchestrator.get_balance(self._config))

    # ── Manual two-step API (submit now, fetch later) ──────────────────────────
    async def send(self, captcha_type: str, **params) -> str:
        """Submit a task and return its task_id without waiting. See CaptchaAI.send."""
        entry = get_entry(captcha_type)
        return await self._drive_engine(orchestrator.submit_task(self._config, entry, params))

    async def get_result(self, captcha_type: str, task_id: str) -> SolveResult:
        """Poll for a previously sent task's result. See CaptchaAI.get_result."""
        entry = get_entry(captcha_type)
        return await self._drive_engine(
            orchestrator.fetch_result(self._config, entry, task_id)
        )

    async def aclose(self) -> None:
        """Close the underlying async transport and release its connections."""
        await self._transport.aclose()

    async def __aenter__(self) -> "AsyncCaptchaAI":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.aclose()
