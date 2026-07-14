# CaptchaAI SDK Examples

Copy-paste cookbook for every captcha type and SDK feature. For API reference and option tables, see [captchaai/readme.md](captchaai/readme.md).

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Sync client setup](#sync-client-setup)
- [Async client setup](#async-client-setup)
- [Solve result](#solve-result)
- [Sync examples](#sync-examples)
  - [Normal captcha](#sync-normal-captcha)
  - [Grid captcha](#sync-grid-captcha)
  - [BLS captcha](#sync-bls-captcha)
  - [reCAPTCHA v2](#sync-recaptcha-v2)
  - [reCAPTCHA v3](#sync-recaptcha-v3)
  - [Cloudflare Turnstile](#sync-cloudflare-turnstile)
  - [Cloudflare Challenge](#sync-cloudflare-challenge)
  - [GeeTest](#sync-geetest)
  - [CaptchaFox](#sync-captchafox)
  - [Friendly Captcha](#sync-friendly-captcha)
  - [Lemin](#sync-lemin)
- [Async examples](#async-examples)
  - [Normal captcha](#async-normal-captcha)
  - [Grid captcha](#async-grid-captcha)
  - [BLS captcha](#async-bls-captcha)
  - [reCAPTCHA v2](#async-recaptcha-v2)
  - [reCAPTCHA v3](#async-recaptcha-v3)
  - [Cloudflare Turnstile](#async-cloudflare-turnstile)
  - [Cloudflare Challenge](#async-cloudflare-challenge)
  - [GeeTest](#async-geetest)
  - [CaptchaFox](#async-captchafox)
  - [Friendly Captcha](#async-friendly-captcha)
  - [Lemin](#async-lemin)
- [Functionality examples](#functionality-examples)
  - [Thread usage](#thread-usage)
  - [Manual submit and fetch](#manual-submit-and-fetch)
  - [Error handling](#error-handling)
  - [Proxies](#proxies)
  - [Retry behaviour](#retry-behaviour)
  - [Resource cleanup](#resource-cleanup)
  - [Mandatory-proxy types](#mandatory-proxy-types)
- [Placeholder reference](#placeholder-reference)

---

## Prerequisites

```bash
pip install captchaai
```

Requires **Python 3.10+**. Set your API key as an environment variable before running any example:

```bash
export CAPTCHAAI_API_KEY="your_32_character_api_key_here"
```

---

## Sync client setup

```python
import os
from captchaai import CaptchaAI

solver = CaptchaAI(
    api_key=os.environ["CAPTCHAAI_API_KEY"],
    proxy="user:pass@host:port",       # optional
    proxytype="HTTP",                  # required when proxy is set
    auto_retry=True,                   # retry transient errors with backoff
    base_url="https://ocr.captchaai.com",
    thread_busy_timeout=120.0,         # seconds to wait when all threads are busy
    max_retries=None,                  # optional; 0 disables, N > 0 caps attempts
)

# The constructor validates the key and learns your thread cap.
# Call solver.close() when finished.
```

---

## Async client setup

```python
import asyncio
import os
from captchaai import AsyncCaptchaAI

async def main():
    # Must use create() — direct AsyncCaptchaAI(...) is not allowed.
    solver = await AsyncCaptchaAI.create(
        api_key=os.environ["CAPTCHAAI_API_KEY"],
        proxy="user:pass@host:port",       # optional
        proxytype="HTTP",                  # required when proxy is set
        auto_retry=True,
        base_url="https://ocr.captchaai.com",
        thread_busy_timeout=120.0,
        max_retries=None,
    )

    # ... solve captchas ...

    await solver.aclose()

asyncio.run(main())
```

Async context manager:

```python
import asyncio
import os
from captchaai import AsyncCaptchaAI

async def main():
    solver = await AsyncCaptchaAI.create(api_key=os.environ["CAPTCHAAI_API_KEY"])
    async with solver:
        # solver is ready; aclose() runs on exit
        pass

asyncio.run(main())
```

---

## Solve result

Every solve method returns a `SolveResult`:

```python
import os
from captchaai import CaptchaAI

solver = CaptchaAI(api_key=os.environ["CAPTCHAAI_API_KEY"])

result = solver.turnstile(
    sitekey="YOUR_SITEKEY",
    url="https://example.com",
)

print(result.task_id)      # str  — task ID from submit (always present)
print(result.solution)     # str | list | dict — the answer
print(result.user_agent)   # str | None — solver browser UA (some types only)
print(result.raw)          # dict | None — full API response
print(result.raw_text)     # str | None — unparsed solution before JSON parsing
print(str(result))         # token string for common token types

solver.close()
```

**Solution shapes by type:**

| Type | `solution` shape | `user_agent` |
|------|------------------|--------------|
| normal, turnstile, friendly_captcha | `str` (token/text) | `None` |
| grid, bls | `list` (cell indices) | `None` |
| geetest, lemin | `dict` | `None` |
| recaptcha_v2/v3 enterprise, cloudflare_challenge, captchafox | `str` (token) | **required on target site** |

Reuse `result.user_agent` when submitting the token for Enterprise, Cloudflare Challenge, and CaptchaFox solves.

---

## Sync examples

### Sync: Normal captcha

Solve a text/image captcha. `image` accepts a file path, URL, data-URI, raw base64, or `bytes`.

**Required:** `image`  
**Optional:** `numeric`, `min_len`, `max_len`, `phrase`, `case_sensitive`, `lang`, `instructions`, `proxy`, `proxytype`

```python
import os
from captchaai import CaptchaAI

solver = CaptchaAI(api_key=os.environ["CAPTCHAAI_API_KEY"])

# From file path
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
print(result.solution)  # str — recognised text

solver.close()
```

From URL:

```python
import os
from captchaai import CaptchaAI

solver = CaptchaAI(api_key=os.environ["CAPTCHAAI_API_KEY"])
result = solver.normal("https://example.com/captcha.png")
print(result.solution)
solver.close()
```

From raw base64:

```python
import os
from captchaai import CaptchaAI

solver = CaptchaAI(api_key=os.environ["CAPTCHAAI_API_KEY"])
result = solver.normal("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
print(result.solution)
solver.close()
```

From bytes:

```python
import os
from captchaai import CaptchaAI

solver = CaptchaAI(api_key=os.environ["CAPTCHAAI_API_KEY"])
with open("captcha.png", "rb") as f:
    image_bytes = f.read()
result = solver.normal(image_bytes)
print(result.solution)
solver.close()
```

---

### Sync: Grid captcha

Solve a tile-selection captcha. `grid_size` must be `"3x3"` or `"4x4"`.

**Required:** `image`, `instructions`, `grid_size`  
**Optional:** `proxy`, `proxytype`

```python
import os
from captchaai import CaptchaAI

solver = CaptchaAI(api_key=os.environ["CAPTCHAAI_API_KEY"])

result = solver.grid(
    "grid.png",
    instructions="select all traffic lights",
    grid_size="3x3",
)
print(result.solution)  # list — cell indices to click, e.g. [0, 3, 7]

solver.close()
```

4x4 grid:

```python
import os
from captchaai import CaptchaAI

solver = CaptchaAI(api_key=os.environ["CAPTCHAAI_API_KEY"])
result = solver.grid(
    "grid_4x4.png",
    instructions="select all crosswalks",
    grid_size="4x4",
)
print(result.solution)
solver.close()
```

---

### Sync: BLS captcha

Solve a BLS multi-image captcha. Pass exactly **9** images.

**Required:** `images` (list of 9), `instructions`  
**Optional:** `proxy`, `proxytype`

```python
import os
from captchaai import CaptchaAI

solver = CaptchaAI(api_key=os.environ["CAPTCHAAI_API_KEY"])

result = solver.bls(
    images=[f"img{i}.png" for i in range(9)],
    instructions="YOUR_INSTRUCTIONS",
)
print(result.solution)  # list — cell indices

solver.close()
```

---

### Sync: reCAPTCHA v2

Solve reCAPTCHA v2 (standard, invisible, or enterprise).

**Required:** `sitekey`, `url`  
**Optional:** `invisible`, `enterprise`, `action`, `cookies`, `user_agent`, `proxy`, `proxytype`

Standard:

```python
import os
from captchaai import CaptchaAI

solver = CaptchaAI(api_key=os.environ["CAPTCHAAI_API_KEY"])

result = solver.recaptcha_v2(
    sitekey="YOUR_SITEKEY",
    url="https://example.com",
)
print(result.solution)  # str — g-recaptcha-response token

solver.close()
```

Invisible:

```python
import os
from captchaai import CaptchaAI

solver = CaptchaAI(api_key=os.environ["CAPTCHAAI_API_KEY"])
result = solver.recaptcha_v2(
    sitekey="YOUR_SITEKEY",
    url="https://example.com",
    invisible=True,
)
print(result.solution)
solver.close()
```

Enterprise (includes `user_agent` — reuse on the target site):

```python
import os
from captchaai import CaptchaAI

solver = CaptchaAI(api_key=os.environ["CAPTCHAAI_API_KEY"])
result = solver.recaptcha_v2(
    sitekey="YOUR_SITEKEY",
    url="https://example.com",
    enterprise=True,
    action="login",
)
print(result.solution, result.user_agent)
solver.close()
```

---

### Sync: reCAPTCHA v3

Solve reCAPTCHA v3 (standard or enterprise). `action` is required.

**Required:** `sitekey`, `url`, `action`  
**Optional:** `enterprise`, `min_score`, `cookies`, `user_agent`, `proxy`, `proxytype`

Standard:

```python
import os
from captchaai import CaptchaAI

solver = CaptchaAI(api_key=os.environ["CAPTCHAAI_API_KEY"])

result = solver.recaptcha_v3(
    sitekey="YOUR_SITEKEY",
    url="https://example.com",
    action="login",
    min_score=0.3,
)
print(result.solution)  # str — v3 token

solver.close()
```

Enterprise:

```python
import os
from captchaai import CaptchaAI

solver = CaptchaAI(api_key=os.environ["CAPTCHAAI_API_KEY"])
result = solver.recaptcha_v3(
    sitekey="YOUR_SITEKEY",
    url="https://example.com",
    action="login",
    enterprise=True,
)
print(result.solution, result.user_agent)  # reuse user_agent on target site
solver.close()
```

---

### Sync: Cloudflare Turnstile

Solve a Cloudflare Turnstile widget.

**Required:** `sitekey`, `url`  
**Optional:** `cookies`, `user_agent`, `proxy`, `proxytype`

```python
import os
from captchaai import CaptchaAI

solver = CaptchaAI(api_key=os.environ["CAPTCHAAI_API_KEY"])

result = solver.turnstile(
    sitekey="YOUR_SITEKEY",
    url="https://example.com",
    cookies="session=abc123",
    user_agent="Mozilla/5.0 ...",
)
print(result.solution)  # str — Turnstile token

solver.close()
```

---

### Sync: Cloudflare Challenge

Solve a Cloudflare interstitial challenge page. **Proxy is mandatory.**

**Required:** `url`, proxy (client-level or per-call)  
**Optional:** `cookies`, `user_agent`, `proxy`, `proxytype`

```python
import os
from captchaai import CaptchaAI

solver = CaptchaAI(
    api_key=os.environ["CAPTCHAAI_API_KEY"],
    proxy="user:pass@host:port",
    proxytype="HTTP",
)

result = solver.cloudflare_challenge(url="https://example.com")
print(result.solution, result.user_agent)  # reuse user_agent on target site

solver.close()
```

Per-call proxy override:

```python
import os
from captchaai import CaptchaAI

solver = CaptchaAI(api_key=os.environ["CAPTCHAAI_API_KEY"])
result = solver.cloudflare_challenge(
    url="https://example.com",
    proxy="user:pass@host:port",
    proxytype="HTTP",
)
print(result.solution, result.user_agent)
solver.close()
```

---

### Sync: GeeTest

Solve GeeTest v3. `solution` is a dict with `challenge`, `validate`, and `seccode`.

**Required:** `gt`, `challenge`, `url`  
**Optional:** `cookies`, `user_agent`, `proxy`, `proxytype`

```python
import os
from captchaai import CaptchaAI

solver = CaptchaAI(api_key=os.environ["CAPTCHAAI_API_KEY"])

result = solver.geetest(
    gt="YOUR_GT",
    challenge="YOUR_CHALLENGE",
    url="https://example.com",
)
print(result.solution["challenge"])
print(result.solution["validate"])
print(result.solution["seccode"])

solver.close()
```

---

### Sync: CaptchaFox

Solve a CaptchaFox slider challenge. **Proxy is mandatory.** Reuse `user_agent` when submitting the token.

**Required:** `sitekey`, `url`, proxy (client-level or per-call)  
**Optional:** `cookies`, `user_agent`, `proxy`, `proxytype`

```python
import os
from captchaai import CaptchaAI

solver = CaptchaAI(
    api_key=os.environ["CAPTCHAAI_API_KEY"],
    proxy="user:pass@host:port",
    proxytype="HTTP",
)

result = solver.captchafox(
    sitekey="YOUR_SITEKEY",
    url="https://example.com",
)
print(result.solution, result.user_agent)  # reuse user_agent on target site

solver.close()
```

---

### Sync: Friendly Captcha

Solve a Friendly Captcha proof-of-work challenge. No proxy required.

**Required:** `sitekey`, `url`  
**Optional:** `version` (`"v1"` or `"v2"`), `proxy`, `proxytype`

```python
import os
from captchaai import CaptchaAI

solver = CaptchaAI(api_key=os.environ["CAPTCHAAI_API_KEY"])

result = solver.friendly_captcha(
    sitekey="YOUR_SITEKEY",
    url="https://example.com",
    version="v1",
)
print(result.solution)  # str — verification token

solver.close()
```

v2 variant:

```python
import os
from captchaai import CaptchaAI

solver = CaptchaAI(api_key=os.environ["CAPTCHAAI_API_KEY"])
result = solver.friendly_captcha(
    sitekey="YOUR_SITEKEY",
    url="https://example.com",
    version="v2",
)
print(result.solution)
solver.close()
```

---

### Sync: Lemin

Solve a Lemin puzzle. `solution` is a dict with `answer` and `challenge_uuid`.

**Required:** `captcha_id`, `div_id`, `url`  
**Optional:** `api_server`, `proxy`, `proxytype`

```python
import os
from captchaai import CaptchaAI

solver = CaptchaAI(api_key=os.environ["CAPTCHAAI_API_KEY"])

result = solver.lemin(
    captcha_id="YOUR_CAPTCHA_ID",
    div_id="lemin-cropped-captcha",
    url="https://example.com",
    api_server="api.leminnow.com",   # optional override
)
print(result.solution["answer"])
print(result.solution["challenge_uuid"])

solver.close()
```

---

## Async examples

### Async: Normal captcha

```python
import asyncio
import os
from captchaai import AsyncCaptchaAI

async def main():
    solver = await AsyncCaptchaAI.create(api_key=os.environ["CAPTCHAAI_API_KEY"])

    # From file path
    result = await solver.normal(
        "captcha.png",
        numeric=1,
        min_len=4,
        max_len=6,
        instructions="Type the characters you see",
    )
    print(result.solution)

    await solver.aclose()

asyncio.run(main())
```

From URL:

```python
import asyncio
import os
from captchaai import AsyncCaptchaAI

async def main():
    solver = await AsyncCaptchaAI.create(api_key=os.environ["CAPTCHAAI_API_KEY"])
    result = await solver.normal("https://example.com/captcha.png")
    print(result.solution)
    await solver.aclose()

asyncio.run(main())
```

From raw base64:

```python
import asyncio
import os
from captchaai import AsyncCaptchaAI

async def main():
    solver = await AsyncCaptchaAI.create(api_key=os.environ["CAPTCHAAI_API_KEY"])
    result = await solver.normal("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
    print(result.solution)
    await solver.aclose()

asyncio.run(main())
```

From bytes:

```python
import asyncio
import os
from captchaai import AsyncCaptchaAI

async def main():
    solver = await AsyncCaptchaAI.create(api_key=os.environ["CAPTCHAAI_API_KEY"])
    with open("captcha.png", "rb") as f:
        image_bytes = f.read()
    result = await solver.normal(image_bytes)
    print(result.solution)
    await solver.aclose()

asyncio.run(main())
```

---

### Async: Grid captcha

```python
import asyncio
import os
from captchaai import AsyncCaptchaAI

async def main():
    solver = await AsyncCaptchaAI.create(api_key=os.environ["CAPTCHAAI_API_KEY"])

    result = await solver.grid(
        "grid.png",
        instructions="select all traffic lights",
        grid_size="3x3",
    )
    print(result.solution)  # list — cell indices

    await solver.aclose()

asyncio.run(main())
```

4x4 grid:

```python
import asyncio
import os
from captchaai import AsyncCaptchaAI

async def main():
    solver = await AsyncCaptchaAI.create(api_key=os.environ["CAPTCHAAI_API_KEY"])
    result = await solver.grid(
        "grid_4x4.png",
        instructions="select all crosswalks",
        grid_size="4x4",
    )
    print(result.solution)
    await solver.aclose()

asyncio.run(main())
```

---

### Async: BLS captcha

```python
import asyncio
import os
from captchaai import AsyncCaptchaAI

async def main():
    solver = await AsyncCaptchaAI.create(api_key=os.environ["CAPTCHAAI_API_KEY"])

    result = await solver.bls(
        images=[f"img{i}.png" for i in range(9)],
        instructions="YOUR_INSTRUCTIONS",
    )
    print(result.solution)  # list — cell indices

    await solver.aclose()

asyncio.run(main())
```

---

### Async: reCAPTCHA v2

Standard:

```python
import asyncio
import os
from captchaai import AsyncCaptchaAI

async def main():
    solver = await AsyncCaptchaAI.create(api_key=os.environ["CAPTCHAAI_API_KEY"])
    result = await solver.recaptcha_v2(
        sitekey="YOUR_SITEKEY",
        url="https://example.com",
    )
    print(result.solution)
    await solver.aclose()

asyncio.run(main())
```

Invisible:

```python
import asyncio
import os
from captchaai import AsyncCaptchaAI

async def main():
    solver = await AsyncCaptchaAI.create(api_key=os.environ["CAPTCHAAI_API_KEY"])
    result = await solver.recaptcha_v2(
        sitekey="YOUR_SITEKEY",
        url="https://example.com",
        invisible=True,
    )
    print(result.solution)
    await solver.aclose()

asyncio.run(main())
```

Enterprise:

```python
import asyncio
import os
from captchaai import AsyncCaptchaAI

async def main():
    solver = await AsyncCaptchaAI.create(api_key=os.environ["CAPTCHAAI_API_KEY"])
    result = await solver.recaptcha_v2(
        sitekey="YOUR_SITEKEY",
        url="https://example.com",
        enterprise=True,
        action="login",
    )
    print(result.solution, result.user_agent)
    await solver.aclose()

asyncio.run(main())
```

---

### Async: reCAPTCHA v3

Standard:

```python
import asyncio
import os
from captchaai import AsyncCaptchaAI

async def main():
    solver = await AsyncCaptchaAI.create(api_key=os.environ["CAPTCHAAI_API_KEY"])
    result = await solver.recaptcha_v3(
        sitekey="YOUR_SITEKEY",
        url="https://example.com",
        action="login",
        min_score=0.3,
    )
    print(result.solution)
    await solver.aclose()

asyncio.run(main())
```

Enterprise:

```python
import asyncio
import os
from captchaai import AsyncCaptchaAI

async def main():
    solver = await AsyncCaptchaAI.create(api_key=os.environ["CAPTCHAAI_API_KEY"])
    result = await solver.recaptcha_v3(
        sitekey="YOUR_SITEKEY",
        url="https://example.com",
        action="login",
        enterprise=True,
    )
    print(result.solution, result.user_agent)
    await solver.aclose()

asyncio.run(main())
```

---

### Async: Cloudflare Turnstile

```python
import asyncio
import os
from captchaai import AsyncCaptchaAI

async def main():
    solver = await AsyncCaptchaAI.create(api_key=os.environ["CAPTCHAAI_API_KEY"])
    result = await solver.turnstile(
        sitekey="YOUR_SITEKEY",
        url="https://example.com",
        cookies="session=abc123",
        user_agent="Mozilla/5.0 ...",
    )
    print(result.solution)
    await solver.aclose()

asyncio.run(main())
```

---

### Async: Cloudflare Challenge

**Proxy is mandatory.**

```python
import asyncio
import os
from captchaai import AsyncCaptchaAI

async def main():
    solver = await AsyncCaptchaAI.create(
        api_key=os.environ["CAPTCHAAI_API_KEY"],
        proxy="user:pass@host:port",
        proxytype="HTTP",
    )
    result = await solver.cloudflare_challenge(url="https://example.com")
    print(result.solution, result.user_agent)
    await solver.aclose()

asyncio.run(main())
```

Per-call proxy:

```python
import asyncio
import os
from captchaai import AsyncCaptchaAI

async def main():
    solver = await AsyncCaptchaAI.create(api_key=os.environ["CAPTCHAAI_API_KEY"])
    result = await solver.cloudflare_challenge(
        url="https://example.com",
        proxy="user:pass@host:port",
        proxytype="HTTP",
    )
    print(result.solution, result.user_agent)
    await solver.aclose()

asyncio.run(main())
```

---

### Async: GeeTest

```python
import asyncio
import os
from captchaai import AsyncCaptchaAI

async def main():
    solver = await AsyncCaptchaAI.create(api_key=os.environ["CAPTCHAAI_API_KEY"])
    result = await solver.geetest(
        gt="YOUR_GT",
        challenge="YOUR_CHALLENGE",
        url="https://example.com",
    )
    print(result.solution["challenge"])
    print(result.solution["validate"])
    print(result.solution["seccode"])
    await solver.aclose()

asyncio.run(main())
```

---

### Async: CaptchaFox

**Proxy is mandatory.**

```python
import asyncio
import os
from captchaai import AsyncCaptchaAI

async def main():
    solver = await AsyncCaptchaAI.create(
        api_key=os.environ["CAPTCHAAI_API_KEY"],
        proxy="user:pass@host:port",
        proxytype="HTTP",
    )
    result = await solver.captchafox(
        sitekey="YOUR_SITEKEY",
        url="https://example.com",
    )
    print(result.solution, result.user_agent)
    await solver.aclose()

asyncio.run(main())
```

---

### Async: Friendly Captcha

```python
import asyncio
import os
from captchaai import AsyncCaptchaAI

async def main():
    solver = await AsyncCaptchaAI.create(api_key=os.environ["CAPTCHAAI_API_KEY"])
    result = await solver.friendly_captcha(
        sitekey="YOUR_SITEKEY",
        url="https://example.com",
        version="v1",
    )
    print(result.solution)
    await solver.aclose()

asyncio.run(main())
```

v2 variant:

```python
import asyncio
import os
from captchaai import AsyncCaptchaAI

async def main():
    solver = await AsyncCaptchaAI.create(api_key=os.environ["CAPTCHAAI_API_KEY"])
    result = await solver.friendly_captcha(
        sitekey="YOUR_SITEKEY",
        url="https://example.com",
        version="v2",
    )
    print(result.solution)
    await solver.aclose()

asyncio.run(main())
```

---

### Async: Lemin

```python
import asyncio
import os
from captchaai import AsyncCaptchaAI

async def main():
    solver = await AsyncCaptchaAI.create(api_key=os.environ["CAPTCHAAI_API_KEY"])
    result = await solver.lemin(
        captcha_id="YOUR_CAPTCHA_ID",
        div_id="lemin-cropped-captcha",
        url="https://example.com",
        api_server="api.leminnow.com",
    )
    print(result.solution["answer"])
    print(result.solution["challenge_uuid"])
    await solver.aclose()

asyncio.run(main())
```

---

## Functionality examples

### Thread usage

CaptchaAI is thread-based. Check current usage:

Sync:

```python
import os
from captchaai import CaptchaAI

solver = CaptchaAI(api_key=os.environ["CAPTCHAAI_API_KEY"])
info = solver.threads_info()
print(info)  # {"threads": 10, "working_threads": 3}
solver.close()
```

Async:

```python
import asyncio
import os
from captchaai import AsyncCaptchaAI

async def main():
    solver = await AsyncCaptchaAI.create(api_key=os.environ["CAPTCHAAI_API_KEY"])
    info = await solver.threads_info()
    print(info)
    await solver.aclose()

asyncio.run(main())
```

---

### Manual submit and fetch

Submit a task now and poll later. Params use **API names** (`googlekey`, `pageurl`), not the friendly client names.

Sync:

```python
import os
from captchaai import CaptchaAI

solver = CaptchaAI(api_key=os.environ["CAPTCHAAI_API_KEY"])

task_id = solver.send(
    "recaptcha_v2",
    googlekey="YOUR_SITEKEY",
    pageurl="https://example.com",
)
print(task_id)

result = solver.get_result("recaptcha_v2", task_id)
print(result.solution)

solver.close()
```

Async:

```python
import asyncio
import os
from captchaai import AsyncCaptchaAI

async def main():
    solver = await AsyncCaptchaAI.create(api_key=os.environ["CAPTCHAAI_API_KEY"])

    task_id = await solver.send(
        "recaptcha_v2",
        googlekey="YOUR_SITEKEY",
        pageurl="https://example.com",
    )
    print(task_id)

    result = await solver.get_result("recaptcha_v2", task_id)
    print(result.solution)

    await solver.aclose()

asyncio.run(main())
```

---

### Error handling

All SDK errors inherit from `CaptchaAIError`:

```python
import os
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

solver = CaptchaAI(api_key=os.environ["CAPTCHAAI_API_KEY"])

try:
    result = solver.recaptcha_v2(
        sitekey="YOUR_SITEKEY",
        url="https://example.com",
    )
except InvalidKeyError:
    print("Wrong-length key, or API rejected the key")
except ValidationError:
    print("Missing/invalid params, bad image input, or missing required proxy")
except ProxyError:
    print("Bad proxy or proxy connection failed")
except ThreadLimitError:
    print("All account threads busy (retries skipped or exhausted)")
except NoThreadsError:
    print("Account expired or has no active plan")
except UnsolvableError:
    print("Service could not solve the captcha")
except NetworkError:
    print("Could not reach the API")
except TimeoutError:
    print("Poll deadline exceeded before a result was ready")
except APIError:
    print("Unexpected or malformed API response")
except CaptchaAIError:
    print("Any other SDK error")
finally:
    solver.close()
```

Async:

```python
import asyncio
import os
from captchaai import AsyncCaptchaAI, CaptchaAIError, ThreadLimitError

async def main():
    solver = await AsyncCaptchaAI.create(api_key=os.environ["CAPTCHAAI_API_KEY"])
    try:
        result = await solver.turnstile(
            sitekey="YOUR_SITEKEY",
            url="https://example.com",
        )
        print(result.solution)
    except ThreadLimitError:
        print("All threads busy")
    except CaptchaAIError as err:
        print(f"SDK error: {err}")
    finally:
        await solver.aclose()

asyncio.run(main())
```

---

### Proxies

Format: `"user:pass@host:port"`. `proxytype` is required whenever a proxy is set (`HTTP`, `HTTPS`, `SOCKS4`, `SOCKS5`).

Client-level (every solve):

```python
import os
from captchaai import CaptchaAI

solver = CaptchaAI(
    api_key=os.environ["CAPTCHAAI_API_KEY"],
    proxy="user:pass@host:port",
    proxytype="HTTP",
)
result = solver.recaptcha_v2(
    sitekey="YOUR_SITEKEY",
    url="https://example.com",
)
print(result.solution)
solver.close()
```

Per-call override (does not mutate client config):

```python
import os
from captchaai import CaptchaAI

solver = CaptchaAI(api_key=os.environ["CAPTCHAAI_API_KEY"])
result = solver.recaptcha_v2(
    sitekey="YOUR_SITEKEY",
    url="https://example.com",
    proxy="user:pass@other-host:port",
    proxytype="SOCKS5",
)
print(result.solution)
solver.close()
```

Async with proxy:

```python
import asyncio
import os
from captchaai import AsyncCaptchaAI

async def main():
    solver = await AsyncCaptchaAI.create(
        api_key=os.environ["CAPTCHAAI_API_KEY"],
        proxy="user:pass@host:port",
        proxytype="HTTP",
    )
    result = await solver.turnstile(
        sitekey="YOUR_SITEKEY",
        url="https://example.com",
    )
    print(result.solution)
    await solver.aclose()

asyncio.run(main())
```

---

### Retry behaviour

| Setting | Behaviour |
|---------|-----------|
| `auto_retry=True` (default) | Retry transient submit/proxy errors with exponential backoff |
| `auto_retry=False` | Raise immediately; fast-fails when local in-flight count hits thread cap |
| `max_retries=N` (`N > 0`) | Like `auto_retry=True`, capped at N submit attempts |
| `max_retries=0` | Like `auto_retry=False` |

Disable retries (raise immediately):

```python
import os
from captchaai import CaptchaAI

solver = CaptchaAI(
    api_key=os.environ["CAPTCHAAI_API_KEY"],
    auto_retry=False,
)
result = solver.recaptcha_v2(
    sitekey="YOUR_SITEKEY",
    url="https://example.com",
)
print(result.solution)
solver.close()
```

Cap retries at 3 attempts:

```python
import os
from captchaai import CaptchaAI

solver = CaptchaAI(
    api_key=os.environ["CAPTCHAAI_API_KEY"],
    max_retries=3,
)
result = solver.recaptcha_v2(
    sitekey="YOUR_SITEKEY",
    url="https://example.com",
)
print(result.solution)
solver.close()
```

Disable retries via `max_retries=0`:

```python
import os
from captchaai import CaptchaAI

solver = CaptchaAI(
    api_key=os.environ["CAPTCHAAI_API_KEY"],
    max_retries=0,
)
result = solver.recaptcha_v2(
    sitekey="YOUR_SITEKEY",
    url="https://example.com",
)
print(result.solution)
solver.close()
```

Async with capped retries:

```python
import asyncio
import os
from captchaai import AsyncCaptchaAI

async def main():
    solver = await AsyncCaptchaAI.create(
        api_key=os.environ["CAPTCHAAI_API_KEY"],
        max_retries=3,
    )
    result = await solver.turnstile(
        sitekey="YOUR_SITEKEY",
        url="https://example.com",
    )
    print(result.solution)
    await solver.aclose()

asyncio.run(main())
```

---

### Resource cleanup

Sync — explicit close:

```python
import os
from captchaai import CaptchaAI

solver = CaptchaAI(api_key=os.environ["CAPTCHAAI_API_KEY"])
result = solver.normal("captcha.png")
print(result.solution)
solver.close()  # release HTTP connections
```

Async — explicit aclose:

```python
import asyncio
import os
from captchaai import AsyncCaptchaAI

async def main():
    solver = await AsyncCaptchaAI.create(api_key=os.environ["CAPTCHAAI_API_KEY"])
    result = await solver.normal("captcha.png")
    print(result.solution)
    await solver.aclose()

asyncio.run(main())
```

Async context manager:

```python
import asyncio
import os
from captchaai import AsyncCaptchaAI

async def main():
    solver = await AsyncCaptchaAI.create(api_key=os.environ["CAPTCHAAI_API_KEY"])
    async with solver:
        result = await solver.normal("captcha.png")
        print(result.solution)

asyncio.run(main())
```

---

### Mandatory-proxy types

These captcha types require a proxy at client level or per call:

- `cloudflare_challenge`
- `captchafox`

Sync — Cloudflare Challenge:

```python
import os
from captchaai import CaptchaAI

solver = CaptchaAI(
    api_key=os.environ["CAPTCHAAI_API_KEY"],
    proxy="user:pass@host:port",
    proxytype="HTTP",
)
result = solver.cloudflare_challenge(url="https://example.com")
print(result.solution, result.user_agent)
solver.close()
```

Sync — CaptchaFox:

```python
import os
from captchaai import CaptchaAI

solver = CaptchaAI(
    api_key=os.environ["CAPTCHAAI_API_KEY"],
    proxy="user:pass@host:port",
    proxytype="HTTP",
)
result = solver.captchafox(
    sitekey="YOUR_SITEKEY",
    url="https://example.com",
)
print(result.solution, result.user_agent)
solver.close()
```

Async — both types:

```python
import asyncio
import os
from captchaai import AsyncCaptchaAI

async def main():
    solver = await AsyncCaptchaAI.create(
        api_key=os.environ["CAPTCHAAI_API_KEY"],
        proxy="user:pass@host:port",
        proxytype="HTTP",
    )

    cf_result = await solver.cloudflare_challenge(url="https://example.com")
    print(cf_result.solution, cf_result.user_agent)

    fox_result = await solver.captchafox(
        sitekey="YOUR_SITEKEY",
        url="https://example.com",
    )
    print(fox_result.solution, fox_result.user_agent)

    await solver.aclose()

asyncio.run(main())
```

---

## Placeholder reference

Replace these placeholders with your real values before running examples:

| Placeholder | Description |
|-------------|-------------|
| `CAPTCHAAI_API_KEY` | 32-character API key (env var) |
| `YOUR_SITEKEY` | reCAPTCHA / Turnstile / CaptchaFox / Friendly Captcha site key |
| `YOUR_GT` | GeeTest static `gt` value from the target site |
| `YOUR_CHALLENGE` | GeeTest dynamic `challenge` value from the target site |
| `YOUR_CAPTCHA_ID` | Lemin `captchaId` value |
| `YOUR_INSTRUCTIONS` | BLS solver instructions text |
| `user:pass@host:port` | Proxy credentials and address |
| `captcha.png`, `grid.png`, `img0.png`… | Local image file paths |
| `https://example.com` | Target page URL where the captcha appears |
| `lemin-cropped-captcha` | Lemin widget parent div `id` attribute |
| `api.leminnow.com` | Lemin API server subdomain (optional override) |
