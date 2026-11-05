# CaptchaAI Python SDK

<p align="left">
  <a href="https://pypi.org/project/captchaai/"><img src="https://img.shields.io/pypi/v/captchaai?label=PyPI&logo=pypi" alt="PyPI" /></a>
  <a href="https://github.com/CaptchaAI/captchaai-python/releases"><img src="https://img.shields.io/github/v/release/CaptchaAI/captchaai-python?label=Release" alt="GitHub Release" /></a>
  <a href="https://docs.captchaai.com/"><img src="https://img.shields.io/badge/Docs-docs.captchaai.com-blue" alt="Documentation" /></a>
  <a href="https://chromewebstore.google.com/detail/fnnmnnfpdnlkccecmiicejhimhkbolhk?utm_source=item-share-cb"><img src="https://img.shields.io/chrome-web-store/v/fnnmnnfpdnlkccecmiicejhimhkbolhk?label=Chrome%20Extension&logo=googlechrome" alt="Chrome Extension" /></a>
  <a href="https://github.com/CaptchaAI/captchaai-python/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License" /></a>
</p>

CaptchaAI Python library — an official CAPTCHA solver and solving API client for reCAPTCHA v2/v3/Enterprise, Cloudflare Turnstile, Cloudflare Challenge, GeeTest v3, and image CAPTCHAs.

Call one method per captcha type; the SDK handles HTTP, polling, retries, and typed error mapping.

