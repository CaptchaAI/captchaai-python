"""Tests for helpers/validation.py."""

import pytest

from captchaai.core.registry import get_entry
from captchaai.exceptions import ValidationError
from captchaai.helpers.validation import SUPPORTED_PROXY_TYPES, validate, validate_proxy_options


def test_validate_passes_when_required_params_present():
    entry = get_entry("recaptcha_v2")
    validate({"googlekey": "key", "pageurl": "https://example.com"}, entry)


def test_validate_missing_required_param():
    entry = get_entry("recaptcha_v3")
    with pytest.raises(ValidationError, match="missing required parameter"):
        validate({"googlekey": "key", "pageurl": "https://example.com"}, entry)


def test_validate_empty_string_param_fails():
    entry = get_entry("turnstile")
    with pytest.raises(ValidationError, match="pageurl"):
        validate({"sitekey": "k", "pageurl": "   "}, entry)


def test_validate_invalid_grid_size():
    entry = get_entry("grid")
    with pytest.raises(ValidationError, match="grid_size"):
        validate(
            {
                "image": "x",
                "instructions": "lights",
                "grid_size": "5x5",
            },
            entry,
        )


def test_validate_proxy_options_supports_http_and_https_only():
    assert SUPPORTED_PROXY_TYPES == ("HTTP", "HTTPS")
    assert validate_proxy_options("user:pass@host:port", "http") == "HTTP"
    assert validate_proxy_options("user:pass@host:port", "HTTPS") == "HTTPS"

    for unsupported in ("SOCKS4", "SOCKS5"):
        with pytest.raises(ValidationError, match="Unsupported proxytype"):
            validate_proxy_options("user:pass@host:port", unsupported)
