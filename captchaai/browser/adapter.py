# ── What this file IS ─────────────────────────────────────────────────────────
# Thin sync/async Playwright Page adapters, proxy converter, and lazy Playwright
# importers so the SDK carries zero import-time dependency on `playwright`.

from __future__ import annotations

from typing import Any, Callable

from ..helpers.validation import validate_proxy_options


class SyncPageDriver:
    """Uniform wrapper around a synchronous Playwright `Page` (or test double)."""

    def __init__(self, page: Any) -> None:
        self._page = page

    def evaluate(self, script: str, arg: Any = None) -> Any:
        return self._page.evaluate(script) if arg is None else self._page.evaluate(script, arg)

    def url(self) -> str:
        val = self._page.url
        return str(val)

    def add_cookies(self, cookies: list[dict[str, Any]]) -> None:
        self._page.context.add_cookies(cookies)


class AsyncPageDriver:
    """Uniform wrapper around an asynchronous Playwright `Page` (or test double)."""

    def __init__(self, page: Any) -> None:
        self._page = page

    async def evaluate(self, script: str, arg: Any = None) -> Any:
        if arg is None:
            return await self._page.evaluate(script)
        return await self._page.evaluate(script, arg)

    async def url(self) -> str:
        val = self._page.url
        return str(val)

    async def add_cookies(self, cookies: list[dict[str, Any]]) -> None:
        await self._page.context.add_cookies(cookies)


def to_sync_driver(page: Any) -> SyncPageDriver:
    """Wrap a sync `Page` in `SyncPageDriver` if not already wrapped."""
    return page if isinstance(page, SyncPageDriver) else SyncPageDriver(page)


def to_async_driver(page: Any) -> AsyncPageDriver:
    """Wrap an async `Page` in `AsyncPageDriver` if not already wrapped."""
    return page if isinstance(page, AsyncPageDriver) else AsyncPageDriver(page)


def parse_playwright_proxy(
    proxy: str | None,
    proxytype: str | None,
) -> dict[str, str] | None:
    """Convert `"user:pass@host:port"` + `"HTTP"`/`"HTTPS"` to a Playwright proxy dict."""
    normalized_type = validate_proxy_options(proxy, proxytype)
    if not proxy:
        return None
    scheme = (normalized_type or "HTTP").lower()
    if "@" in proxy:
        creds, host_port = proxy.rsplit("@", 1)
        username, _, password = creds.partition(":")
        out: dict[str, str] = {"server": f"{scheme}://{host_port}", "username": username}
        if password:
            out["password"] = password
        return out
    return {"server": f"{scheme}://{proxy}"}


def require_sync_playwright() -> Callable[[], Any]:
    """Lazily import `playwright.sync_api.sync_playwright` or raise a clear ImportError."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ImportError(
            'Playwright is required for solve_url(). Install with: '
            'pip install "captchaai[playwright]" && playwright install chromium'
        ) from exc
    return sync_playwright


def require_async_playwright() -> Callable[[], Any]:
    """Lazily import `playwright.async_api.async_playwright` or raise a clear ImportError."""
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise ImportError(
            'Playwright is required for solve_url(). Install with: '
            'pip install "captchaai[playwright]" && playwright install chromium'
        ) from exc
    return async_playwright
