# ── What this file IS ─────────────────────────────────────────────────────────
# The transport contract: the single abstract method every transport implements
# and the uniform response shape every transport returns.
# It exists so the orchestrator can talk to "some transport" without caring whether
# it is sync or async, or which HTTP library sits underneath.

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import NamedTuple


class UniformResponse(NamedTuple):
    """The one response shape every transport returns, success or failure.

    Fields:
        status_code: HTTP status code, or a sentinel (999) the transport uses to
            signal a connection-level failure so the orchestrator handles it uniformly.
        body: the parsed JSON response as a dict, or None when there is no usable body.
        raw_text: the raw response text when JSON parsing fails, or None otherwise.
            Preserved so the orchestrator can inspect plain-text error codes (e.g.
            ERROR_UPLOAD) that the API occasionally returns instead of JSON.
        transport_error_type: exception class name for transport-level failures.
        transport_error_message: exception text for transport-level failures.
    """

    status_code: int  # real HTTP code, or 999 sentinel for transport-level failure
    body: dict | None  # parsed JSON body, or None when nothing usable came back
    raw_text: str | None = None  # plain-text body when JSON parsing fails
    transport_error_type: str | None = None
    transport_error_message: str | None = None


class BaseTransport(ABC):
    """Abstract transport — defines the only method a transport must implement.

    A transport is a dumb HTTP pipe: it sends one request and returns one
    UniformResponse. It knows nothing about captchas, retries, or polling.
    Concrete transports (sync/async) differ ONLY in how request_raw is implemented.
    """

    @abstractmethod
    def request_raw(self, method: str, url: str, data: dict) -> UniformResponse:
        """Send one HTTP request and return a UniformResponse.

        Parameters:
            method: HTTP verb, e.g. "POST".
            url: full URL to hit (base_url + endpoint).
            data: form fields for POST body, or query params for GET requests.

        Returns:
            UniformResponse(status_code, body). On any exception the transport
            must return UniformResponse(999, None) instead of raising, so the
            orchestrator owns all error handling.
        """
        raise NotImplementedError
