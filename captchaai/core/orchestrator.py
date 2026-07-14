# ── What this file IS ─────────────────────────────────────────────────────────
# The orchestrator: the single engine that runs every solve from start to finish.
# It exists so ALL business logic (validate, submit, wait, poll, retry, error
# mapping, thread model) is written exactly once and shared by both the sync and
# async clients.
#
# How sync/async sharing works (the "sans-IO" pattern):
#   The engine is written as GENERATORS that never touch the network or the clock
#   themselves. Instead they YIELD small "effect" objects:
#       - ApiCall(method, url, data) → "please send this request"
#       - Sleep(seconds)             → "please wait this long"
#   A tiny driver in each client runs the generator: it performs the effect (sync
#   or async) and sends the outcome back in. The generator holds every decision;
#   the driver holds only the transport difference. Zero logic is duplicated.

from __future__ import annotations

from dataclasses import dataclass
from typing import Generator

from ..exceptions import (
    APIError,
    InvalidKeyError,
    NetworkError,
    NoThreadsError,
    ProxyError,
    ThreadLimitError,
    TimeoutError,
    UnsolvableError,
    ValidationError,
)
from ..helpers import extract, image, params as params_helper, retry, validation
from .config import Config
from .registry import CaptchaTypeEntry

# ── Effects: the only things the engine asks the driver to perform ─────────────
@dataclass(frozen=True)
class ApiCall:
    """Effect: send one HTTP request and send back a UniformResponse."""

    method: str  # HTTP verb — "GET" or "POST" per endpoint/type (from registry or fixed)
    url: str  # full URL (base_url + endpoint), built by the engine
    data: dict  # form fields to send


@dataclass(frozen=True)
class Sleep:
    """Effect: wait `seconds`, then send back None."""

    seconds: float


# The return type of every engine generator: it yields effects (ApiCall | Sleep),
# receives whatever the driver sends back, and finally returns a value.
Effect = ApiCall | Sleep


# ── Sentinel the transport uses for connection-level failure ───────────────────
_NETWORK_FAIL = 999


# ── Error code maps ────────────────────────────────────────────────────────────
# Submit (in.php) errors that ALWAYS raise immediately, regardless of auto_retry.
# Each maps an API error code to (exception class, human message).
_SUBMIT_FATAL: dict[str, tuple[type[Exception], str]] = {
    "ERROR_WRONG_USER_KEY": (InvalidKeyError, "Key must be 32 characters"),
    "ERROR_KEY_DOES_NOT_EXIST": (InvalidKeyError, "Key not found — check your dashboard"),
    "ERROR_BAD_PARAMETERS": (ValidationError, "Required parameters missing or malformed"),
    "ERROR_PAGEURL": (ValidationError, "pageurl is missing or invalid"),
    "ERROR_GOOGLEKEY": (ValidationError, "googlekey/sitekey is missing"),
    "ERROR_WRONG_GOOGLEKEY": (ValidationError, "googlekey is malformed"),
    "ERROR_TOO_BIG_CAPTCHA_FILESIZE": (ValidationError, "Image is too large"),
    "ERROR_ZERO_CAPTCHA_FILESIZE": (ValidationError, "Image is too small (under 100 bytes)"),
    "ERROR_IMAGE_DIMENSIONS_TOO_LARGE": (ValidationError, "Image dimensions are too large"),
    "ERROR_WRONG_FILE_EXTENSION": (ValidationError, "Unsupported image file extension"),
    "ERROR_IMAGE_TYPE_NOT_SUPPORTED": (ValidationError, "Unsupported image type"),
    "ERROR_UPLOAD": (ValidationError, "Bad image upload (multipart/base64)"),
    "ERROR_BAD_TOKEN_OR_PAGEURL": (ValidationError, "Wrong sitekey + pageurl pair"),
    "ERROR_BAD_PROXY": (ProxyError, "Proxy was marked bad"),
    "IP_BANNED": (APIError, "IP banned — too many bad auth attempts"),
}

# Submit errors that MAY retry (respecting auto_retry). Maps code to the
# exception raised when retries are exhausted or auto_retry=False.
_SUBMIT_RETRYABLE: dict[str, tuple[type[Exception], str]] = {
    "ERROR_SERVER_ERROR": (APIError, "Transient server error"),
    "ERROR_INTERNAL_SERVER_ERROR": (APIError, "Internal server error"),
    "ERROR_PROXY_CONNECTION_FAILED": (ProxyError, "Proxy connection failed"),
}

