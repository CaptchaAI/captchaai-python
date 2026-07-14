"""Shared fixtures and mock transport helpers for the CaptchaAI SDK test suite."""

from __future__ import annotations

import asyncio
from typing import Any, Callable
from unittest.mock import patch

import pytest

from captchaai.async_client import AsyncCaptchaAI
from captchaai.client import CaptchaAI
from captchaai.core.config import Config
from captchaai.core.orchestrator import ApiCall, Sleep
from captchaai.core.registry import REGISTRY, CaptchaTypeEntry, get_entry
from captchaai.transport.base import UniformResponse

VALID_API_KEY = "a" * 32

# Minimal 1x1 PNG as raw base64 (passes image dimension check).
MIN_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

DEFAULT_THREADS = 10
DEFAULT_WORKING = 0


def threadsinfo_body(threads: int = DEFAULT_THREADS, working: int = DEFAULT_WORKING) -> dict:
    return {"threads": threads, "working_threads": working}


def submit_ok(task_id: str = "12345") -> dict:
    return {"status": 1, "request": task_id}


def submit_error(code: str) -> dict:
    return {"status": 0, "request": code}


def poll_not_ready() -> dict:
    return {"status": 0, "request": "CAPCHA_NOT_READY"}


def poll_ok(entry: CaptchaTypeEntry, solution: Any, user_agent: str | None = None) -> dict:
    body: dict = {"status": 1, entry.solution_key: solution}
    if user_agent is not None:
        body["user_agent"] = user_agent
    return body


def json_response(body: dict, status_code: int = 200) -> UniformResponse:
    return UniformResponse(status_code, body)


def network_fail(
    error_type: str = "ConnectError",
    error_message: str = "connection refused",
) -> UniformResponse:
    return UniformResponse(
        999,
        None,
        transport_error_type=error_type,
        transport_error_message=error_message,
    )


def plain_text_error(code: str, status_code: int = 200) -> UniformResponse:
    return UniformResponse(status_code, None, raw_text=code)


class MockSyncTransport:
    """Sync transport mock driven by a per-request handler."""

    def __init__(self, handler: Callable[[str, str, dict], UniformResponse]) -> None:
        self.handler = handler
        self.calls: list[tuple[str, str, dict]] = []
        self.closed = False

    def request_raw(self, method: str, url: str, data: dict) -> UniformResponse:
        self.calls.append((method, url, dict(data)))
        return self.handler(method, url, data)

    def close(self) -> None:
        self.closed = True


class MockAsyncTransport:
    """Async transport mock driven by a per-request handler."""

    def __init__(self, handler: Callable[[str, str, dict], UniformResponse]) -> None:
        self.handler = handler
        self.calls: list[tuple[str, str, dict]] = []
        self.closed = False

    async def request_raw(self, method: str, url: str, data: dict) -> UniformResponse:
        self.calls.append((method, url, dict(data)))
        return self.handler(method, url, data)

    async def aclose(self) -> None:
        self.closed = True


def default_solve_handler(
    entry: CaptchaTypeEntry,
    *,
    task_id: str = "12345",
    solution: Any | None = None,
    user_agent: str | None = None,
    threads: int = DEFAULT_THREADS,
    working: int = DEFAULT_WORKING,
    poll_attempts_not_ready: int = 0,
) -> Callable[[str, str, dict], UniformResponse]:
    """Build a handler for a standard submit → poll solve flow."""
    if solution is None:
        if entry.is_structured:
            if entry.name == "geetest":
                solution = '{"challenge":"c","validate":"v","seccode":"s"}'
            elif entry.name == "lemin":
                solution = '{"answer":"a","challenge_uuid":"u"}'
            else:
                solution = "[0, 3]"
        else:
            solution = "solved-token"

    if entry.returns_user_agent and user_agent is None:
        user_agent = "Mozilla/5.0 Test"

    poll_count = {"n": 0}

    def handler(method: str, url: str, data: dict) -> UniformResponse:
        if "res.php" in url and data.get("action") == "threadsinfo":
            return json_response(threadsinfo_body(threads, working))
        if "in.php" in url:
            return json_response(submit_ok(task_id))
        if "res.php" in url and data.get("action") == "get":
            if poll_count["n"] < poll_attempts_not_ready:
                poll_count["n"] += 1
                return json_response(poll_not_ready())
            return json_response(poll_ok(entry, solution, user_agent))
        return json_response({"status": 0, "request": "UNEXPECTED_TEST_REQUEST"})

    return handler


def make_config(**overrides) -> Config:
    defaults = dict(
        api_key=VALID_API_KEY,
        auto_retry=True,
        max_retries=5,
        max_poll_seconds=180.0,
        thread_busy_timeout=120.0,
        jitter_max=0.0,  # deterministic sleeps in orchestrator unit tests
    )
    defaults.update(overrides)
    return Config(**defaults)


def make_sync_client(
    handler: Callable[[str, str, dict], UniformResponse],
    **config_kwargs,
) -> tuple[CaptchaAI, MockSyncTransport]:
    transport = MockSyncTransport(handler)
    with patch("captchaai.client.SyncTransport", return_value=transport):
        client = CaptchaAI(api_key=VALID_API_KEY, **config_kwargs)
    return client, transport


