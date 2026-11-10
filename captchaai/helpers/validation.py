# ── What this file IS ─────────────────────────────────────────────────────────
# The input validator: checks the caller supplied every required param BEFORE any
# HTTP call is made. It exists to catch bad input early so we never waste an API
# call (and a thread) on a request the API would just reject.

from __future__ import annotations

from ..core.registry import CaptchaTypeEntry
from ..exceptions import ValidationError

SUPPORTED_PROXY_TYPES: tuple[str, ...] = ("HTTP", "HTTPS")


def validate_proxy_options(proxy: str | None, proxytype: str | None) -> str | None:
    """Validate optional proxy + proxytype pairing and supported protocol.

    Returns the normalized uppercase proxytype ("HTTP" or "HTTPS") or None.
    """
    if proxy and not proxytype:
        raise ValidationError("proxytype is required when proxy is set")
    if proxytype is None:
        return None
    normalized = proxytype.strip().upper() if isinstance(proxytype, str) else ""
    if not normalized:
        if proxy:
            raise ValidationError("proxytype is required when proxy is set")
        return None
    if normalized not in SUPPORTED_PROXY_TYPES:
        supported = ", ".join(SUPPORTED_PROXY_TYPES)
        raise ValidationError(
            f"Unsupported proxytype {proxytype!r}; supported values are: {supported}"
        )
    return normalized


def validate(params: dict, entry: CaptchaTypeEntry) -> None:
    """Ensure every required param for this type is present and non-empty.

    Parameters:
        params: the params dict the client built (keyed by API param names).
        entry: the registry row whose `required_params` declares what is needed.

    Raises:
        ValidationError: if any required param is missing, None, or empty — with a
        clear message listing exactly what is wrong. Runs FIRST, before any request.
    """
    # A param fails if it is absent, None, or an empty/whitespace-only string.
    missing = [
        name
        for name in entry.required_params
        if params.get(name) is None
        or (isinstance(params.get(name), str) and not params[name].strip())
    ]
    if missing:
        raise ValidationError(
            f"{entry.name}: missing required parameter(s): {', '.join(missing)}"
        )

    for param_name, allowed in entry.valid_values.items():
        value = params.get(param_name)
        if value is not None and str(value) not in allowed:
            raise ValidationError(
                f"{entry.name}: '{param_name}' must be one of "
                f"{list(allowed)}, got {value!r}"
            )
