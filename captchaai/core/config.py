# ── What this file IS ─────────────────────────────────────────────────────────
# The Config dataclass: every client setting in one place.
# It exists so configuration is collected once at client creation and passed down
# to the orchestrator as a single object, instead of threading many loose args.

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Config:
    """All settings for one client instance, fixed at creation time.

    Holds both the user-facing options (api_key, proxy, proxytype, auto_retry)
    and the internal tuning knobs (base_url, timeouts, retry/poll bounds). The
    orchestrator reads from this object; nothing here is type-specific (that lives
    in the registry).
    """

    # ── User-facing settings ──────────────────────────────────────────────────
    api_key: str  # 32-char CaptchaAI key; validated at startup via threadsinfo
    proxy: str | None = None  # "user:pass@host:port"; forwarded on every solve
    proxytype: str | None = None  # required when proxy is set: HTTP or HTTPS
    auto_retry: bool = True  # True = SDK retries with backoff; False = raise immediately on transient errors

    # ── Endpoint settings ─────────────────────────────────────────────────────
    base_url: str = "https://ocr.captchaai.com"  # host serving in.php and res.php
    network_timeout: float = 30.0  # per-request HTTP timeout in seconds

    # ── Retry / poll bounds (specs require bounded loops, give no exact numbers) ─
    max_retries: int = 5  # cap on submit retry attempts before surfacing an error
    max_poll_seconds: float = 180.0  # overall poll deadline before TimeoutError
    jitter_max: float = 1.0  # max random seconds added to every sleep (anti-herd)
    submit_backoff_base: float = 5.0  # base seconds for exponential submit backoff
    thread_busy_wait: float = 5.0  # linear wait between retries while threads busy (legacy; superseded by thread_busy_timeout)
    thread_busy_timeout: float = 120.0  # seconds to keep retrying when all threads are busy;
    # must cover the maximum expected solve time for the captcha type.
    # Default 120s covers reCAPTCHA v2 (60-80s) and Cloudflare Challenge (~90s).
