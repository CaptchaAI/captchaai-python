"""Tests for helpers/extract.py and SolveResult."""

import pytest

from captchaai.core.registry import get_entry
from captchaai.core.result import SolveResult
from captchaai.exceptions import APIError
from captchaai.helpers.extract import build_result


def test_build_result_token_type():
    entry = get_entry("turnstile")
    result = build_result(
        {"status": 1, "request": "token-abc"},
        entry,
        task_id="99",
    )
    assert result.task_id == "99"
    assert result.solution == "token-abc"
    assert result.user_agent is None
    assert result.raw_text == "token-abc"
    assert str(result) == "token-abc"


def test_build_result_structured_list():
    entry = get_entry("grid")
    result = build_result(
        {"status": 1, "request": "[0, 3, 7]"},
        entry,
        task_id="1",
    )
    assert result.solution == [0, 3, 7]
    assert str(result) == "[0, 3, 7]"


def test_build_result_structured_dict():
    entry = get_entry("geetest")
    result = build_result(
        {
            "status": 1,
            "request": '{"challenge":"c","validate":"v","seccode":"s"}',
        },
        entry,
        task_id="1",
    )
    assert result.solution == {"challenge": "c", "validate": "v", "seccode": "s"}


def test_build_result_extracts_user_agent():
    entry = get_entry("recaptcha_v2_enterprise")
    result = build_result(
        {"status": 1, "result": "ent-token", "user_agent": "UA/1.0"},
        entry,
        task_id="1",
    )
    assert result.solution == "ent-token"
    assert result.user_agent == "UA/1.0"


def test_build_result_missing_solution_key_raises():
    entry = get_entry("turnstile")
    with pytest.raises(APIError, match="missing 'request' field"):
        build_result({"status": 1}, entry, task_id="1")


def test_build_result_invalid_json_raises():
    entry = get_entry("grid")
    with pytest.raises(APIError, match="Could not parse structured answer"):
        build_result({"status": 1, "request": "not-json"}, entry, task_id="1")
