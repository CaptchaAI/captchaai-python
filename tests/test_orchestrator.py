"""Tests for core/orchestrator.py engine generators."""

import pytest

from captchaai.core import orchestrator
from captchaai.core.registry import get_entry
from captchaai.exceptions import (
    APIError,
    InvalidKeyError,
    NetworkError,
    NoThreadsError,
    ProxyError,
    ThreadLimitError,
    TimeoutError,
    UnsolvableError,
    ValidationError,
)
from tests.conftest import (
    VALID_API_KEY,
    drive_sync_engine,
    json_response,
    make_config,
    network_fail,
    plain_text_error,
    poll_not_ready,
    poll_ok,
    submit_error,
    submit_ok,
    threadsinfo_body,
)


def test_build_endpoint_url():
    cfg = make_config(base_url="https://ocr.captchaai.com/")
    assert orchestrator.build_endpoint_url(cfg, "in.php") == "https://ocr.captchaai.com/in.php"


def test_get_thread_usage_success():
    cfg = make_config()
    engine = orchestrator.get_thread_usage(cfg)
    result = drive_sync_engine(engine, [json_response(threadsinfo_body(10, 2))])
    assert result == {"threads": 10, "working_threads": 2}


def test_get_thread_usage_invalid_key():
    cfg = make_config()
    engine = orchestrator.get_thread_usage(cfg)
    with pytest.raises(InvalidKeyError, match="Key not found"):
        drive_sync_engine(
            engine,
            [json_response({"status": 0, "request": "ERROR_KEY_DOES_NOT_EXIST"})],
        )


def test_get_thread_usage_network_error():
    cfg = make_config()
    engine = orchestrator.get_thread_usage(cfg)
    with pytest.raises(NetworkError):
        drive_sync_engine(engine, [network_fail()])


def test_submit_task_success():
    cfg = make_config()
    entry = get_entry("turnstile")
    engine = orchestrator.submit_task(
        cfg,
        entry,
        {"sitekey": "k", "pageurl": "https://example.com"},
    )
    task_id = drive_sync_engine(
        engine,
        [json_response(submit_ok("777"))],
    )
    assert task_id == "777"


def test_submit_task_missing_proxy_for_required_type():
    cfg = make_config()
    entry = get_entry("cloudflare_challenge")
    engine = orchestrator.submit_task(cfg, entry, {"pageurl": "https://example.com"})
    with pytest.raises(ValidationError, match="proxy and proxytype are required"):
        drive_sync_engine(engine, [])


def test_submit_task_fatal_api_error():
    cfg = make_config()
    entry = get_entry("turnstile")
    engine = orchestrator.submit_task(
        cfg,
        entry,
        {"sitekey": "k", "pageurl": "https://example.com"},
    )
    with pytest.raises(ValidationError, match="googlekey/sitekey is missing"):
        drive_sync_engine(
            engine,
            [json_response(submit_error("ERROR_GOOGLEKEY"))],
        )


def test_submit_task_proactive_thread_limit_when_auto_retry_false():
    cfg = make_config(auto_retry=False)
    entry = get_entry("turnstile")
    engine = orchestrator.submit_task(
        cfg,
        entry,
        {"sitekey": "k", "pageurl": "https://example.com"},
    )
    with pytest.raises(ThreadLimitError, match="All account threads are busy"):
        drive_sync_engine(
            engine,
            [json_response(threadsinfo_body(threads=5, working=5))],
        )


def test_submit_task_zero_balance_no_retry_raises_thread_limit():
    cfg = make_config(auto_retry=False)
    entry = get_entry("turnstile")
    engine = orchestrator.submit_task(
        cfg,
        entry,
        {"sitekey": "k", "pageurl": "https://example.com"},
    )
    with pytest.raises(ThreadLimitError, match="All account threads are busy"):
        drive_sync_engine(
            engine,
            [
                json_response(threadsinfo_body(threads=5, working=2)),
                json_response(submit_error("ERROR_ZERO_BALANCE")),
                json_response(threadsinfo_body(threads=5, working=5)),
            ],
        )


def test_submit_task_zero_balance_dead_account_raises_no_threads():
    cfg = make_config(auto_retry=True)
    entry = get_entry("turnstile")
    engine = orchestrator.submit_task(
        cfg,
        entry,
        {"sitekey": "k", "pageurl": "https://example.com"},
    )
    with pytest.raises(NoThreadsError, match="Account expired"):
        drive_sync_engine(
            engine,
            [
                json_response(submit_error("ERROR_ZERO_BALANCE")),
                json_response(threadsinfo_body(threads=5, working=2)),
            ],
        )


