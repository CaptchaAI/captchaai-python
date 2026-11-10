"""Tests for get_balance() and supported_types() additions in the SDK."""

from __future__ import annotations

import pytest

from captchaai import APIError, InvalidKeyError, supported_types
from captchaai.core.registry import REGISTRY
from tests.conftest import (
    json_response,
    make_async_client,
    make_sync_client,
    threadsinfo_body,
)


def _balance_handler(balance_body: dict):
    def handler(method: str, url: str, data: dict):
        if "res.php" in url and data.get("action") == "threadsinfo":
            return json_response(threadsinfo_body())
        if "res.php" in url and data.get("action") == "getbalance":
            return json_response(balance_body)
        return json_response({"status": 0, "request": "UNEXPECTED_CALL"})

    return handler


@pytest.mark.parametrize("raw_balance", ["12.34", "0", "unlimited"])
def test_sync_get_balance_returns_raw_string(raw_balance: str) -> None:
    client, transport = make_sync_client(_balance_handler({"status": 1, "request": raw_balance}))
    try:
        assert client.get_balance() == raw_balance
        balance_call = [c for c in transport.calls if c[2].get("action") == "getbalance"]
        assert len(balance_call) == 1
        method, url, data = balance_call[0]
        assert method == "POST"
        assert url.endswith("/res.php")
        assert data["json"] == 1
    finally:
        client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("raw_balance", ["12.34", "unlimited"])
async def test_async_get_balance_returns_raw_string(raw_balance: str) -> None:
    client, transport = await make_async_client(
        _balance_handler({"status": 1, "request": raw_balance})
    )
    try:
        assert await client.get_balance() == raw_balance
        balance_call = [c for c in transport.calls if c[2].get("action") == "getbalance"]
        assert len(balance_call) == 1
        assert balance_call[0][0] == "POST"
        assert balance_call[0][1].endswith("/res.php")
    finally:
        await client.aclose()


def test_get_balance_invalid_key_raises_invalid_key_error() -> None:
    client, _ = make_sync_client(
        _balance_handler({"status": 0, "request": "ERROR_KEY_DOES_NOT_EXIST"})
    )
    try:
        with pytest.raises(InvalidKeyError):
            client.get_balance()
    finally:
        client.close()


@pytest.mark.parametrize(
    "bad_body",
    [
        {"status": 0, "request": "ERROR_INTERNAL_SERVER_ERROR"},
        {"status": 1, "request": ""},
        {"status": 1, "request": None},
    ],
)
def test_get_balance_failure_or_empty_raises_api_error(bad_body: dict) -> None:
    client, _ = make_sync_client(_balance_handler(bad_body))
    try:
        with pytest.raises(APIError):
            client.get_balance()
    finally:
        client.close()


def test_supported_types_covers_registry_and_returns_copies() -> None:
    summary = supported_types()
    assert set(summary.keys()) == set(REGISTRY.keys())
    assert len(summary) == 14

    summary["recaptcha_v2"]["required_params"].append("mutated")
    assert "mutated" not in REGISTRY["recaptcha_v2"].required_params
