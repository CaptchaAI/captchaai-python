# ── What this file IS ─────────────────────────────────────────────────────────
# Sans-IO browser generator engine, mirroring `core/orchestrator.py`.
# Generators yield `BrowserEffect` values (`PageEval`, `PageUrl`, `ContextAddCookies`)
# and never touch Playwright directly, so sync and async clients share 100% of the logic.

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generator
from urllib.parse import urlparse

from ..core.result import SolveResult
from ..exceptions import ValidationError
from .scripts import (
    GET_CLOUDFLARE_CHALLENGE_PARAMS_JS,
    GET_RECAPTCHA_PARAMS_JS,
    GET_TURNSTILE_PARAMS_JS,
    INJECT_RECAPTCHA_JS,
    INJECT_TURNSTILE_JS,
)
from .types import CaptchaParams


@dataclass(frozen=True)
class PageEval:
    """Effect asking the driver to evaluate JS on the active page."""

    script: str
    arg: Any = None


@dataclass(frozen=True)
class PageUrl:
    """Effect asking the driver for the active page's URL."""


@dataclass(frozen=True)
class ContextAddCookies:
    """Effect asking the driver to add cookies to the page's browser context."""

    cookies: list[dict[str, Any]]


BrowserEffect = PageEval | PageUrl | ContextAddCookies


def get_captchas_params() -> Generator[BrowserEffect, Any, list[CaptchaParams]]:
    """Extract `CaptchaParams` for every token-mode CAPTCHA detected on the page."""
    pageurl: str = yield PageUrl()
    params_list: list[CaptchaParams] = []

    recaptchas: list[dict[str, Any]] = (yield PageEval(GET_RECAPTCHA_PARAMS_JS)) or []
    for item in recaptchas:
        params_list.append(
            CaptchaParams(
                captcha_type=item["captcha_type"],
                pageurl=pageurl,
                sitekey=item.get("sitekey"),
                action=item.get("action"),
                invisible=bool(item.get("invisible", False)),
                enterprise=bool(item.get("enterprise", False)),
                s=item.get("s"),
                container_id=item.get("container_id"),
                callback=item.get("callback"),
                binded_button_id=item.get("binded_button_id"),
                user_agent=item.get("user_agent"),
            )
        )

    turnstiles: list[dict[str, Any]] = (yield PageEval(GET_TURNSTILE_PARAMS_JS)) or []
    for item in turnstiles:
        params_list.append(
            CaptchaParams(
                captcha_type="turnstile",
                pageurl=pageurl,
                sitekey=item.get("sitekey"),
                action=item.get("action"),
                cdata=item.get("cdata"),
                container_id=item.get("container_id"),
                callback=item.get("callback"),
                user_agent=item.get("user_agent"),
            )
        )

    # Full-page Cloudflare Challenge only applies when no standalone Turnstile widget exists.
    if not turnstiles:
        cf_challenge: dict[str, Any] | None = yield PageEval(
            GET_CLOUDFLARE_CHALLENGE_PARAMS_JS
        )
        if cf_challenge and cf_challenge.get("detected"):
            params_list.append(
                CaptchaParams(
                    captcha_type="cloudflare_challenge",
                    pageurl=pageurl,
                    user_agent=cf_challenge.get("user_agent"),
                )
            )

    return params_list


def detect_captchas() -> Generator[BrowserEffect, Any, list[str]]:
    """Return an order-preserving deduplicated list of CAPTCHA types on the page."""
    infos = yield from get_captchas_params()
    return list(dict.fromkeys(info.captcha_type for info in infos))


def _extract_token(result: SolveResult | str) -> str:
    raw: Any = result.solution if isinstance(result, SolveResult) else result
    if isinstance(raw, dict) and "cf_clearance" in raw:
        return str(raw["cf_clearance"])
    return str(raw)


def inject_on_page(
    params: CaptchaParams,
    result: SolveResult | str,
) -> Generator[BrowserEffect, Any, bool]:
    """Inject a solved token (or `cf_clearance` cookie) back into the page."""
    token = _extract_token(result)

    if params.captcha_type in (
        "recaptcha_v2",
        "recaptcha_v2_invisible",
        "recaptcha_v2_enterprise",
        "recaptcha_v3",
        "recaptcha_v3_enterprise",
    ):
        injected: bool = yield PageEval(
            INJECT_RECAPTCHA_JS,
            {
                "token": token,
                "containerId": params.container_id,
                "callback": params.callback,
            },
        )
        return bool(injected)

    if params.captcha_type == "turnstile":
        injected = yield PageEval(
            INJECT_TURNSTILE_JS,
            {
                "token": token,
                "containerId": params.container_id,
                "callback": params.callback,
            },
        )
        return bool(injected)

    if params.captcha_type == "cloudflare_challenge":
        parsed = urlparse(params.pageurl)
        cookie: dict[str, Any] = {
            "name": "cf_clearance",
            "value": token,
            "domain": parsed.hostname or "",
            "path": "/",
            "httpOnly": True,
            "secure": parsed.scheme == "https",
            "sameSite": "None",
        }
        yield ContextAddCookies([cookie])
        return True

    raise ValidationError(
        f"inject_on_page does not support captcha type {params.captcha_type!r}"
    )
