"""Integration tests for captchaai.async_client.AsyncCaptchaAI."""

import pytest

from captchaai import AsyncCaptchaAI
from captchaai.core.registry import get_entry
from captchaai.exceptions import ThreadLimitError, ValidationError
from tests.conftest import (
    REGISTRY_SOLVE_CASES,
    VALID_API_KEY,
    default_solve_handler,
    json_response,
    make_async_client,
    threadsinfo_body,
)


def test_direct_instantiation_blocked():
    with pytest.raises(TypeError, match="cannot be instantiated directly"):
        AsyncCaptchaAI(api_key=VALID_API_KEY)


@pytest.mark.asyncio
async def test_create_rejects_proxy_without_proxytype():
    with pytest.raises(ValidationError, match="proxytype is required"):
        await AsyncCaptchaAI.create(api_key=VALID_API_KEY, proxy="user:pass@host:port")


@pytest.mark.asyncio
async def test_recaptcha_v3_requires_action():
    handler = default_solve_handler(get_entry("recaptcha_v3"))
    client, _ = await make_async_client(handler)
    with pytest.raises(ValidationError, match="action"):
        await client.recaptcha_v3(sitekey="k", url="https://example.com")
    await client.aclose()


@pytest.mark.parametrize("case", REGISTRY_SOLVE_CASES, ids=lambda c: c["registry_name"])
@pytest.mark.asyncio
async def test_async_solve_each_registry_type(case, no_sleep):
    entry = get_entry(case["registry_name"])
    handler = default_solve_handler(entry)
    proxy_cfg = case.get("proxy") or {}
    client, _ = await make_async_client(
        handler,
        **{k: v for k, v in proxy_cfg.items() if k in ("proxy", "proxytype")},
    )
    method = getattr(client, case["method"])
    kwargs = dict(case["kwargs"])
    if case.get("proxy") and "proxy" not in kwargs:
        kwargs.update(case["proxy"])
    result = await method(**kwargs)
    assert result.task_id == "12345"
    if entry.returns_user_agent:
        assert result.user_agent == "Mozilla/5.0 Test"
    else:
        assert result.solution is not None
    await client.aclose()


@pytest.mark.asyncio
async def test_threads_info(no_sleep):
    def handler(method, url, data):
        return json_response(threadsinfo_body(8, 1))

    client, _ = await make_async_client(handler)
    info = await client.threads_info()
    assert info == {"threads": 8, "working_threads": 1}
    await client.aclose()


@pytest.mark.asyncio
async def test_send_and_get_result(no_sleep):
    entry = get_entry("turnstile")
    handler = default_solve_handler(entry)
    client, _ = await make_async_client(handler)
    task_id = await client.send(
        "turnstile",
        sitekey="k",
        pageurl="https://example.com",
    )
    assert task_id == "12345"
    result = await client.get_result("turnstile", task_id)
    assert result.solution == "solved-token"
    await client.aclose()


@pytest.mark.asyncio
async def test_async_context_manager_closes_transport(no_sleep):
    handler = default_solve_handler(get_entry("turnstile"))
    client, transport = await make_async_client(handler)
    async with client:
        pass
    assert transport.closed is True
