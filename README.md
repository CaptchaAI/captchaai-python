# CaptchaAI Python SDK

<p align="left">
  <a href="https://pypi.org/project/captchaai/"><img src="https://img.shields.io/pypi/v/captchaai?label=PyPI&logo=pypi" alt="PyPI" /></a>
  <a href="https://github.com/CaptchaAI/captchaai-python/releases"><img src="https://img.shields.io/github/v/release/CaptchaAI/captchaai-python?label=Release" alt="GitHub Release" /></a>
  <a href="https://docs.captchaai.com/"><img src="https://img.shields.io/badge/Docs-docs.captchaai.com-blue" alt="Documentation" /></a>
  <a href="https://chromewebstore.google.com/detail/fnnmnnfpdnlkccecmiicejhimhkbolhk?utm_source=item-share-cb"><img src="https://img.shields.io/chrome-web-store/v/fnnmnnfpdnlkccecmiicejhimhkbolhk?label=Chrome%20Extension&logo=googlechrome" alt="Chrome Extension" /></a>
  <a href="https://github.com/CaptchaAI/captchaai-python/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License" /></a>
</p>

CaptchaAI Python library (`v2.0.1`, Python `>=3.10`, typed via `py.typed`) — an official CAPTCHA solver and solving API client for reCAPTCHA v2/v3/Enterprise, Cloudflare Turnstile, Cloudflare Challenge, GeeTest v3, CaptchaFox, Friendly Captcha, Lemin, and image CAPTCHAs, with optional Playwright browser automation.

Call one method per captcha type; the SDK handles HTTP, polling, retries, and typed error mapping via a sans-IO generator engine.

