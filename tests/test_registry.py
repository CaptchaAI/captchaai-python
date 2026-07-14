"""Tests for core/registry.py."""

import pytest

from captchaai.core.registry import REGISTRY, get_entry
from captchaai.exceptions import ValidationError

EXPECTED_REGISTRY_KEYS = {
    "normal",
    "grid",
    "bls",
    "recaptcha_v2",
    "recaptcha_v2_invisible",
    "recaptcha_v2_enterprise",
    "recaptcha_v3",
    "recaptcha_v3_enterprise",
    "turnstile",
    "cloudflare_challenge",
    "geetest",
    "captchafox",
    "friendly_captcha",
    "lemin",
}


def test_registry_contains_all_fourteen_types():
    assert set(REGISTRY.keys()) == EXPECTED_REGISTRY_KEYS


@pytest.mark.parametrize("name", sorted(EXPECTED_REGISTRY_KEYS))
def test_registry_entry_has_required_fields(name):
    entry = REGISTRY[name]
    assert entry.name == name
    assert entry.api_method
    assert isinstance(entry.required_params, tuple)
    assert entry.submit_http_method in ("GET", "POST")
    assert entry.solution_key in ("request", "result")
    assert entry.initial_wait >= 0
    assert entry.poll_interval > 0


def test_proxy_required_types():
    assert REGISTRY["cloudflare_challenge"].requires_proxy is True
    assert REGISTRY["captchafox"].requires_proxy is True
    assert REGISTRY["turnstile"].requires_proxy is False


def test_grid_valid_values():
    entry = REGISTRY["grid"]
    assert entry.valid_values["grid_size"] == ("3x3", "4x4")


def test_get_entry_returns_row():
    entry = get_entry("turnstile")
    assert entry.api_method == "turnstile"
    assert entry.required_params == ("sitekey", "pageurl")


def test_get_entry_unknown_raises_validation_error():
    with pytest.raises(ValidationError, match="Unknown captcha type"):
        get_entry("not_a_real_type")
