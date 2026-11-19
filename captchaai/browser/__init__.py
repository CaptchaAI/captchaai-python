# ── What this file IS ─────────────────────────────────────────────────────────
# Public exports for optional Playwright browser helpers.

from __future__ import annotations

from .adapter import AsyncPageDriver, SyncPageDriver, to_async_driver, to_sync_driver
from .scripts import RECAPTCHA_INIT_HOOK_JS
from .types import CaptchaParams, PageSolveResult

__all__ = [
    "CaptchaParams",
    "PageSolveResult",
    "RECAPTCHA_INIT_HOOK_JS",
    "SyncPageDriver",
    "AsyncPageDriver",
    "to_sync_driver",
    "to_async_driver",
]