For full copy-paste examples of every captcha type and SDK feature, see [examples.md](https://github.com/CaptchaAI/captchaai-python/blob/main/examples.md).

---

## Table of Contents

- [Examples](https://github.com/CaptchaAI/captchaai-python/blob/main/examples.md)
- [Packages](#packages)
- [Installation](#installation)
- [Configuration](#configuration)
- [Solve result](#solve-result)
- [Normal captcha](#normal-captcha)
- [Grid captcha](#grid-captcha)
- [BLS captcha](#bls-captcha)
- [reCAPTCHA v2 & v3](#recaptcha-v2)
- [Cloudflare Turnstile](#cloudflare-turnstile)
- [Cloudflare Challenge](#cloudflare-challenge)
- [GeeTest v3](#geetest-v3)
- [CaptchaFox (beta)](#captchafox-beta)
- [Friendly Captcha (beta)](#friendly-captcha-beta)
- [Lemin (beta)](#lemin-beta)
- [Other methods](#other-methods)
- [Error handling](#error-handling)
- [Proxies](#proxies)
- [Async usage](#async-usage)
- [License](#license)

---

## Packages

- **PyPI Package:** [https://pypi.org/project/captchaai/](https://pypi.org/project/captchaai/) (`pip install captchaai`)
- **GitHub Releases:** [https://github.com/CaptchaAI/captchaai-python/releases](https://github.com/CaptchaAI/captchaai-python/releases)

---

## Installation

```bash
pip install captchaai
```

## Configuration

Create a sync client with your API key from [CaptchaAI](https://captchaai.com/). The constructor validates the key and reads the account thread cap via a startup `threadsinfo` call.

```python
from captchaai import CaptchaAI

solver = CaptchaAI(
    api_key="YOUR_32_CHAR_API_KEY",
    proxy="user:pass@host:port",       # optional
    proxytype="HTTP",                  # required when proxy is set
    auto_retry=True,
    base_url="https://ocr.captchaai.com",
    thread_busy_timeout=120.0,
    max_retries=None,                  # optional; overrides auto_retry when set
)
```

| Option | Default | Description |
|--------|---------|-------------|
| `api_key` | *(required)* | 32-character CaptchaAI API key |
| `proxy` | `None` | `"user:pass@host:port"` applied to every solve |
| `proxytype` | `None` | `HTTP` / `HTTPS` / `SOCKS4` / `SOCKS5` — required when `proxy` is set |
| `auto_retry` | `True` | `True` = SDK retries transient errors with backoff; `False` = raise immediately |
| `base_url` | `https://ocr.captchaai.com` | API host for `in.php` / `res.php` |
| `thread_busy_timeout` | `120.0` | Seconds to keep retrying while all account threads are busy |
| `max_retries` | `None` | When set: `0` disables retries; `N > 0` enables up to N submit attempts (supersedes `auto_retry`) |

A bad key raises `InvalidKeyError` before any solve runs. Call `solver.close()` when finished to release the HTTP client.

---

## Solve result

Every solve method returns a `SolveResult`:

```python
result.task_id     # str — task ID from submit (always present)
result.solution    # str | list | dict — token, cell indices, or structured answer
result.user_agent  # str | None — set for Enterprise / Cloudflare Challenge / CaptchaFox
result.raw         # dict | None — full API response (debugging)
result.raw_text    # str | None — unparsed solution string before JSON parsing

str(result)        # token string for common token types
```

Reuse `result.user_agent` on the target site when it is present (Enterprise, Cloudflare Challenge, CaptchaFox).

---

## Normal captcha

Solve a text/image captcha. `image` may be a file path, URL, data-URI, raw base64, or `bytes`.

```python
from captchaai import CaptchaAI

solver = CaptchaAI(api_key="YOUR_32_CHAR_API_KEY")

result = solver.normal(
    "captcha.png",
    numeric=1,              # 0=any, 1=digits, 2=letters, 3=digits+letters, 4=no digits
    min_len=4,
    max_len=6,
    phrase=0,               # 0=single word, 1=multi-word
    case_sensitive=0,       # 0=insensitive, 1=case-sensitive
    lang="en",
    instructions="Type the characters you see",
)
print(result.solution)
```

---

## Grid captcha

Solve a tile-selection captcha. `grid_size` must be `"3x3"` or `"4x4"`. `solution` is a list of cell indices.

```python
result = solver.grid(
    "grid.png",
    instructions="select all traffic lights",
    grid_size="3x3",
)
print(result.solution)
```

---

## BLS captcha

Solve a BLS multi-image captcha. Pass exactly **9** images (path/URL/base64/bytes each). `solution` is a list of cell indices.

```python
result = solver.bls(
    images=[f"img{i}.png" for i in range(9)],
    instructions="YOUR_INSTRUCTIONS",
)
print(result.solution)
```

---

## reCAPTCHA v2

Solve reCAPTCHA v2 (standard, invisible, or enterprise). Pass `sitekey` and page `url`. Enterprise results include `user_agent`.

```python
# Standard
result = solver.recaptcha_v2(
    sitekey="YOUR_SITEKEY",
    url="https://example.com",
)
print(result.solution)

# Invisible
result = solver.recaptcha_v2(
    sitekey="YOUR_SITEKEY",
    url="https://example.com",
    invisible=True,
)

# Enterprise (optional action; result may include user_agent)
result = solver.recaptcha_v2(
    sitekey="YOUR_SITEKEY",
    url="https://example.com",
    enterprise=True,
    action="login",
)
print(result.solution)
print(result.user_agent)
```

---

## reCAPTCHA v3

Solve reCAPTCHA v3. `min_score` defaults to `0.3`. Enterprise results include `user_agent`.

```python
# Standard v3
result = solver.recaptcha_v3(
    sitekey="YOUR_SITEKEY",
    url="https://example.com",
    action="verify",
    min_score=0.7,
)
print(result.solution)

# Enterprise v3
result = solver.recaptcha_v3(
    sitekey="YOUR_SITEKEY",
    url="https://example.com",
    action="login",
    min_score=0.9,
    enterprise=True,
)
```

---

## Cloudflare Turnstile

Solve a Cloudflare Turnstile challenge. Optional: `action`, `cdata`, `user_agent`.

```python
result = solver.turnstile(
    sitekey="0x4AAAAAAAB...",
    url="https://example.com",
    action="login",
)
print(result.solution)
```

---

## Cloudflare Challenge

Solve Cloudflare Challenge (5s / Managed / Non-Interactive). **A working proxy is required.**

```python
result = solver.cloudflare_challenge(
    url="https://example.com",
    html="<html>...</html>",                 # full page HTML
    proxy="user:pass@host:port",             # required
    proxytype="HTTP",                        # required
    user_agent="Mozilla/5.0 ...",            # must match the session that fetched the HTML
)
print(result.solution)                       # clearance cf_clearance cookie or token
print(result.user_agent)
```

---

## GeeTest v3

Solve a GeeTest v3 challenge. Requires `gt`, `challenge`, and `url`. Optional: `api_server`.

```python
result = solver.geetest_v3(
    gt="YOUR_GT",
    challenge="YOUR_CHALLENGE",
    url="https://example.com",
)
print(result.solution["geetest_challenge"])
print(result.solution["geetest_validate"])
print(result.solution["geetest_seccode"])
```

---

## CaptchaFox (beta)

Solve CaptchaFox. **A working proxy is required.**

```python
result = solver.captchafox(
    sitekey="YOUR_SITEKEY",
    url="https://example.com",
    proxy="user:pass@host:port",
    proxytype="HTTP",
)
print(result.solution)
```

---

## Friendly Captcha (beta)

Solve Friendly Captcha (v1 or v2). No proxy is required.

```python
result = solver.friendly_captcha(
    sitekey="YOUR_SITEKEY",
    url="https://example.com",
    version="v1",   # optional: "v1" or "v2"
)
print(result.solution)
```

---

## Lemin (beta)

Solve a Lemin puzzle. `solution` is a dict with `answer` and `challenge_uuid`.

```python
result = solver.lemin(
    captcha_id="YOUR_CAPTCHA_ID",
    div_id="lemin-cropped-captcha",
    url="https://example.com",
    api_server="api.leminnow.com",   # optional
)
print(result.solution["answer"])
print(result.solution["challenge_uuid"])
```

---

## Other methods

### Thread usage

CaptchaAI is thread-based. Check current usage:

```python
info = solver.threads_info()
# {"threads": 10, "working_threads": 3}
```

### Manual submit / fetch

Submit now and poll later:

```python
task_id = solver.send(
    "recaptcha_v2",
    googlekey="YOUR_SITEKEY",
    pageurl="https://example.com",
)

result = solver.get_result("recaptcha_v2", task_id)
print(result.solution)
```

### Close

```python
solver.close()
```

---

## Error handling

All SDK errors inherit from `CaptchaAIError`:

```python
from captchaai import (
    CaptchaAI,
    CaptchaAIError,
    InvalidKeyError,
    ValidationError,
    ProxyError,
    ThreadLimitError,
    NoThreadsError,
    UnsolvableError,
    APIError,
    NetworkError,
    TimeoutError,
)

solver = CaptchaAI(api_key="YOUR_32_CHAR_API_KEY")

try:
    result = solver.recaptcha_v2(
        sitekey="YOUR_SITEKEY",
        url="https://example.com",
    )
except InvalidKeyError:
    ...  # wrong-length key, or API rejected the key
except ValidationError:
    ...  # missing/invalid params, bad image input, missing required proxy, etc.
except ProxyError:
    ...  # bad proxy or proxy connection failed
except ThreadLimitError:
    ...  # all account threads busy
except NoThreadsError:
    ...  # account expired or has no active plan
except UnsolvableError:
    ...  # service could not solve the captcha
except NetworkError:
    ...  # could not reach the API
except TimeoutError:
    ...  # poll deadline exceeded before a result was ready
except APIError:
    ...  # unexpected / malformed API response
except CaptchaAIError:
    ...  # any other SDK error
```

---

## Proxies

Proxies are supported at client level and per call. Format: `"user:pass@host:port"`. `proxytype` is required whenever a proxy is set (`HTTP`, `HTTPS`, `SOCKS4`, or `SOCKS5`).

```python
# Client-level (every solve)
solver = CaptchaAI(
    api_key="YOUR_32_CHAR_API_KEY",
    proxy="user:pass@host:port",
    proxytype="HTTP",
)

# Per-call override (does not mutate client config)
result = solver.recaptcha_v2(
    sitekey="YOUR_SITEKEY",
    url="https://example.com",
    proxy="user:pass@other-host:port",
    proxytype="SOCKS5",
)
```

---

## Async usage

Build the async client with `await AsyncCaptchaAI.create(...)`:

```python
import asyncio
from captchaai import AsyncCaptchaAI

async def main():
    solver = await AsyncCaptchaAI.create(api_key="YOUR_32_CHAR_API_KEY")

    result = await solver.turnstile(
        sitekey="YOUR_SITEKEY",
        url="https://example.com",
    )
    print(result.solution)

    await solver.aclose()

asyncio.run(main())
```

---

## Resources & Links

- 🌐 [Official Website](https://captchaai.com/)
- 📘 [API Documentation](https://docs.captchaai.com/)
- 🐍 [PyPI Package](https://pypi.org/project/captchaai/)
- 🧩 [Chrome Extension](https://chromewebstore.google.com/detail/fnnmnnfpdnlkccecmiicejhimhkbolhk?utm_source=item-share-cb)

---

## License

This project is licensed under the [MIT License](LICENSE).

Copyright (c) 2026 Dev@Captchaai
