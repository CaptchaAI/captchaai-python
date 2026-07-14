"""Tests for thread-limit behavior (client counter + orchestrator paths)."""

import threading

import pytest

from captchaai.core.registry import get_entry
from captchaai.exceptions import ThreadLimitError
from tests.conftest import (
    default_solve_handler,
    json_response,
    make_sync_bypass,
    make_sync_client,
    make_async_client,
    submit_ok,
    threadsinfo_body,
)


def test_client_local_inflight_counter_raises_when_cap_reached(no_sleep):
    entry = get_entry("turnstile")
    handler = default_solve_handler(entry)
    client, _ = make_sync_bypass(handler, auto_retry=False, max_retries=0)
    client._thread_cap = 2
    client._inflight = 2
    with pytest.raises(ThreadLimitError, match="Thread cap reached"):
        client.recaptcha_v2(sitekey="k", url="https://example.com")


def test_client_inflight_decremented_after_solve(no_sleep):
    entry = get_entry("turnstile")
    handler = default_solve_handler(entry)
    client, _ = make_sync_bypass(handler, auto_retry=False, max_retries=0)
    client._thread_cap = 5
    client.recaptcha_v2(sitekey="k", url="https://example.com")
    assert client._inflight == 0


def test_orchestrator_proactive_thread_limit_via_client(no_sleep):
    """auto_retry=False triggers orchestrator threadsinfo check before submit."""

    def handler(method, url, data):
        if data.get("action") == "threadsinfo":
            return json_response(threadsinfo_body(threads=3, working=3))
        return json_response(submit_ok())

    client, _ = make_sync_client(handler, auto_retry=False, max_retries=0)
    with pytest.raises(ThreadLimitError, match="All account threads are busy"):
        client.turnstile(sitekey="k", url="https://example.com")
    client.close()


@pytest.mark.asyncio
async def test_async_client_local_inflight_counter_raises(no_sleep):
    entry = get_entry("turnstile")
    handler = default_solve_handler(entry)
    client, transport = await make_async_client(handler, auto_retry=False, max_retries=0)
    client._thread_cap = 1
    client._inflight = 1
    with pytest.raises(ThreadLimitError, match="Thread cap reached"):
        await client.turnstile(sitekey="k", url="https://example.com")
    await client.aclose()


def test_concurrent_sync_solves_respect_inflight_cap(no_sleep):
    """Two solves can run; a third with cap=2 fails while others are in-flight."""
    entry = get_entry("turnstile")
    gate = threading.Event()
    poll_started = threading.Event()

    def handler(method, url, data):
        if "res.php" in url and data.get("action") == "threadsinfo":
            return json_response(threadsinfo_body())
        if "in.php" in url:
            return json_response(submit_ok("1"))
        if "res.php" in url and data.get("action") == "get":
            poll_started.set()
            gate.wait(timeout=2)
            from tests.conftest import poll_ok

            return json_response(poll_ok(entry, "tok"))
        return json_response({"status": 0, "request": "UNEXPECTED"})

    client, _ = make_sync_bypass(handler, auto_retry=False, max_retries=0)
    client._thread_cap = 2

    errors: list[Exception] = []

    def run_solve():
        try:
            client.recaptcha_v2(sitekey="k", url="https://example.com")
        except Exception as exc:
            errors.append(exc)

    t1 = threading.Thread(target=run_solve)
    t2 = threading.Thread(target=run_solve)
    t1.start()
    t2.start()
    poll_started.wait(timeout=2)
    t3 = threading.Thread(target=run_solve)
    t3.start()
    t3.join(timeout=2)
    gate.set()
    t1.join(timeout=2)
    t2.join(timeout=2)

    assert any(isinstance(e, ThreadLimitError) for e in errors)