def test_submit_task_zero_balance_retries_then_succeeds(no_sleep):
    cfg = make_config(auto_retry=True, thread_busy_timeout=120.0)
    entry = get_entry("turnstile")
    engine = orchestrator.submit_task(
        cfg,
        entry,
        {"sitekey": "k", "pageurl": "https://example.com"},
    )
    task_id = drive_sync_engine(
        engine,
        [
            json_response(submit_error("ERROR_ZERO_BALANCE")),
            json_response(threadsinfo_body(threads=5, working=5)),
            json_response(submit_ok("888")),
        ],
    )
    assert task_id == "888"


def test_submit_task_zero_balance_timeout_exhausted(no_sleep):
    cfg = make_config(auto_retry=True, thread_busy_timeout=5.0)
    entry = get_entry("turnstile")
    engine = orchestrator.submit_task(
        cfg,
        entry,
        {"sitekey": "k", "pageurl": "https://example.com"},
    )
    responses = [
        json_response(submit_error("ERROR_ZERO_BALANCE")),
        json_response(threadsinfo_body(threads=5, working=5)),
    ]
    for _ in range(3):
        responses.extend(
            [
                json_response(submit_error("ERROR_ZERO_BALANCE")),
                json_response(threadsinfo_body(5, 5)),
            ]
        )

    with pytest.raises(ThreadLimitError, match="retries exhausted"):
        drive_sync_engine(engine, responses)


def test_submit_task_transient_error_retries_then_raises(no_sleep):
    cfg = make_config(auto_retry=True, max_retries=1)
    entry = get_entry("turnstile")
    engine = orchestrator.submit_task(
        cfg,
        entry,
        {"sitekey": "k", "pageurl": "https://example.com"},
    )
    with pytest.raises(APIError, match="retries exhausted"):
        drive_sync_engine(
            engine,
            [
                json_response(submit_error("ERROR_SERVER_ERROR")),
                json_response(submit_error("ERROR_SERVER_ERROR")),
            ],
        )


def test_submit_task_transient_error_no_auto_retry():
    cfg = make_config(auto_retry=False)
    entry = get_entry("turnstile")
    engine = orchestrator.submit_task(
        cfg,
        entry,
        {"sitekey": "k", "pageurl": "https://example.com"},
    )
    with pytest.raises(APIError, match="Transient server error"):
        drive_sync_engine(
            engine,
            [
                json_response(threadsinfo_body()),
                json_response(submit_error("ERROR_SERVER_ERROR")),
            ],
        )


def test_poll_until_ready_success_after_not_ready(no_sleep):
    cfg = make_config(jitter_max=0.0)
    entry = get_entry("turnstile")
    engine = orchestrator.poll_until_ready(cfg, entry, "123")
    body = drive_sync_engine(
        engine,
        [
            json_response(poll_not_ready()),
            json_response(poll_ok(entry, "token")),
        ],
    )
    assert body["request"] == "token"


def test_poll_until_ready_timeout(no_sleep):
    cfg = make_config(max_poll_seconds=5.0, jitter_max=0.0)
    entry = get_entry("turnstile")
    engine = orchestrator.poll_until_ready(cfg, entry, "123")
    responses = []
    for _ in range(3):
        responses.append(json_response(poll_not_ready()))
    with pytest.raises(TimeoutError, match="Poll deadline exceeded"):
        drive_sync_engine(engine, responses)


def test_poll_until_ready_unsolvable():
    cfg = make_config()
    entry = get_entry("turnstile")
    engine = orchestrator.poll_until_ready(cfg, entry, "123")
    with pytest.raises(UnsolvableError, match="could not be solved"):
        drive_sync_engine(
            engine,
            [json_response({"status": 0, "request": "ERROR_CAPTCHA_UNSOLVABLE"})],
        )


def test_poll_proxy_error_no_auto_retry(no_sleep):
    cfg = make_config(auto_retry=False, jitter_max=0.0)
    entry = get_entry("turnstile")
    engine = orchestrator.poll_until_ready(cfg, entry, "123")
    with pytest.raises(ProxyError, match="Proxy connection failed"):
        drive_sync_engine(
            engine,
            [json_response({"status": 0, "request": "ERROR_PROXY_CONNECTION_FAILED"})],
        )


def test_solve_captcha_end_to_end(no_sleep):
    cfg = make_config(jitter_max=0.0)
    entry = get_entry("turnstile")
    engine = orchestrator.solve_captcha(
        cfg,
        entry,
        {"sitekey": "k", "pageurl": "https://example.com"},
    )
    result = drive_sync_engine(
        engine,
        [
            json_response(submit_ok("42")),
            json_response(poll_ok(entry, "final-token")),
        ],
    )
    assert result.task_id == "42"
    assert result.solution == "final-token"


def test_get_body_or_raise_plain_text_fatal_error():
    with pytest.raises(ValidationError, match="Bad image upload"):
        orchestrator.get_body_or_raise(plain_text_error("ERROR_UPLOAD"))


def test_read_thread_counts_missing_fields():
    with pytest.raises(APIError, match="threadsinfo response missing"):
        orchestrator.read_thread_counts({})
