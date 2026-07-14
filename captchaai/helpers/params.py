# ── What this file IS ─────────────────────────────────────────────────────────
# The param normaliser: turns the SDK's params dict into the exact wire form the
# API expects. It exists so the orchestrator hands the transport clean, stringy
# form fields — no None values, no Python bools, no SDK-only key names.

from __future__ import annotations

# ── SDK-name → API-name map ───────────────────────────────────────────────────
# Required params are already built with API names by the client, so this map only
# covers optional SDK conveniences. It is the single place such renames live.
_RENAME = {
    "url": "pageurl",           # allow callers/tests that pass `url` instead of `pageurl`
    "user_agent": "userAgent",  # Python snake_case → API camelCase
    "api_server": "apiServer",  # Lemin: optional API server override
}


def normalise(params: dict) -> dict:
    """Convert an SDK params dict into API-ready form fields.

    Steps:
        - drop any param whose value is None (optional params left unset)
        - rename SDK-only keys to their API names via `_RENAME`
        - convert Python bools to "1"/"0" (the API speaks strings, not JSON bools)
        - stringify every remaining value for form encoding

    Parameters:
        params: the SDK params dict (post-validation, post-image-resolve).

    Returns:
        A new dict of API-named string fields ready for the transport.
    """
    out: dict = {}
    for key, value in params.items():
        # Skip unset optionals entirely so they are simply not sent.
        if value is None:
            continue
        api_key = _RENAME.get(key, key)
        if isinstance(value, bool):
            # Booleans become "1"/"0" — the API has no notion of JSON booleans.
            out[api_key] = "1" if value else "0"
        else:
            # Everything else is sent as a string form field.
            out[api_key] = str(value)
    return out
