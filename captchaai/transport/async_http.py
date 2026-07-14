# ── What this file IS ─────────────────────────────────────────────────────────
# The asynchronous transport: implements request_raw using a reused
# httpx.AsyncClient. It is the async twin of sync_http.py and the ONLY async-
# specific piece of the transport layer. It contains no captcha logic — it just
# sends a request and normalises the outcome to a UniformResponse, awaited.

from __future__ import annotations

import httpx

from .base import BaseTransport, UniformResponse


class AsyncTransport(BaseTransport):
    """Asynchronous transport backed by a single reused httpx.AsyncClient.

    Implements the same request_raw contract as the sync transport, but as a
    coroutine. The driver in the async client awaits it. The client/session is
    created once and reused across calls.
    """

    def __init__(self, timeout: float = 30.0) -> None:
        """Create the transport and its reusable async HTTP client.

        Parameters:
            timeout: per-request network timeout in seconds.
        """
        # One async client for the transport's whole lifetime — connection reuse.
        self._client = httpx.AsyncClient(timeout=timeout)

    async def request_raw(self, method: str, url: str, data: dict) -> UniformResponse:  # type: ignore[override]
        """Send one HTTP request asynchronously and normalise the result.

        Returns UniformResponse(status_code, body). On ANY exception we return
        UniformResponse(999, None) instead of raising — identical contract to the
        sync transport, so the shared engine handles every outcome the same way.
        """
        try:
            # GET endpoints send fields as query params; POST uses form body.
            if method.upper() == "GET":
                response = await self._client.request(method, url, params=data)
            else:
                response = await self._client.request(method, url, data=data)
            try:
                # Parse the JSON body into a dict for the engine to read.
                body = response.json()
            except ValueError:
                # Not valid JSON — preserve the raw text so the orchestrator can
                # inspect plain-text error codes (e.g. ERROR_UPLOAD).
                return UniformResponse(response.status_code, None, raw_text=response.text)
            return UniformResponse(response.status_code, body)
        except Exception as exc:
            # Any transport-level failure collapses to the 999 sentinel.
            return UniformResponse(
                999,
                None,
                transport_error_type=type(exc).__name__,
                transport_error_message=str(exc) or None,
            )

    async def aclose(self) -> None:
        """Close the underlying async HTTP client and release its connections."""
        await self._client.aclose()
