"""Parametrized tests for API error code → exception class mapping."""

import pytest

from captchaai.core import orchestrator
from captchaai.exceptions import (
    APIError,
    InvalidKeyError,
    NetworkError,
    ProxyError,
    UnsolvableError,
    ValidationError,
)
from tests.conftest import drive_sync_engine, json_response, make_config, network_fail


@pytest.mark.parametrize(
    "code,exc_type,message",
    [
        ("ERROR_WRONG_USER_KEY", InvalidKeyError, "Key must be 32 characters"),
        ("ERROR_KEY_DOES_NOT_EXIST", InvalidKeyError, "Key not found"),
        ("ERROR_BAD_PARAMETERS", ValidationError, "Required parameters missing"),
        ("ERROR_PAGEURL", ValidationError, "pageurl is missing"),
        ("ERROR_GOOGLEKEY", ValidationError, "googlekey/sitekey is missing"),
        ("ERROR_BAD_PROXY", ProxyError, "Proxy was marked bad"),
        ("IP_BANNED", APIError, "IP banned"),
    ],
)
def test_submit_fatal_error_mapping(code, exc_type, message):
    cfg = make_config()
    from captchaai.core.registry import get_entry

    entry = get_entry("turnstile")
    engine = orchestrator.submit_task(
        cfg,
        entry,
        {"sitekey": "k", "pageurl": "https://example.com"},
    )
    with pytest.raises(exc_type, match=message):
        drive_sync_engine(engine, [json_response({"status": 0, "request": code})])


@pytest.mark.parametrize(
    "code,exc_type,message",
    [
        ("ERROR_CAPTCHA_UNSOLVABLE", UnsolvableError, "could not be solved"),
        ("ERROR_WRONG_CAPTCHA_ID", APIError, "Task ID not found"),
    ],
)
def test_poll_fatal_error_mapping(code, exc_type, message):
    cfg = make_config(jitter_max=0.0)
    from captchaai.core.registry import get_entry

    entry = get_entry("turnstile")
    engine = orchestrator.poll_until_ready(cfg, entry, "123")
    with pytest.raises(exc_type, match=message):
        drive_sync_engine(
            engine,
            [json_response({"status": 0, "request": code})],
        )


def test_network_error_on_transport_failure():
    cfg = make_config()
    engine = orchestrator.get_thread_usage(cfg)
    with pytest.raises(NetworkError, match="Connection to the CaptchaAI API failed"):
        drive_sync_engine(
            engine,
            [network_fail(error_type="ConnectError", error_message="connection refused")],
        )


def test_network_error_timeout_message():
    cfg = make_config()
    engine = orchestrator.get_thread_usage(cfg)
    with pytest.raises(NetworkError, match="Network timeout"):
        drive_sync_engine(
            engine,
            [network_fail(error_type="ReadTimeout", error_message="timed out")],
        )
