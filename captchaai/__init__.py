# ── What this package IS ──────────────────────────────────────────────────────
# The CaptchaAI Python SDK public package.
# This is the single import surface for users: the sync and async clients, the one
# result type, and the full exception hierarchy.

from .async_client import AsyncCaptchaAI
from .client import CaptchaAI
from .core.registry import supported_types
from .core.result import SolveResult
from .helpers.validation import SUPPORTED_PROXY_TYPES
from .exceptions import (
    APIError,
    CaptchaAIError,
    InvalidKeyError,
    NetworkError,
    NoThreadsError,
    ProxyError,
    ThreadLimitError,
    TimeoutError,
    UnsolvableError,
    ValidationError,
)

__all__ = [
    "CaptchaAI",
    "AsyncCaptchaAI",
    "SolveResult",
    "supported_types",
    "SUPPORTED_PROXY_TYPES",
    "CaptchaAIError",
    "InvalidKeyError",
    "ValidationError",
    "ProxyError",
    "ThreadLimitError",
    "NoThreadsError",
    "UnsolvableError",
    "APIError",
    "NetworkError",
    "TimeoutError",
]
