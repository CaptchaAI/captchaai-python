# ── What this file IS ─────────────────────────────────────────────────────────
# The registry: the ONE table that holds every captcha type's behaviour.
# It exists so adding a new captcha type is a data change (one new row), never a
# code change. The orchestrator reads rows from here and NEVER branches on type
# name itself — if type-specific data is needed anywhere, it lives in this file.

from __future__ import annotations

from dataclasses import dataclass, field

from ..exceptions import ValidationError


@dataclass(frozen=True)
class CaptchaTypeEntry:
    """One row of the registry — everything the engine needs to run a type.

    Fields:
        name: SDK type name, e.g. "turnstile".
        api_method: value sent as `method=` to in.php.
        required_params: API param names that must be present before submitting.
            Validation checks these first, so they are the keys the client builds.
        has_image: True means the image resolver runs for this type.
        solution_key: response field holding the answer ("request" or "result").
        returns_user_agent: True means also extract `user_agent` from the response.
        is_structured: True means parse the answer string as JSON (dict or list).
        initial_wait: seconds to wait before the first poll.
        poll_interval: seconds between polls.
        submit_http_method: HTTP verb for in.php ("GET" or "POST" per API spec).
        requires_proxy: True means config.proxy + config.proxytype must be set.
    """

    name: str
    api_method: str
    required_params: tuple[str, ...]
    has_image: bool
    solution_key: str
    returns_user_agent: bool
    is_structured: bool
    initial_wait: float
    poll_interval: float
    submit_http_method: str
    requires_proxy: bool = False
    valid_values: dict[str, tuple[str, ...]] = field(default_factory=dict)