For full copy-paste examples of every captcha type and SDK feature, see [examples.md](https://github.com/CaptchaAI/captchaai-python/blob/main/examples.md). For internal design details, see [ARCHITECTURE.md](ARCHITECTURE.md).

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
- [reCAPTCHA v2](#recaptcha-v2)
- [reCAPTCHA v3](#recaptcha-v3)
- [Cloudflare Turnstile](#cloudflare-turnstile)
- [Cloudflare Challenge](#cloudflare-challenge)
- [GeeTest v3](#geetest-v3)
- [CaptchaFox](#captchafox)
- [Friendly Captcha](#friendly-captcha)
- [Lemin](#lemin)
- [Browser automation (Playwright)](#browser-automation-playwright)
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

Requires **Python 3.10+** (runtime dependency: `httpx`):

```bash
pip install captchaai
```

To enable optional Playwright browser helpers (`detect_captchas`, `get_captchas_params`, `inject_on_page`, `solve_url`):

```bash
pip install "captchaai[playwright]"
playwright install chromium
```

## Configuration

Create a sync client with your API key from [CaptchaAI](https://captchaai.com/). `CaptchaAI` validates the 32-character key length locally and reads the account thread cap via a startup `threadsinfo` call (`AsyncCaptchaAI.create()` delegates key validation to the startup `threadsinfo` call).

```python
from captchaai import CaptchaAI

solver = CaptchaAI(
    api_key="YOUR_32_CHAR_API_KEY",
    proxy="user:pass@host:port",       # optional
    proxytype="HTTP",                  # required when proxy is set ("HTTP" or "HTTPS")
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
| `proxytype` | `None` | `"HTTP"` or `"HTTPS"` — required when `proxy` is set |
| `auto_retry` | `True` | `True` = SDK retries transient/proxy/busy-thread errors with backoff; `False` = fail fast (including local in-flight thread-cap gating) |
| `base_url` | `https://ocr.captchaai.com` | API host for `in.php` / `res.php` |
| `thread_busy_timeout` | `120.0` | Logical seconds budget to keep retrying while all account threads are busy |
| `max_retries` | `None` | When set: `0` disables retries (`auto_retry=False`); `N > 0` enables retries with up to `N` submit attempts (supersedes `auto_retry`) |

A bad key raises `InvalidKeyError` before any solve runs. Call `solver.close()` when finished to release the HTTP client (`CaptchaAI` does not implement `__enter__`/`__exit__`; use `async with` on `AsyncCaptchaAI`).

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

Solve a text/image captcha. `image` may be a file path, URL, data-URI, raw base64, or `bytes`. PNG and GIF images are checked locally and must not exceed `1000px` in width or height.

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

Solve reCAPTCHA v3. `action` is required; `min_score` defaults to `None` (omitted unless set, e.g. `0.1`–`0.9`). Enterprise results include `user_agent`.

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

Solve a Cloudflare Turnstile challenge. Optional: `cookies`, `user_agent`, `proxy`, `proxytype`.

```python
result = solver.turnstile(
    sitekey="0x4AAAAAAAB...",
    url="https://example.com",
)
print(result.solution)
```

---

## Cloudflare Challenge

Solve Cloudflare Challenge (5s / Managed / Non-Interactive). **A working proxy is required** (`HTTP` or `HTTPS`, via client config or per-call override). Optional: `cookies`, `user_agent`.

```python
result = solver.cloudflare_challenge(
    url="https://example.com",
    proxy="user:pass@host:port",             # required (or set at client level)
    proxytype="HTTP",                        # required
    user_agent="Mozilla/5.0 ...",            # optional
)
print(result.solution)                       # cf_clearance cookie / token
print(result.user_agent)
```

---

## GeeTest v3

Solve a GeeTest v3 challenge. Requires `gt`, `challenge`, and `url`. Optional: `cookies`, `user_agent`, `proxy`, `proxytype`. Returns a structured dict with `challenge`, `validate`, and `seccode`.

```python
result = solver.geetest(
    gt="YOUR_GT",
    challenge="YOUR_CHALLENGE",
    url="https://example.com",
)
print(result.solution["challenge"])
print(result.solution["validate"])
print(result.solution["seccode"])
```

---

## CaptchaFox

Solve CaptchaFox. **A working proxy is required.** Returns the solution token and a `user_agent` to reuse on the target site.

```python
result = solver.captchafox(
    sitekey="YOUR_SITEKEY",
    url="https://example.com",
    proxy="user:pass@host:port",
    proxytype="HTTP",
)
print(result.solution)
print(result.user_agent)
```

---

## Friendly Captcha

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

## Lemin

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

## Browser automation (Playwright)

With `pip install "captchaai[playwright]"`, both `CaptchaAI` and `AsyncCaptchaAI` provide token-mode CAPTCHA detection, parameter extraction, solving, and page injection for Playwright (`reCAPTCHA v2/v3/Enterprise`, `Turnstile`, and `Cloudflare Challenge`):

```python
# One-shot: launch Chromium, detect CAPTCHAs, solve, and autofill
results = solver.solve_url("https://example.com", headless=True)
for item in results:
    print(item.params.captcha_type, item.injected, item.error)
    if item.result:
        print(item.result.solution)
```

You can also pass an already-open Playwright `page` (left open after solving) or use the lower-level building blocks:

```python
from captchaai import RECAPTCHA_INIT_HOOK_JS

# Install hook before navigation so dynamic callbacks / v3 actions are captured
page.context.add_init_script(RECAPTCHA_INIT_HOOK_JS)
page.goto("https://example.com")

# Option A: solve & autofill an already-open page
results = solver.solve_url(page=page)

# Option B: inspect and inject manually
detected = solver.detect_captchas(page)           # e.g. ["recaptcha_v2", "turnstile"]
params_list = solver.get_captchas_params(page)    # list[CaptchaParams]
for params in params_list:
    task_id = solver.send(params.captcha_type, **params.to_api_params())
    res = solver.get_result(params.captcha_type, task_id)
    solver.inject_on_page(page, params, res)
```

> **Note:** `solve_url()` installs `RECAPTCHA_INIT_HOOK_JS` automatically when given a `url`. For `cloudflare_challenge`, `inject_on_page()` adds the `cf_clearance` cookie directly to `page.context`.

---

## Other methods

### Thread usage

Check current thread usage:

```python
info = solver.threads_info()
# {"threads": 10, "working_threads": 3}
```

### Account balance

Check the raw account balance string:

```python
balance = solver.get_balance()
# e.g. "12.34"
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

### Supported types metadata

Inspect all 14 registered captcha types and their requirements:

```python
from captchaai import supported_types

types_map = supported_types()
print(list(types_map.keys()))
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

Proxies are supported at client level and per call. Format: `"user:pass@host:port"`. `proxytype` is required whenever a proxy is set (`HTTP` or `HTTPS`).

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
    proxytype="HTTPS",
)
```

---

## Async usage

`AsyncCaptchaAI` mirrors every solver, utility, and Playwright browser method as `async def`. Direct `AsyncCaptchaAI(...)` instantiation is blocked — always construct it via `await AsyncCaptchaAI.create(...)`, and close via `await solver.aclose()` or `async with`:

```python
import asyncio
from captchaai import AsyncCaptchaAI

async def main():
    async with await AsyncCaptchaAI.create(api_key="YOUR_32_CHAR_API_KEY") as solver:
        result = await solver.turnstile(
            sitekey="YOUR_SITEKEY",
            url="https://example.com",
        )
        print(result.solution)

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