def make_sync_bypass(
    handler: Callable[[str, str, dict], UniformResponse],
    **config_kwargs,
) -> tuple[CaptchaAI, MockSyncTransport]:
    """Build a sync client without running __init__ (per source test hook)."""
    import threading

    transport = MockSyncTransport(handler)
    cfg = make_config(**config_kwargs)
    client = object.__new__(CaptchaAI)
    client._config = cfg
    client._transport = transport
    client._thread_cap = config_kwargs.get("thread_cap", DEFAULT_THREADS)
    client._inflight = 0
    client._inflight_lock = threading.Lock()
    return client, transport


async def make_async_client(
    handler: Callable[[str, str, dict], UniformResponse],
    **config_kwargs,
) -> tuple[AsyncCaptchaAI, MockAsyncTransport]:
    transport = MockAsyncTransport(handler)
    with patch("captchaai.async_client.AsyncTransport", return_value=transport):
        client = await AsyncCaptchaAI.create(api_key=VALID_API_KEY, **config_kwargs)
    return client, transport


def drive_sync_engine(engine, responses: list[UniformResponse]):
    """Run an orchestrator generator with canned transport responses.

    ``responses`` supplies one UniformResponse per ApiCall, in order.
    Sleep effects do not consume entries from this list.
    """
    try:
        effect = next(engine)
        response_iter = iter(responses)
        while True:
            if isinstance(effect, ApiCall):
                response = next(response_iter)
                effect = engine.send(response)
            elif isinstance(effect, Sleep):
                effect = engine.send(None)
            else:
                raise RuntimeError(f"Unknown effect: {effect!r}")
    except StopIteration as stop:
        return stop.value


# ── Registry → client method mapping for parametrized solve tests ──────────────

REGISTRY_SOLVE_CASES: list[dict] = [
    {
        "registry_name": "normal",
        "method": "normal",
        "kwargs": {"image": MIN_PNG_B64},
        "proxy": None,
    },
    {
        "registry_name": "grid",
        "method": "grid",
        "kwargs": {
            "image": MIN_PNG_B64,
            "instructions": "select traffic lights",
            "grid_size": "3x3",
        },
        "proxy": None,
    },
    {
        "registry_name": "bls",
        "method": "bls",
        "kwargs": {"images": [MIN_PNG_B64] * 9, "instructions": "pick cells"},
        "proxy": None,
    },
    {
        "registry_name": "recaptcha_v2",
        "method": "recaptcha_v2",
        "kwargs": {"sitekey": "sitekey", "url": "https://example.com"},
        "proxy": None,
    },
    {
        "registry_name": "recaptcha_v2_invisible",
        "method": "recaptcha_v2",
        "kwargs": {
            "sitekey": "sitekey",
            "url": "https://example.com",
            "invisible": True,
        },
        "proxy": None,
    },
    {
        "registry_name": "recaptcha_v2_enterprise",
        "method": "recaptcha_v2",
        "kwargs": {
            "sitekey": "sitekey",
            "url": "https://example.com",
            "enterprise": True,
        },
        "proxy": None,
    },
    {
        "registry_name": "recaptcha_v3",
        "method": "recaptcha_v3",
        "kwargs": {
            "sitekey": "sitekey",
            "url": "https://example.com",
            "action": "login",
        },
        "proxy": None,
    },
    {
        "registry_name": "recaptcha_v3_enterprise",
        "method": "recaptcha_v3",
        "kwargs": {
            "sitekey": "sitekey",
            "url": "https://example.com",
            "action": "login",
            "enterprise": True,
        },
        "proxy": None,
    },
    {
        "registry_name": "turnstile",
        "method": "turnstile",
        "kwargs": {"sitekey": "sitekey", "url": "https://example.com"},
        "proxy": None,
    },
    {
        "registry_name": "cloudflare_challenge",
        "method": "cloudflare_challenge",
        "kwargs": {"url": "https://example.com"},
        "proxy": {"proxy": "user:pass@host:port", "proxytype": "HTTP"},
    },
    {
        "registry_name": "geetest",
        "method": "geetest",
        "kwargs": {
            "gt": "gt-value",
            "challenge": "challenge-value",
            "url": "https://example.com",
        },
        "proxy": None,
    },
    {
        "registry_name": "captchafox",
        "method": "captchafox",
        "kwargs": {"sitekey": "sitekey", "url": "https://example.com"},
        "proxy": {"proxy": "user:pass@host:port", "proxytype": "HTTP"},
    },
    {
        "registry_name": "friendly_captcha",
        "method": "friendly_captcha",
        "kwargs": {"sitekey": "sitekey", "url": "https://example.com"},
        "proxy": None,
    },
    {
        "registry_name": "lemin",
        "method": "lemin",
        "kwargs": {
            "captcha_id": "CAPTCHA_ID",
            "div_id": "lemin-cropped-captcha",
            "url": "https://example.com",
        },
        "proxy": None,
    },
]


@pytest.fixture
def no_sleep(monkeypatch):
    """Disable real sleeps so orchestrator logical timers advance instantly."""

    async def _noop_async_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("captchaai.client.time.sleep", lambda _s: None)
    monkeypatch.setattr("captchaai.async_client.asyncio.sleep", _noop_async_sleep)