# Poll (res.php) errors that ALWAYS raise immediately.
_POLL_FATAL: dict[str, tuple[type[Exception], str]] = {
    "ERROR_CAPTCHA_UNSOLVABLE": (UnsolvableError, "Captcha could not be solved"),
    "ERROR_WRONG_USER_KEY": (InvalidKeyError, "Key must be 32 characters"),
    "ERROR_KEY_DOES_NOT_EXIST": (InvalidKeyError, "Key not found — check your dashboard"),
    "ERROR_WRONG_ID_FORMAT": (APIError, "Task ID not numeric (likely an SDK bug)"),
    "ERROR_WRONG_CAPTCHA_ID": (APIError, "Task ID not found"),
    "ERROR_EMPTY_ACTION": (APIError, "Missing action parameter (likely an SDK bug)"),
}


# ── Small shared helpers ───────────────────────────────────────────────────────
def build_endpoint_url(config: Config, path: str) -> str:
    """Build a full endpoint URL from the configured base_url and a path."""
    return f"{config.base_url.rstrip('/')}/{path}"


def _build_friendly_network_message(resp) -> str:
    """Build a user-friendly network error message from transport metadata."""
    error_type = (getattr(resp, "transport_error_type", "") or "").lower()
    error_message = (getattr(resp, "transport_error_message", "") or "").lower()
    details = " ".join(part for part in (error_type, error_message) if part)

    if "timeout" in details or "timed out" in details:
        return "Network timeout contacting the CaptchaAI API. Check your connection and try again."
    if any(
        marker in details
        for marker in ("name or service not known", "nodename nor servname", "gaierror", "dns")
    ):
        return "Could not resolve the CaptchaAI host. Check DNS settings or base_url."
    if any(
        marker in details
        for marker in ("connection refused", "connection reset", "connecterror", "network is unreachable")
    ):
        return "Connection to the CaptchaAI API failed. The service may be blocked, offline, or unreachable."
    return "Network disconnected while contacting the CaptchaAI API. Check internet access and try again."


def get_body_or_raise(resp) -> dict:
    """Turn a UniformResponse into a usable body dict, or raise.

    Handles the two transport-level failures uniformly:
        - status 999 (sentinel) → NetworkError (could not reach the API)
        - body is None, raw_text is a known error code → mapped exception
        - body is None, raw_text unknown or absent    → APIError (malformed)
    """
    if resp.status_code == _NETWORK_FAIL:
        raise NetworkError(_build_friendly_network_message(resp))
    if resp.body is None:
        # The API occasionally returns plain-text error codes instead of JSON
        # (e.g. ERROR_UPLOAD when the image body is invalid). Check the raw text
        # against the known fatal-error map so callers get a meaningful exception
        # instead of the generic "Malformed API response" message.
        raw = (resp.raw_text or "").strip()
        if raw in _SUBMIT_FATAL:
            exc, message = _SUBMIT_FATAL[raw]
            raise exc(message)
        raise APIError(f"Malformed API response (HTTP {resp.status_code})")
    return resp.body


def read_status_and_request(body: dict) -> tuple[int, str]:
    """Pull the API's (status, request) pair from a JSON body.

    status==1 means success and `request` holds the answer/task-id; status==0
    means failure and `request` holds the error code.
    """
    return int(body.get("status", 0)), str(body.get("request", ""))


def raise_if_key_invalid(body: dict) -> None:
    """Raise InvalidKeyError if a body reports a key problem (used by utilities)."""
    status, request = read_status_and_request(body)
    if status == 0:
        if request == "ERROR_WRONG_USER_KEY":
            raise InvalidKeyError("Key must be 32 characters")
        if request == "ERROR_KEY_DOES_NOT_EXIST":
            raise InvalidKeyError("Key not found — check your dashboard")


def read_thread_counts(body: dict) -> dict:
    """Read thread counts from a threadsinfo response into ints.

    Returns {"threads": int, "working_threads": int}. Raises APIError if the
    expected fields are absent or non-numeric.
    """
    try:
        return {
            "threads": int(body["threads"]),
            "working_threads": int(body["working_threads"]),
        }
    except (KeyError, TypeError, ValueError):
        raise APIError("threadsinfo response missing thread counts")


# ── Public engine generators ───────────────────────────────────────────────────
def get_thread_usage(config: Config) -> Generator[Effect, object, dict]:
    """Ask the API how many threads exist and how many are in use.

    Also doubles as the startup key check: the same single call both proves the key
    is valid (raises InvalidKeyError if not) and learns the thread cap.
    Returns {"threads": int, "working_threads": int}.
    """
    resp = yield ApiCall(
        "POST",
        build_endpoint_url(config, "res.php"),
        {"key": config.api_key, "action": "threadsinfo", "json": 1},
    )
    body = get_body_or_raise(resp)
    raise_if_key_invalid(body)  # bad/unknown key → InvalidKeyError, before anything else
    return read_thread_counts(body)