# ── The table ─────────────────────────────────────────────────────────────────
# Every supported captcha type is one row. Adding a type = adding a row; the
# orchestrator never changes. Values come from captchaai_api_reference.md.
REGISTRY: dict[str, CaptchaTypeEntry] = {
    # Normal image captcha: base64 body + method=base64; POST submit.
    "normal": CaptchaTypeEntry(
        name="normal",
        api_method="base64",
        required_params=("image",),
        has_image=True,
        solution_key="request",
        returns_user_agent=False,
        is_structured=False,
        initial_wait=1,
        poll_interval=5,
        submit_http_method="POST",
    ),
    # Grid / tile selection: POST base64 submit; answer is a JSON array.
    "grid": CaptchaTypeEntry(
        name="grid",
        api_method="base64",
        required_params=("image", "instructions", "grid_size"),
        has_image=True,
        solution_key="request",
        returns_user_agent=False,
        is_structured=True,
        initial_wait=1,
        poll_interval=5,
        submit_http_method="POST",
        valid_values={"grid_size": ("3x3", "4x4")},
    ),
    # BLS captcha: nine data-URI images; answer is a JSON array of cell indices.
    "bls": CaptchaTypeEntry(
        name="bls",
        api_method="bls",
        required_params=("images", "instructions"),
        has_image=True,
        solution_key="request",
        returns_user_agent=False,
        is_structured=True,
        initial_wait=1,
        poll_interval=5,
        submit_http_method="POST",
    ),
    # reCAPTCHA v2: GET submit with query params.
    "recaptcha_v2": CaptchaTypeEntry(
        name="recaptcha_v2",
        api_method="userrecaptcha",
        required_params=("googlekey", "pageurl"),
        has_image=False,
        solution_key="request",
        returns_user_agent=False,
        is_structured=False,
        initial_wait=15,
        poll_interval=5,
        submit_http_method="GET",
    ),
    # reCAPTCHA v2 Invisible: GET submit; invisible=1 is added by the client.
    "recaptcha_v2_invisible": CaptchaTypeEntry(
        name="recaptcha_v2_invisible",
        api_method="userrecaptcha",
        required_params=("googlekey", "pageurl"),
        has_image=False,
        solution_key="request",
        returns_user_agent=False,
        is_structured=False,
        initial_wait=15,
        poll_interval=5,
        submit_http_method="GET",
    ),
    # reCAPTCHA v2 Enterprise: POST submit; token in `result` + mandatory user_agent.
    "recaptcha_v2_enterprise": CaptchaTypeEntry(
        name="recaptcha_v2_enterprise",
        api_method="userrecaptcha",
        required_params=("googlekey", "pageurl"),
        has_image=False,
        solution_key="result",
        returns_user_agent=True,
        is_structured=False,
        initial_wait=15,
        poll_interval=5,
        submit_http_method="POST",
    ),
    # reCAPTCHA v3: GET submit; needs action.
    "recaptcha_v3": CaptchaTypeEntry(
        name="recaptcha_v3",
        api_method="userrecaptcha",
        required_params=("googlekey", "pageurl", "action"),
        has_image=False,
        solution_key="request",
        returns_user_agent=False,
        is_structured=False,
        initial_wait=10,
        poll_interval=5,
        submit_http_method="GET",
    ),
    # reCAPTCHA v3 Enterprise: POST submit; token in `result` + user_agent.
    # action is required for v3 (scoring is tied to the action name).
    "recaptcha_v3_enterprise": CaptchaTypeEntry(
        name="recaptcha_v3_enterprise",
        api_method="userrecaptcha",
        required_params=("googlekey", "pageurl", "action"),
        has_image=False,
        solution_key="result",
        returns_user_agent=True,
        is_structured=False,
        initial_wait=10,
        poll_interval=5,
        submit_http_method="POST",
    ),
    # Cloudflare Turnstile: GET submit; token in `request` (no user_agent per API).
    "turnstile": CaptchaTypeEntry(
        name="turnstile",
        api_method="turnstile",
        required_params=("sitekey", "pageurl"),
        has_image=False,
        solution_key="request",
        returns_user_agent=False,
        is_structured=False,
        initial_wait=10,
        poll_interval=5,
        submit_http_method="GET",
    ),
    # Cloudflare Challenge: POST submit; cf_clearance in `result`; proxy mandatory.
    "cloudflare_challenge": CaptchaTypeEntry(
        name="cloudflare_challenge",
        api_method="cloudflare_challenge",
        required_params=("pageurl",),
        has_image=False,
        solution_key="result",
        returns_user_agent=True,
        is_structured=False,
        initial_wait=15,
        poll_interval=5,
        submit_http_method="POST",
        requires_proxy=True,
    ),
    # GeeTest v3: GET submit; answer is a JSON dict inside `request`.
    "geetest": CaptchaTypeEntry(
        name="geetest",
        api_method="geetest",
        required_params=("gt", "challenge", "pageurl"),
        has_image=False,
        solution_key="request",
        returns_user_agent=False,
        is_structured=True,
        initial_wait=15,
        poll_interval=5,
        submit_http_method="GET",
    ),
    # CaptchaFox: GET submit; browser-interactive slider challenge.
    # Proxy is mandatory — the solver loads the page through the proxy.
    # Returns token in `request` + user_agent (different from CF Challenge which uses `result`).
    "captchafox": CaptchaTypeEntry(
        name="captchafox",
        api_method="captchafox",
        required_params=("sitekey", "pageurl"),
        has_image=False,
        solution_key="request",
        returns_user_agent=True,
        is_structured=False,
        initial_wait=10,
        poll_interval=5,
        submit_http_method="GET",
        requires_proxy=True,
    ),
    # Friendly Captcha: GET submit; PoW-based challenge, no proxy required.
    # Returns a plain token in `request`.
    "friendly_captcha": CaptchaTypeEntry(
        name="friendly_captcha",
        api_method="friendly_captcha",
        required_params=("sitekey", "pageurl"),
        has_image=False,
        solution_key="request",
        returns_user_agent=False,
        is_structured=False,
        initial_wait=10,
        poll_interval=5,
        submit_http_method="GET",
    ),
    # Lemin: GET submit; puzzle-based challenge.
    # Answer is a structured JSON dict {"answer": "...", "challenge_uuid": "..."}.
    # API uses snake_case param names in in.php format (captcha_id, div_id).
    "lemin": CaptchaTypeEntry(
        name="lemin",
        api_method="lemin",
        required_params=("captcha_id", "div_id", "pageurl"),
        has_image=False,
        solution_key="request",
        returns_user_agent=False,
        is_structured=True,
        initial_wait=10,
        poll_interval=5,
        submit_http_method="GET",
    ),
}


def get_entry(name: str) -> CaptchaTypeEntry:
    """Return the registry row for a captcha type.

    Parameters:
        name: SDK type name to look up.

    Returns:
        The CaptchaTypeEntry for that type.

    Raises:
        ValidationError: if the type name is not in the registry (caught before
        any HTTP call is made).
    """
    try:
        return REGISTRY[name]
    except KeyError:
        # Unknown type is a caller mistake — fail fast with a clear message.
        raise ValidationError(f"Unknown captcha type: {name!r}")
