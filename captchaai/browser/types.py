# ── What this file IS ─────────────────────────────────────────────────────────
# Data models bridging browser DOM extraction (`get_captchas_params`) with the
# CaptchaAI API solver (`_solve_type`) and page injection (`inject_on_page`).

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..core.result import SolveResult
from ..exceptions import ValidationError


@dataclass
class CaptchaParams:
    """Parameters extracted from a single token-mode CAPTCHA on a live page."""

    captcha_type: str
    pageurl: str
    sitekey: str | None = None
    action: str | None = None
    invisible: bool = False
    enterprise: bool = False
    s: str | None = None
    cdata: str | None = None
    container_id: str | None = None
    callback: str | None = None
    binded_button_id: str | None = None
    user_agent: str | None = None

    def to_api_params(self, default_v3_action: str = "verify") -> dict[str, Any]:
        """Build the parameter dict expected by `CaptchaAI._solve_type()`."""
        params: dict[str, Any] = {"pageurl": self.pageurl}

        if self.captcha_type in (
            "recaptcha_v2",
            "recaptcha_v2_invisible",
            "recaptcha_v2_enterprise",
        ):
            if self.sitekey is not None:
                params["googlekey"] = self.sitekey
            if self.invisible or self.captcha_type == "recaptcha_v2_invisible":
                params["invisible"] = 1
            if self.enterprise or self.captcha_type == "recaptcha_v2_enterprise":
                params["enterprise"] = 1
            if self.action is not None:
                params["action"] = self.action
            if self.s is not None:
                params["data-s"] = self.s
        elif self.captcha_type in ("recaptcha_v3", "recaptcha_v3_enterprise"):
            if self.sitekey is not None:
                params["googlekey"] = self.sitekey
            params["version"] = "v3"
            params["action"] = self.action or default_v3_action
            if self.enterprise or self.captcha_type == "recaptcha_v3_enterprise":
                params["enterprise"] = 1
        elif self.captcha_type == "turnstile":
            if self.sitekey is not None:
                params["sitekey"] = self.sitekey
            if self.action is not None:
                params["action"] = self.action
            if self.cdata is not None:
                params["cdata"] = self.cdata
        elif self.captcha_type == "cloudflare_challenge":
            pass
        else:
            raise ValidationError(
                f"Unsupported browser captcha type: {self.captcha_type!r}"
            )

        if self.user_agent is not None:
            params["user_agent"] = self.user_agent
        return params


@dataclass
class PageSolveResult:
    """Outcome of solving (and optionally injecting) one detected page CAPTCHA."""

    params: CaptchaParams
    result: SolveResult | None = None
    injected: bool = False
    error: str | None = None