def submit_task(
    config: Config, entry: CaptchaTypeEntry, params: dict
) -> Generator[Effect, object, str]:
    """Check the inputs, build the request, send the task, and return its task_id.

    Runs in a strict order: validate FIRST → resolve image (if any) → normalise
    names → attach proxy → submit, retrying transient failures (bounded) and
    handling a hit thread cap. The returned task_id is then used to poll for the answer.
    """
    # 1. Validation runs FIRST — bad input fails before any HTTP call is made.
    validation.validate(params, entry)

    # 1b. Types that require a proxy (e.g. Cloudflare Challenge) fail fast here.
    if entry.requires_proxy and (not config.proxy or not config.proxytype):
        raise ValidationError(
            f"{entry.name}: proxy and proxytype are required for this captcha type"
        )

    # Inconsistent proxy config: proxytype given but no proxy address to attach it to.
    if config.proxytype and not config.proxy:
        raise ValidationError(
            "proxytype is set but proxy is missing — "
            "provide both proxy and proxytype or neither"
        )

    # 2. Image resolver runs only for image types (path/URL/base64 → body).
    if entry.has_image:
        image.resolve(params, entry)

    # 3. Normalise SDK params into API-ready string form fields.
    data = params_helper.normalise(params)

    # 4. Base submit fields: key, method, and JSON output so bodies are parseable.
    data["key"] = config.api_key
    data["method"] = entry.api_method
    data["json"] = 1

    # 4b. Attach the proxy if one is configured (set once, applied every solve).
    if config.proxy:
        data["proxy"] = config.proxy
        data["proxytype"] = config.proxytype

    url = build_endpoint_url(config, "in.php")
    # Exponential backoff for transient submit failures, with jitter.
    backoff = retry.exponential(config.submit_backoff_base, config.jitter_max)
    # Thread-busy backoff: ~8s intervals, independent from server-error retries.
    busy_backoff = retry.thread_busy_backoff()
    # Logical seconds already spent waiting for a thread slot to free up.
    # Advances by each sleep duration so the deadline check is sans-IO (no
    # time.monotonic() call needed — works correctly with the no_sleep test fixture).
    busy_waited = 0.0
    attempts = 0  # counts only transient server/proxy error retries

    # Proactive thread check for auto_retry=False. The CaptchaAI API queues tasks
    # silently when all threads are busy — it never returns ERROR_ZERO_BALANCE, so
    # the reactive branch below is unreachable in production. When auto_retry=False
    # the caller has opted out of SDK retries and expects an immediate exception.
    # We check once before submitting: if all slots are taken, raise now rather than
    # letting the task queue invisibly and block indefinitely.
    if not config.auto_retry:
        resp = yield ApiCall(
            "POST",
            build_endpoint_url(config, "res.php"),
            {"key": config.api_key, "action": "threadsinfo", "json": 1},
        )
        body = get_body_or_raise(resp)
        counts = read_thread_counts(body)
        if counts["working_threads"] >= counts["threads"]:
            raise ThreadLimitError("All account threads are busy")
        

    while True:
        resp = yield ApiCall(entry.submit_http_method, url, data)
        body = get_body_or_raise(resp)
        status, request = read_status_and_request(body)

        # Success: `request` is the task id.
        if status == 1:
            return request

        code = request  # status==0 → request carries the error code

        # Always-fatal submit errors: raise immediately, regardless of auto_retry.
        if code in _SUBMIT_FATAL:
            exc, message = _SUBMIT_FATAL[code]
            raise exc(message)

        # Thread cap hit: diagnose via threadsinfo, then retry or raise.
        if code == "ERROR_ZERO_BALANCE":
            # Sub-engine decides busy-vs-dead; returns True if we should retry.
            should_retry = yield from diagnose_account_when_busy(config)
            if not should_retry:
                # auto_retry=False and threads busy → ThreadLimitError now.
                raise ThreadLimitError("All account threads are busy")
            # Time-based: keep retrying until thread_busy_timeout logical seconds
            # have elapsed. This covers a full reCAPTCHA v2 solve (60-80s) so a
            # slot is virtually certain to free up before the deadline.
            if busy_waited >= config.thread_busy_timeout:
                raise ThreadLimitError("All account threads busy — retries exhausted")
            # Wait ~8s for a slot to free, then retry. Track logical sleep time so
            # the deadline advances correctly even when time.sleep is a test no-op.
            sleep_time = next(busy_backoff)
            yield Sleep(sleep_time)
            busy_waited += sleep_time
            continue

        # Transient server/proxy errors: retry with backoff unless user opted out.
        if code in _SUBMIT_RETRYABLE:
            exc, message = _SUBMIT_RETRYABLE[code]
            if not config.auto_retry:
                raise exc(message)  # user manages retries → surface immediately
            attempts += 1
            if attempts > config.max_retries:
                raise exc(f"{message} — retries exhausted")
            yield Sleep(next(backoff))
            continue

        # Anything unrecognised is an unexpected API response.
        raise APIError(f"Unexpected submit error: {code or 'empty response'}")


