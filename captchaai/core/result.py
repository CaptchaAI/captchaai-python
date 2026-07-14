# ── What this file IS ─────────────────────────────────────────────────────────
# The SolveResult dataclass: the single return type for every solve.
# It exists so callers always get the same shape back no matter the captcha type,
# instead of guessing which response key holds the answer.

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SolveResult:
    """The one object returned by every solve, regardless of captcha type.

    Fields:
        task_id: task ID returned by in.php — always present.
        solution: the answer. A token string for most types; a list of cell
            indices for grid/BLS types; a dict {challenge, validate, seccode}
            for Geetest.
        user_agent: the solver's User-Agent — only for Enterprise and Cloudflare
            types, where it MUST be reused when submitting the token. None otherwise.
        raw: the full API response dict, for debugging.
        raw_text: the unparsed solution string exactly as returned by the API,
            before any JSON parsing. Useful when you need the plain-text token
            without going through the structured solution field.
    """

    task_id: str  # always present — from the in.php submit
    solution: str | list | dict  # token, cell-index list, or structured dict
    user_agent: str | None = None  # only for Enterprise / Cloudflare types
    raw: dict | None = None  # full API response, for debugging
    raw_text: str | None = None  # unparsed solution string from the API

    def __str__(self) -> str:
        """Return the answer as a string for the common case.

        For token types this returns the token directly, so `str(result)` is the
        token. For structured types (list/dict) it returns a string representation.
        """
        if isinstance(self.solution, (dict, list)):
            return str(self.solution)
        # Token types: the solution already IS the string the caller wants.
        return self.solution
