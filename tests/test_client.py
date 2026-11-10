"""Integration tests for captchaai.client.CaptchaAI."""

import pytest

from captchaai import CaptchaAI
from captchaai.core.registry import get_entry
from captchaai.exceptions import InvalidKeyError, ThreadLimitError, ValidationError
from tests.conftest import (
    REGISTRY_SOLVE_CASES,
    VALID_API_KEY,
    default_solve_handler,
    make_sync_client,
    threadsinfo_body,
    json_response,
)


def test_init_rejects_short_api_key():
    with pytest.raises(InvalidKeyError, match="Key must be 32 characters"):
        CaptchaAI(api_key="too-short")


def test_init_rejects_proxy_without_proxytype():
    with pytest.raises(ValidationError, match="proxytype is required"):
        CaptchaAI(api_key=VALID_API_KEY, proxy="user:pass@host:port")


def test_init_max_retries_zero_disables_auto_retry():
    handler = default_solve_handler(get_entry("turnstile"))
    client, _ = make_sync_client(handler, max_retries=0)
    assert client._config.auto_retry is False
    client.close()


def test_init_max_retries_positive_sets_cap():
    handler = default_solve_handler(get_entry("turnstile"))
    client, _ = make_sync_client(handler, max_retries=3)
    assert client._config.auto_retry is True
    assert client._config.max_retries == 3
    client.close()


def test_recaptcha_v2_enterprise_flag_selects_registry_row():
    handler = default_solve_handler(get_entry("recaptcha_v2_enterprise"))
    client, transport = make_sync_client(handler)
    result = client.recaptcha_v2(
        sitekey="k",
        url="https://example.com",
        enterprise=True,
    )
    assert result.solution == "solved-token"
    assert result.user_agent == "Mozilla/5.0 Test"
    submit_calls = [c for c in transport.calls if "in.php" in c[1]]
    assert submit_calls[0][2]["method"] == "userrecaptcha"
    assert submit_calls[0][2]["enterprise"] == "1"
    client.close()


def test_recaptcha_v2_invisible_flag():
    handler = default_solve_handler(get_entry("recaptcha_v2_invisible"))
    client, transport = make_sync_client(handler)
    client.recaptcha_v2(
        sitekey="k",
        url="https://example.com",
        invisible=True,
    )
    submit_calls = [c for c in transport.calls if "in.php" in c[1]]
    assert submit_calls[0][2]["invisible"] == "1"
    client.close()


def test_recaptcha_v3_requires_action_at_validation_layer():
    handler = default_solve_handler(get_entry("recaptcha_v3"))
    client, _ = make_sync_client(handler)
    with pytest.raises(ValidationError, match="action"):
        client.recaptcha_v3(sitekey="k", url="https://example.com")
    client.close()


def test_per_call_proxy_override_without_mutating_config(no_sleep):
    handler = default_solve_handler(get_entry("turnstile"))
    client, transport = make_sync_client(handler)
    client.recaptcha_v2(
        sitekey="k",
        url="https://example.com",
        proxy="user:pass@other:port",
        proxytype="HTTPS",
    )
    submit_calls = [c for c in transport.calls if "in.php" in c[1]]
    assert submit_calls[0][2]["proxy"] == "user:pass@other:port"
    assert submit_calls[0][2]["proxytype"] == "HTTPS"
    assert client._config.proxy is None
    client.close()


@pytest.mark.parametrize("bad_proxytype", ["SOCKS4", "SOCKS5", "FTP"])
def test_init_rejects_unsupported_proxytype(bad_proxytype: str):
    with pytest.raises(ValidationError, match="Unsupported proxytype"):
        CaptchaAI(
            api_key=VALID_API_KEY,
            proxy="user:pass@host:port",
            proxytype=bad_proxytype,
        )


def test_per_call_proxy_without_proxytype_raises():
    handler = default_solve_handler(get_entry("turnstile"))
    client, _ = make_sync_client(handler)
    with pytest.raises(ValidationError, match="proxytype is required"):
        client.recaptcha_v2(
            sitekey="k",
            url="https://example.com",
            proxy="user:pass@host:port",
        )
    client.close()


def test_mandatory_proxy_types_raise_without_proxy():
    handler = default_solve_handler(get_entry("cloudflare_challenge"))
    client, _ = make_sync_client(handler)
    with pytest.raises(ValidationError, match="proxy and proxytype are required"):
        client.cloudflare_challenge(url="https://example.com")
    client.close()


@pytest.mark.parametrize("case", REGISTRY_SOLVE_CASES, ids=lambda c: c["registry_name"])
def test_solve_each_registry_type(case, no_sleep):
    entry = get_entry(case["registry_name"])
    handler = default_solve_handler(entry)
    proxy_cfg = case.get("proxy") or {}
    client, _ = make_sync_client(handler, **{k: v for k, v in proxy_cfg.items() if k == "proxy" or k == "proxytype"})
    method = getattr(client, case["method"])
    kwargs = dict(case["kwargs"])
    if case.get("proxy") and "proxy" not in kwargs:
        kwargs.update(case["proxy"])
    result = method(**kwargs)
    assert result.task_id == "12345"
    if entry.is_structured:
        assert result.solution is not None
    else:
        assert result.solution == "solved-token"
    if entry.returns_user_agent:
        assert result.user_agent == "Mozilla/5.0 Test"
    client.close()


def test_threads_info():
    def handler(method, url, data):
        return json_response(threadsinfo_body(10, 3))

    client, _ = make_sync_client(handler)
    info = client.threads_info()
    assert info == {"threads": 10, "working_threads": 3}
    client.close()


def test_send_and_get_result(no_sleep):
    entry = get_entry("recaptcha_v2")
    handler = default_solve_handler(entry)
    client, _ = make_sync_client(handler)
    task_id = client.send(
        "recaptcha_v2",
        googlekey="k",
        pageurl="https://example.com",
    )
    assert task_id == "12345"
    result = client.get_result("recaptcha_v2", task_id)
    assert result.solution == "solved-token"
    client.close()


def test_close_closes_transport():
    handler = default_solve_handler(get_entry("turnstile"))
    client, transport = make_sync_client(handler)
    client.close()
    assert transport.closed is True