def diagnose_account_when_busy(config: Config) -> Generator[Effect, object, bool]:
    resp = yield ApiCall(
        "POST",
        build_endpoint_url(config, "res.php"),
        {"key": config.api_key, "action": "threadsinfo", "json": 1},
    )
    body = get_body_or_raise(resp)
    counts = read_thread_counts(body)

    if counts["working_threads"] >= counts["threads"]:
        result = config.auto_retry
        return result
    raise NoThreadsError("Account expired or has no active plan")

def poll_until_ready(
    config: Config, entry: CaptchaTypeEntry, task_id: str
) -> Generator[Effect, object, dict]:
    """Keep asking the API for the answer until it is ready, then return it.

    Waits `entry.initial_wait` once, then checks every `entry.poll_interval`. All
    timing comes from the registry entry — never hardcoded here. Gives up with a
    TimeoutError after `config.max_poll_seconds` so a stuck task cannot hang forever.
    """
    # Initial wait before the first poll (with jitter), per the registry entry.
    yield Sleep(retry.add_jitter(entry.initial_wait, config.jitter_max))

    url = build_endpoint_url(config, "res.php")
    data = {"key": config.api_key, "action": "get", "id": task_id, "json": 1}
    waited = 0.0  # planned seconds elapsed, our deterministic timeout clock

    while True:
        resp = yield ApiCall("GET", url, data)
        body = get_body_or_raise(resp)
        status, request = read_status_and_request(body)

        # Success: the whole body goes to the extractor (it knows where the answer is).
        if status == 1:
            return body

        code = request

        # Not solved yet — this is NOT an error, just keep polling.
        if code == "CAPCHA_NOT_READY":
            if waited >= config.max_poll_seconds:
                raise TimeoutError("Poll deadline exceeded before a result was ready")
            yield Sleep(retry.add_jitter(entry.poll_interval, config.jitter_max))
            waited += entry.poll_interval
            continue

        # Always-fatal poll errors: raise immediately.
        if code in _POLL_FATAL:
            exc, message = _POLL_FATAL[code]
            raise exc(message)

        # Proxy hiccup during polling: retry unless the user manages retries.
        if code == "ERROR_PROXY_CONNECTION_FAILED":
            if not config.auto_retry:
                raise ProxyError("Proxy connection failed")
            if waited >= config.max_poll_seconds:
                raise ProxyError("Proxy connection failed — retries exhausted")
            yield Sleep(retry.add_jitter(entry.poll_interval, config.jitter_max))
            waited += entry.poll_interval
            continue

        # Anything else is an unexpected response.
        raise APIError(f"Unexpected poll error: {code or 'empty response'}")


def fetch_result(
    config: Config, entry: CaptchaTypeEntry, task_id: str
) -> Generator[Effect, object, object]:
    """Fetch the result of a task that was already submitted separately.

    Used by the manual `get_result()` API (submit and fetch as two steps). Reuses
    the same poll loop and extractor as the full solve, so behaviour is identical.
    """
    response = yield from poll_until_ready(config, entry, task_id)
    return extract.build_result(response, entry, task_id)


def solve_captcha(
    config: Config, entry: CaptchaTypeEntry, params: dict
) -> Generator[Effect, object, object]:
    """Solve one captcha from start to finish and return a SolveResult.

    Ties the three steps together: submit the task → wait and poll for the answer →
    shape it into a SolveResult. This is what every public client method runs.
    """
    # Submit and get the task id (validation/image/normalise happen inside).
    task_id = yield from submit_task(config, entry, params)
    # Poll until the answer is ready, then turn it into the uniform result shape.
    response = yield from poll_until_ready(config, entry, task_id)
    return extract.build_result(response, entry, task_id)
