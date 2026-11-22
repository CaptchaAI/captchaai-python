"""Unit and fixture tests for `captchaai.browser` and client browser methods."""

from __future__ import annotations

import builtins
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from captchaai import (
    RECAPTCHA_INIT_HOOK_JS,
    CaptchaParams,
    PageSolveResult,
    SolveResult,
)
from captchaai.browser.adapter import parse_playwright_proxy
from captchaai.browser.scripts import (
    GET_CLOUDFLARE_CHALLENGE_PARAMS_JS,
    GET_RECAPTCHA_PARAMS_JS,
    GET_TURNSTILE_PARAMS_JS,
    INJECT_RECAPTCHA_JS,
    INJECT_TURNSTILE_JS,
)
from captchaai.core.registry import get_entry
from captchaai.exceptions import UnsolvableError, ValidationError
from tests.conftest import (
    default_solve_handler,
    json_response,
    make_async_client,
    make_sync_client,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class _FakeSyncContext:
    def __init__(self) -> None:
        self.added_cookies: list[dict[str, Any]] = []
        self.init_scripts: list[str] = []

    def add_cookies(self, cookies: list[dict[str, Any]]) -> None:
        self.added_cookies.extend(cookies)

    def add_init_script(self, script: str) -> None:
        self.init_scripts.append(script)


class FakeSyncPage:
    """Minimal sync Playwright Page double driven by canned script results."""

    def __init__(
        self,
        url: str = "https://example.com/login",
        *,
        recaptchas: list[dict[str, Any]] | None = None,
        turnstiles: list[dict[str, Any]] | None = None,
        cloudflare_challenge: dict[str, Any] | None = None,
        inject_result: bool = True,
    ) -> None:
        self.url = url
        self.context = _FakeSyncContext()
        self.recaptchas = recaptchas or []
        self.turnstiles = turnstiles or []
        self.cloudflare_challenge = cloudflare_challenge
        self.inject_result = inject_result
        self.eval_calls: list[tuple[str, Any]] = []
        self.goto_calls: list[tuple[str, str | None]] = []
        self.wait_timeouts: list[float] = []

    def evaluate(self, script: str, arg: Any = None) -> Any:
        self.eval_calls.append((script, arg))
        if script == GET_RECAPTCHA_PARAMS_JS:
            return self.recaptchas
        if script == GET_TURNSTILE_PARAMS_JS:
            return self.turnstiles
        if script == GET_CLOUDFLARE_CHALLENGE_PARAMS_JS:
            return self.cloudflare_challenge
        if script in (INJECT_RECAPTCHA_JS, INJECT_TURNSTILE_JS):
            return self.inject_result
        raise AssertionError("Unexpected evaluate script")

    def goto(self, url: str, wait_until: str | None = None) -> None:
        self.url = url
        self.goto_calls.append((url, wait_until))

    def wait_for_timeout(self, timeout: float) -> None:
        self.wait_timeouts.append(timeout)


class _FakeAsyncContext(_FakeSyncContext):
    async def add_cookies(self, cookies: list[dict[str, Any]]) -> None:
        self.added_cookies.extend(cookies)

    async def add_init_script(self, script: str) -> None:
        self.init_scripts.append(script)


class FakeAsyncPage(FakeSyncPage):
    """Minimal async Playwright Page double driven by canned script results."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.context = _FakeAsyncContext()

    async def evaluate(self, script: str, arg: Any = None) -> Any:
        return super().evaluate(script, arg)

    async def goto(self, url: str, wait_until: str | None = None) -> None:
        super().goto(url, wait_until=wait_until)

    async def wait_for_timeout(self, timeout: float) -> None:
        super().wait_for_timeout(timeout)


# ── Detection & param extraction ──────────────────────────────────────────────

@pytest.mark.parametrize(
    "captcha_type,kwargs,expected_api",
    [
        (
            "recaptcha_v2",
            {"sitekey": "k-v2", "invisible": False, "enterprise": False},
            {"googlekey": "k-v2", "pageurl": "https://example.com/login"},
        ),
        (
            "recaptcha_v2_invisible",
            {"sitekey": "k-inv", "invisible": True, "enterprise": False},
            {"googlekey": "k-inv", "pageurl": "https://example.com/login", "invisible": 1},
        ),
        (
            "recaptcha_v2_enterprise",
            {"sitekey": "k-ent", "invisible": False, "enterprise": True, "action": "sa"},
            {
                "googlekey": "k-ent",
                "pageurl": "https://example.com/login",
                "enterprise": 1,
                "action": "sa",
            },
        ),
        (
            "recaptcha_v3",
            {"sitekey": "k-v3", "invisible": True, "enterprise": False, "action": "login"},
            {
                "googlekey": "k-v3",
                "pageurl": "https://example.com/login",
                "version": "v3",
                "action": "login",
            },
        ),
        (
            "recaptcha_v3_enterprise",
            {"sitekey": "k-v3e", "invisible": True, "enterprise": True, "action": None},
            {
                "googlekey": "k-v3e",
                "pageurl": "https://example.com/login",
                "version": "v3",
                "action": "verify",
                "enterprise": 1,
            },
        ),
    ],
)
def test_detect_and_get_captchas_params_recaptcha_variants(
    captcha_type: str,
    kwargs: dict[str, Any],
    expected_api: dict[str, Any],
) -> None:
    client, _ = make_sync_client(default_solve_handler(get_entry(captcha_type)))
    page = FakeSyncPage(recaptchas=[{"captcha_type": captcha_type, **kwargs}])

    assert client.detect_captchas(page) == [captcha_type]
    params_list = client.get_captchas_params(page)
    assert len(params_list) == 1
    assert params_list[0].captcha_type == captcha_type
    assert params_list[0].to_api_params() == expected_api
    client.close()


def test_detect_and_get_captchas_params_turnstile_and_empty_page() -> None:
    client, _ = make_sync_client(default_solve_handler(get_entry("turnstile")))

    empty_page = FakeSyncPage()
    assert client.detect_captchas(empty_page) == []
    assert client.get_captchas_params(empty_page) == []

    ts_page = FakeSyncPage(
        turnstiles=[
            {
                "sitekey": "0x4AAA",
                "action": "submit",
                "cdata": "c1",
                "callback": "onTs",
                "container_id": "ts-box",
                "user_agent": "UA/1.0",
            }
        ],
        cloudflare_challenge={"detected": True, "user_agent": "UA/1.0"},
    )
    assert client.detect_captchas(ts_page) == ["turnstile"]
    params = client.get_captchas_params(ts_page)
    assert len(params) == 1
    assert params[0].to_api_params() == {
        "pageurl": "https://example.com/login",
        "sitekey": "0x4AAA",
        "action": "submit",
        "cdata": "c1",
        "user_agent": "UA/1.0",
    }
    client.close()


async def test_async_detect_and_get_captchas_params_cloudflare_challenge() -> None:
    client, _ = await make_async_client(
        default_solve_handler(get_entry("cloudflare_challenge"))
    )
    page = FakeAsyncPage(
        url="https://protected.example.org/app",
        cloudflare_challenge={"detected": True, "user_agent": "Mozilla/5.0 CF"},
    )

    assert await client.detect_captchas(page) == ["cloudflare_challenge"]
    params = await client.get_captchas_params(page)
    assert len(params) == 1
    assert params[0].captcha_type == "cloudflare_challenge"
    assert params[0].to_api_params() == {
        "pageurl": "https://protected.example.org/app",
        "user_agent": "Mozilla/5.0 CF",
    }
    await client.aclose()


# ── Injection ─────────────────────────────────────────────────────────────────

def test_inject_on_page_recaptcha_turnstile_and_unsupported() -> None:
    client, _ = make_sync_client(default_solve_handler(get_entry("recaptcha_v2")))
    page = FakeSyncPage()

    rc_params = CaptchaParams(
        captcha_type="recaptcha_v2",
        pageurl="https://example.com",
        sitekey="k",
        container_id="rc-box",
        callback="onRc",
    )
    assert client.inject_on_page(page, rc_params, SolveResult("1", "tok-rc")) is True
    assert page.eval_calls[-1] == (
        INJECT_RECAPTCHA_JS,
        {"token": "tok-rc", "containerId": "rc-box", "callback": "onRc"},
    )

    ts_params = CaptchaParams(
        captcha_type="turnstile",
        pageurl="https://example.com",
        sitekey="0x4AAA",
    )
    assert client.inject_on_page(page, ts_params, "tok-ts") is True
    assert page.eval_calls[-1] == (
        INJECT_TURNSTILE_JS,
        {"token": "tok-ts", "containerId": None, "callback": None},
    )

    for bad_type in ("normal", "grid"):
        with pytest.raises(ValidationError, match="does not support"):
            client.inject_on_page(
                page,
                CaptchaParams(captcha_type=bad_type, pageurl="https://example.com"),
                "tok",
            )
    client.close()


def test_inject_on_page_cloudflare_cookie_sets_samesite_none() -> None:
    client, _ = make_sync_client(default_solve_handler(get_entry("cloudflare_challenge")))
    page = FakeSyncPage(url="https://sub.example.com/path")
    cf_params = CaptchaParams(
        captcha_type="cloudflare_challenge",
        pageurl="https://sub.example.com/path",
    )

    ok = client.inject_on_page(
        page, cf_params, SolveResult("1", {"cf_clearance": "clearance-abc"})
    )
    assert ok is True
    assert page.context.added_cookies == [
        {
            "name": "cf_clearance",
            "value": "clearance-abc",
            "domain": "sub.example.com",
            "path": "/",
            "httpOnly": True,
            "secure": True,
            "sameSite": "None",
        }
    ]
    client.close()


# ── solve_url (mocked Playwright) & helpers ───────────────────────────────────

def test_parse_playwright_proxy_and_missing_playwright_error(monkeypatch) -> None:
    assert parse_playwright_proxy(None, None) is None
    assert parse_playwright_proxy("u:p@1.2.3.4:8080", "http") == {
        "server": "http://1.2.3.4:8080",
        "username": "u",
        "password": "p",
    }
    with pytest.raises(ValidationError, match="proxytype"):
        parse_playwright_proxy("1.2.3.4:8080", None)

    client, _ = make_sync_client(default_solve_handler(get_entry("turnstile")))
    real_import = builtins.__import__

    def _block_playwright(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith("playwright"):
            raise ImportError("No module named 'playwright'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _block_playwright)
    with pytest.raises(ImportError, match="captchaai\\[playwright\\]"):
        client.solve_url("https://example.com")
    client.close()


def test_solve_url_sync_full_pipeline_uses_context_init_script(no_sleep) -> None:
    page = FakeSyncPage(
        recaptchas=[
            {
                "captcha_type": "recaptcha_v3",
                "sitekey": "k-v3",
                "action": "checkout",
                "invisible": True,
                "enterprise": False,
            }
        ]
    )
    launched: list[dict[str, Any]] = []

    class _FakeBrowser:
        def new_context(self) -> _FakeSyncContext:
            return page.context

        def close(self) -> None:
            launched.append({"closed": True})

    # Attach new_page onto context for solve_url flow.
    page.context.new_page = lambda: page  # type: ignore[attr-defined]

    class _FakeChromium:
        def launch(self, **kwargs: Any) -> _FakeBrowser:
            launched.append(kwargs)
            return _FakeBrowser()

    class _FakePW:
        chromium = _FakeChromium()

        def __enter__(self) -> _FakePW:
            return self

        def __exit__(self, *args: Any) -> None:
            return None

    client, transport = make_sync_client(default_solve_handler(get_entry("recaptcha_v3")))
    with patch("captchaai.client.require_sync_playwright", return_value=lambda: _FakePW()):
        results = client.solve_url(
            "https://example.com/checkout",
            headless=True,
            wait_timeout=250.0,
            close_delay=1.5,
            proxy="user:pass@127.0.0.1:8888",
            proxytype="HTTP",
        )

    assert launched[0] == {
        "headless": True,
        "proxy": {
            "server": "http://127.0.0.1:8888",
            "username": "user",
            "password": "pass",
        },
    }
    assert launched[1] == {"closed": True}
    assert page.context.init_scripts == [RECAPTCHA_INIT_HOOK_JS]
    assert page.goto_calls == [("https://example.com/checkout", "domcontentloaded")]
    assert page.wait_timeouts == [250.0, 1500.0]
    assert len(results) == 1
    assert isinstance(results[0], PageSolveResult)
    assert results[0].injected is True
    assert results[0].result is not None
    assert results[0].result.solution == "solved-token"
    submit_calls = [c for c in transport.calls if "in.php" in c[1]]
    assert submit_calls[0][2]["action"] == "checkout"
    client.close()


async def test_solve_url_async_error_handling_and_throw_on_error(no_sleep) -> None:
    page = FakeAsyncPage(
        turnstiles=[{"sitekey": "0x4AAA"}],
    )

    class _FakeAsyncBrowser:
        def __init__(self) -> None:
            self.closed = False

        async def new_context(self) -> _FakeAsyncContext:
            return page.context

        async def close(self) -> None:
            self.closed = True

    async def _new_page() -> FakeAsyncPage:
        return page

    page.context.new_page = _new_page  # type: ignore[attr-defined]
    fake_browser = _FakeAsyncBrowser()

    class _FakeAsyncChromium:
        async def launch(self, **kwargs: Any) -> _FakeAsyncBrowser:
            return fake_browser

    class _FakeAsyncPW:
        chromium = _FakeAsyncChromium()

        async def __aenter__(self) -> _FakeAsyncPW:
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

    def _unsolvable_handler(method: str, url: str, data: dict[str, Any]):
        if "threadsinfo" in str(data.get("action")):
            return json_response({"threads": 10, "working_threads": 0})
        if "in.php" in url:
            return json_response({"status": 1, "request": "999"})
        return json_response({"status": 0, "request": "ERROR_CAPTCHA_UNSOLVABLE"})

    client, _ = await make_async_client(_unsolvable_handler)
    with patch(
        "captchaai.async_client.require_async_playwright",
        return_value=lambda: _FakeAsyncPW(),
    ):
        results = await client.solve_url("https://example.com", wait_timeout=0)
        assert len(results) == 1
        assert results[0].injected is False
        assert results[0].result is None
        assert results[0].error is not None
        assert fake_browser.closed is True

        with pytest.raises(UnsolvableError, match="Captcha could not be solved"):
            await client.solve_url("https://example.com", wait_timeout=0, throw_on_error=True)

    await client.aclose()


def test_solve_url_with_existing_page_sync_and_missing_args(no_sleep) -> None:
    client, _ = make_sync_client(default_solve_handler(get_entry("recaptcha_v2")))

    with pytest.raises(ValidationError, match="Either url or page"):
        client.solve_url()

    # Already-loaded page (url=None): skips goto/wait_timeout and Playwright launch.
    loaded_page = FakeSyncPage(
        url="https://example.com/already-open",
        recaptchas=[{"captcha_type": "recaptcha_v2", "sitekey": "k-open"}],
    )
    results = client.solve_url(page=loaded_page)
    assert len(results) == 1
    assert results[0].injected is True
    assert loaded_page.goto_calls == []
    assert loaded_page.wait_timeouts == []
    assert loaded_page.context.init_scripts == []

    # Open page + url: navigates and injects without launching/closing a browser.
    nav_page = FakeSyncPage()
    nav_results = client.solve_url(
        "https://example.com/target",
        page=nav_page,
        wait_timeout=100.0,
    )
    assert nav_results == []
    assert nav_page.context.init_scripts == [RECAPTCHA_INIT_HOOK_JS]
    assert nav_page.goto_calls == [("https://example.com/target", "domcontentloaded")]
    assert nav_page.wait_timeouts == [100.0]
    client.close()


async def test_solve_url_with_existing_page_async(no_sleep) -> None:
    client, _ = await make_async_client(default_solve_handler(get_entry("turnstile")))

    with pytest.raises(ValidationError, match="Either url or page"):
        await client.solve_url()

    page = FakeAsyncPage(turnstiles=[{"sitekey": "0x4AAA"}])
    results = await client.solve_url(page=page)
    assert len(results) == 1
    assert results[0].injected is True
    assert page.goto_calls == []
    await client.aclose()


def test_import_captchaai_never_loads_playwright() -> None:
    assert "playwright" not in sys.modules


# ── Optional real-Chromium HTML fixture tests ─────────────────────────────────

def test_playwright_html_fixtures_detect_extract_and_inject() -> None:
    pw_mod = pytest.importorskip("playwright.sync_api")
    client, _ = make_sync_client(default_solve_handler(get_entry("recaptcha_v2")))

    with pw_mod.sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context()
            context.route("https://**/*", lambda route: route.abort())
            context.add_init_script(RECAPTCHA_INIT_HOOK_JS)
            page = context.new_page()

            page.goto((FIXTURES_DIR / "recaptcha_v2.html").as_uri(), wait_until="domcontentloaded")
            assert client.detect_captchas(page) == ["recaptcha_v2"]
            v2_params = client.get_captchas_params(page)
            assert len(v2_params) == 1
            assert v2_params[0].captcha_type == "recaptcha_v2"
            assert v2_params[0].sitekey == "v2-sitekey-123"
            assert v2_params[0].action == "action"
            assert client.inject_on_page(page, v2_params[0], "tok-v2") is True
            assert page.evaluate("() => window.v2CallbackToken") == "tok-v2"

            page.goto((FIXTURES_DIR / "recaptcha_v3.html").as_uri(), wait_until="domcontentloaded")
            assert client.detect_captchas(page) == ["recaptcha_v3"]
            v3_params = client.get_captchas_params(page)
            assert v3_params[0].sitekey == "v3-sitekey-456"
            assert v3_params[0].action == "checkout"

            page.goto((FIXTURES_DIR / "turnstile.html").as_uri())
            assert client.detect_captchas(page) == ["turnstile"]
            ts_params = client.get_captchas_params(page)
            assert ts_params[0].sitekey == "0x4AAAAAAATestKey"
            assert ts_params[0].cdata == "cdata-xyz"
            assert client.inject_on_page(page, ts_params[0], "tok-ts") is True
            assert page.evaluate("() => window.tsCallbackToken") == "tok-ts"

            page.goto((FIXTURES_DIR / "cloudflare_challenge.html").as_uri())
            assert client.detect_captchas(page) == ["cloudflare_challenge"]

            # Programmatic turnstile.render() via external script + callback capture.
            from urllib.parse import quote

            prog_html = """<!doctype html><body>
                <div id="ts-mount"></div>
                <input type="hidden" name="cf-turnstile-response" value="">
                <script src="data:application/javascript,window.turnstile%3D%7Brender%3Afunction()%7B%7D%7D%3B" onload="window.turnstile.render('#ts-mount', { sitekey: '0x4ProgrammaticKey', action: 'login', callback: function(tok) { window.progCallbackToken = tok; } })"></script>
                </body>"""
            page.goto("data:text/html," + quote(prog_html), wait_until="load")
            prog_params = client.get_captchas_params(page)
            assert len(prog_params) == 1
            assert prog_params[0].sitekey == "0x4ProgrammaticKey"
            assert prog_params[0].action == "login"
            assert client.inject_on_page(page, prog_params[0], "tok-prog") is True
            assert page.evaluate("() => window.progCallbackToken") == "tok-prog"

            # Open shadowRoot iframe fallback when no init hook or .cf-turnstile exists.
            shadow_html = """<!doctype html><body>
                <div id="shadow-host"></div>
                <script>
                  window.__captchaai_turnstiles = [];
                  const host = document.getElementById("shadow-host");
                  const sr = host.attachShadow({ mode: "open" });
                  const frame = document.createElement("iframe");
                  frame.src = "https://challenges.cloudflare.com/cdn-cgi/challenge-platform/h/b/turnstile/f/av0/rch/abc/0x4ShadowKey/auto";
                  sr.appendChild(frame);
                </script>
                </body>"""
            page.goto("data:text/html," + quote(shadow_html), wait_until="load")
            shadow_params = client.get_captchas_params(page)
            assert len(shadow_params) == 1
            assert shadow_params[0].sitekey == "0x4ShadowKey"

            # reCAPTCHA v2 `sa` iframe param, `promise-callback`, and throwing callback safety.
            sa_html = """<!doctype html><body>
                <iframe title="reCAPTCHA" src="https://www.google.com/recaptcha/enterprise/anchor?sa=enterprise_login"></iframe>
                <textarea name="g-recaptcha-response"></textarea>
                <script>
                  window.___grecaptcha_cfg = {
                    clients: {
                      0: { id: 0, cfg: { sitekey: "k-sa", "promise-callback": function(t) { window.saTok = t; throw new Error("boom"); } } }
                    }
                  };
                </script>
                </body>"""
            page.goto("data:text/html," + quote(sa_html), wait_until="load")
            sa_params = client.get_captchas_params(page)
            assert len(sa_params) == 1
            assert sa_params[0].action == "enterprise_login"
            assert client.inject_on_page(page, sa_params[0], "tok-sa") is True
            assert page.evaluate("() => window.saTok") == "tok-sa"
            assert page.evaluate("() => document.querySelector('textarea[name=\"g-recaptcha-response\"]').value") == "tok-sa"

            # Full-page Cloudflare Challenge with embedded Turnstile must resolve to cloudflare_challenge.
            cf_embedded_html = """<!doctype html><body>
                <div id="cf-shadow"></div>
                <script>
                  window._cf_chl_opt = { cType: "managed" };
                  window.__captchaai_turnstiles = [{ sitekey: "0x4EmbeddedChallengeKey" }];
                  const sr = document.getElementById("cf-shadow").attachShadow({ mode: "open" });
                  const frame = document.createElement("iframe");
                  frame.src = "https://challenges.cloudflare.com/cdn-cgi/challenge-platform/h/b/turnstile/f/av0/rch/xyz/0x4EmbeddedChallengeKey/dark";
                  sr.appendChild(frame);
                </script>
                </body>"""
            page.goto("data:text/html," + quote(cf_embedded_html), wait_until="load")
            assert client.detect_captchas(page) == ["cloudflare_challenge"]
        finally:
            browser.close()
    client.close()
