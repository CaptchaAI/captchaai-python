# ── What this file IS ─────────────────────────────────────────────────────────
# The synchronous transport: implements request_raw using a reused httpx.Client.
# It exists as the concrete HTTP pipe for the sync client. It contains no captcha
# logic — it only sends a request and normalises the outcome to a UniformResponse.

from __future__ import annotations

import httpx

from .base import BaseTransport, UniformResponse


class SyncTransport(BaseTransport):
    """Synchronous transport backed by a single reused httpx.Client.

    Responsible only for sending one request and returning a UniformResponse.
    The client/session is created once and reused across calls (do not create a
    new client per request — that wastes connections).
    """

    def __init__(self, timeout: float = 30.0) -> None:
        """Create the transport and its reusable HTTP client.

        Parameters:
            timeout: per-request network timeout in seconds.
        """
        # One client for the transport's whole lifetime — connection reuse.
        self._client = httpx.Client(timeout=timeout)

    def request_raw(self, method: str, url: str, data: dict) -> UniformResponse:
        """Send one HTTP request and normalise the result.

        Returns UniformResponse(status_code, body). On ANY exception we return
        UniformResponse(999, None) instead of raising, so the orchestrator is the
        single place that decides what every outcome means.
        """
        try:
            # GET endpoints send fields as query params; POST uses form body.
            # The orchestrator always asks for JSON (json=1), so bodies are parseable.
            if method.upper() == "GET":
                response = self._client.request(method, url, params=data)
            else:
                response = self._client.request(method, url, data=data)
            try:
                # Parse the JSON body into a dict for the orchestrator to read.
                body = response.json()
            except ValueError:
                # Body was not valid JSON — preserve the raw text so the
                # orchestrator can inspect plain-text error codes (e.g. ERROR_UPLOAD).
                return UniformResponse(response.status_code, None, raw_text=response.text)
            return UniformResponse(response.status_code, body)
        except Exception as exc:
            # Any transport-level failure (DNS, connect, timeout, etc.) collapses
            # to the 999 sentinel; the orchestrator maps this to NetworkError.
            return UniformResponse(
                999,
                None,
                transport_error_type=type(exc).__name__,
                transport_error_message=str(exc) or None,
            )

    def close(self) -> None:
        """Close the underlying HTTP client and release its connections."""
        self._client.close()
