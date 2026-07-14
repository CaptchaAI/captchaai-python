# ── What this file IS ─────────────────────────────────────────────────────────
# The complete typed exception hierarchy for the CaptchaAI SDK.
# It exists so callers can either catch one base class (CaptchaAIError) to handle
# every failure in one place, or catch a specific subclass to react differently
# to each distinct failure mode. Every error the SDK raises is one of these types.


class CaptchaAIError(Exception):
    """Base class for every error the SDK raises.

    Catch this to handle all SDK failures in one place. Every other exception
    in this module is a subclass, so `except CaptchaAIError` covers everything.
    """


class InvalidKeyError(CaptchaAIError):
    """The API key is the wrong format or does not exist.

    Raised at startup from the `threadsinfo` validation call when the API returns
    ERROR_WRONG_USER_KEY (bad format) or ERROR_KEY_DOES_NOT_EXIST (not found).
    """


class ValidationError(CaptchaAIError):
    """Input failed validation, or the API rejected the input as malformed.

    Raised by the local validator before any HTTP call, and also when the API
    reports a bad-input error code (bad params, bad page URL, image issues, etc.).
    """


class ProxyError(CaptchaAIError):
    """The supplied proxy was rejected as bad.

    Raised on ERROR_BAD_PROXY. A bad proxy will not fix itself, so this never
    retries regardless of the auto_retry flag.
    """


class ThreadLimitError(CaptchaAIError):
    """All account threads are busy and retries were exhausted (or skipped).

    Raised after a `threadsinfo` check confirms working_threads >= threads when
    either auto_retry=False (raise immediately) or the bounded retry loop gives up.
    """


class NoThreadsError(CaptchaAIError):
    """The account has no usable threads (expired or no active plan).

    Raised when `threadsinfo` shows working_threads < threads yet a submit was
    still rejected. Always raised immediately — retrying a dead account is pointless.
    """


class UnsolvableError(CaptchaAIError):
    """The captcha could not be solved after the service's own attempts.

    Raised on ERROR_CAPTCHA_UNSOLVABLE during polling. No retry — the service
    already tried multiple times before reporting this.
    """


class APIError(CaptchaAIError):
    """The API returned an unexpected, malformed, or programmer-error response.

    Raised for codes that indicate a bug or an out-of-band condition (wrong/empty
    task id, empty action, IP banned, or any response shape the SDK cannot parse).
    """


class NetworkError(CaptchaAIError):
    """The HTTP request could not reach the API.

    Raised when the transport reports a connection-level failure (its sentinel
    status code) rather than a usable API response.
    """


class TimeoutError(CaptchaAIError):
    """The poll loop ran out of time before a result was ready.

    Raised when polling exceeds the configured overall deadline. Defined here so
    it lives inside the CaptchaAIError tree rather than being the builtin TimeoutError.
    """
