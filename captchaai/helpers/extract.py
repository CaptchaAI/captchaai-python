# ── What this file IS ─────────────────────────────────────────────────────────
# The answer extractor: turns a successful API response into a SolveResult.
# It exists so every type returns the same object shape, and so the "where is the
# answer?" logic lives in exactly one place driven by the registry row.

from __future__ import annotations

import json

from ..core.registry import CaptchaTypeEntry
from ..core.result import SolveResult
from ..exceptions import APIError


def build_result(response: dict, entry: CaptchaTypeEntry, task_id: str) -> SolveResult:
    """Build a SolveResult from a solved API response.

    Reads `entry.solution_key` ("request" or "result") to find the answer, then
    shapes it per the registry row:
        - is_structured=True  → parse the answer string as JSON (dict or list)
        - returns_user_agent=True → also pull `user_agent` from the response

    Parameters:
        response: the full API response dict (status already known to be success).
        entry: the registry row describing how to read this type's answer.
        task_id: the task ID from the original submit.

    Returns:
        A populated SolveResult.

    Raises:
        APIError: if the solution field is absent, or structured parsing fails.
    """
    # The answer lives under the registry's solution_key ("request" or "result").
    answer = response.get(entry.solution_key)
    if answer is None:
        raise APIError(f"API response missing '{entry.solution_key}' field")

    # Capture the raw string before any JSON parsing so callers can read plain text.
    raw_text: str | None = answer if isinstance(answer, str) else None

    if entry.is_structured:
        # Structured types: JSON string → dict (Geetest) or list (grid/bls).
        if isinstance(answer, str):
            try:
                solution: str | list | dict = json.loads(answer)
            except json.JSONDecodeError as exc:
                raise APIError(f"Could not parse structured answer as JSON: {exc}")
        else:
            # Already a dict/list (some responses pre-parse it) — use as-is.
            solution = answer
    else:
        # Token types: the answer is the token string itself.
        solution = answer

    # Enterprise / Cloudflare types return a user_agent that MUST be reused.
    user_agent = response.get("user_agent") if entry.returns_user_agent else None

    return SolveResult(
        task_id=task_id,
        solution=solution,
        user_agent=user_agent,
        raw=response,
        raw_text=raw_text,
    )
