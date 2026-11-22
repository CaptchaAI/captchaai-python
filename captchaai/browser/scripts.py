# ── What this file IS ─────────────────────────────────────────────────────────
# Self-contained JavaScript snippets evaluated on a Playwright Page for token-mode
# CAPTCHA detection/extraction and solution token injection.

from __future__ import annotations

# Installed via `page.context.add_init_script(...)` prior to `page.goto(...)` so
# `grecaptcha.execute(sitekey, {action})` calls are captured during page boot.
RECAPTCHA_INIT_HOOK_JS: str = """
(() => {
  const actions = (window.__captchaai_v3_actions = window.__captchaai_v3_actions || []);
  const record = (sitekey, opts) => {
    if (opts && typeof opts === "object" && opts.action) {
      actions.push({ sitekey: sitekey || null, action: String(opts.action) });
    }
  };
  const wrapExecute = (fn) => {
    if (typeof fn !== "function" || fn.__captchaai_wrapped) return fn;
    const wrapped = function (sitekey, opts) {
      record(sitekey, opts);
      return fn.apply(this, arguments);
    };
    wrapped.__captchaai_wrapped = true;
    return wrapped;
  };
  const hookObj = (obj) => {
    if (!obj || typeof obj !== "object" || obj.__captchaai_hooked) return obj;
    let currentExec = typeof obj.execute === "function" ? wrapExecute(obj.execute) : obj.execute;
    try {
      Object.defineProperty(obj, "execute", {
        configurable: true,
        enumerable: true,
        get() { return currentExec; },
        set(fn) { currentExec = wrapExecute(fn); },
      });
    } catch (_) {}
    if ("enterprise" in obj && obj.enterprise) {
      hookObj(obj.enterprise);
    } else {
      let currentEnt = obj.enterprise;
      try {
        Object.defineProperty(obj, "enterprise", {
          configurable: true,
          enumerable: true,
          get() { return currentEnt; },
          set(ent) { currentEnt = hookObj(ent); },
        });
      } catch (_) {}
    }
    try { Object.defineProperty(obj, "__captchaai_hooked", { value: true }); } catch (_) {}
    return obj;
  };
  if (window.grecaptcha) {
    hookObj(window.grecaptcha);
  } else {
    let current = undefined;
    try {
      Object.defineProperty(window, "grecaptcha", {
        configurable: true,
        enumerable: true,
        get() { return current; },
        set(val) { current = hookObj(val); },
      });
    } catch (_) {}
  }

  // Hook `window.turnstile.render` so programmatic widgets (e.g. React wrappers)
  // expose their sitekey and callback even without `.cf-turnstile[data-sitekey]`.
  const tsWidgets = (window.__captchaai_turnstiles = window.__captchaai_turnstiles || []);
  const wrapTurnstileRender = (fn) => {
    if (typeof fn !== "function" || fn.__captchaai_wrapped) return fn;
    const wrapped = function (container, opts) {
      if (opts && typeof opts === "object" && opts.sitekey) {
        let cbName = typeof opts.callback === "string" && opts.callback ? opts.callback : null;
        if (typeof opts.callback === "function") {
          cbName = "__captchaai_ts_cb_" + tsWidgets.length;
          window[cbName] = opts.callback;
        }
        const el = typeof container === "string" ? document.querySelector(container) : container;
        tsWidgets.push({
          sitekey: String(opts.sitekey),
          action: opts.action ? String(opts.action) : null,
          cdata: opts.cData ? String(opts.cData) : null,
          callback: cbName,
          container_id: el && el.id ? el.id : null,
        });
      }
      return fn.apply(this, arguments);
    };
    wrapped.__captchaai_wrapped = true;
    return wrapped;
  };
  const hookTurnstile = (obj) => {
    if (!obj || typeof obj !== "object" || obj.__captchaai_hooked) return obj;
    if (typeof obj.render === "function") obj.render = wrapTurnstileRender(obj.render);
    try { Object.defineProperty(obj, "__captchaai_hooked", { value: true }); } catch (_) {}
    return obj;
  };
  // Avoid pre-defining `window.turnstile` because api.js skips init if `"turnstile" in window`.
  // Capture `<script>` load events on `document` (subresource `load` captures at `document`, not `window`).
  if (window.turnstile) hookTurnstile(window.turnstile);
  document.addEventListener("load", () => {
    if (window.turnstile) hookTurnstile(window.turnstile);
  }, true);
})();
"""

GET_RECAPTCHA_PARAMS_JS: str = """
(() => {
  const results = [];
  const seen = new Set();
  const ua = navigator.userAgent;
  const v3Actions = Array.isArray(window.__captchaai_v3_actions)
    ? window.__captchaai_v3_actions
    : [];
  const hasEnterpriseScript = Boolean(
    document.querySelector('script[src*="recaptcha/enterprise.js"]') ||
      document.querySelector('iframe[src*="/recaptcha/enterprise/"]') ||
      (window.grecaptcha && window.grecaptcha.enterprise)
  );
  const renderKeys = new Set();
  document.querySelectorAll('script[src*="recaptcha/"]').forEach((sc) => {
    try {
      const u = new URL(sc.src, location.href);
      const r = u.searchParams.get("render");
      if (r && r !== "explicit") renderKeys.add(r);
    } catch (_) {}
  });

  const actionForKey = (sitekey) => {
    for (let i = v3Actions.length - 1; i >= 0; i--) {
      if (!v3Actions[i].sitekey || v3Actions[i].sitekey === sitekey) {
        return v3Actions[i].action;
      }
    }
    return null;
  };

  const resolveCallback = (cb, widgetId) => {
    if (typeof cb === "function") {
      const name = "reCaptchaWidgetCallback" + widgetId;
      window[name] = cb;
      return name;
    }
    return typeof cb === "string" && cb ? cb : null;
  };

  const getSaParam = () => {
    try {
      const frame = document.querySelector('iframe[title="reCAPTCHA"]');
      const src = frame ? frame.getAttribute("src") : null;
      return src ? new URL(src, location.href).searchParams.get("sa") : null;
    } catch (_) {
      return null;
    }
  };

  const pushWidget = (w) => {
    const key = `${w.sitekey || ""}|${w.captcha_type}|${w.container_id || ""}|${w.action || ""}`;
    if (seen.has(key)) return;
    seen.add(key);
    results.push(w);
  };

  const cfg = window.___grecaptcha_cfg;
  if (cfg && cfg.clients) {
    Object.values(cfg.clients).forEach((client, idx) => {
      if (!client || typeof client !== "object") return;
      const widgetId = client.id !== undefined ? client.id : idx;
      const enterprise =
        hasEnterpriseScript ||
        (Array.isArray(cfg.enterprise) && cfg.enterprise.includes(widgetId));
      let sitekey = null;
      let size = null;
      let callback = null;
      let action = null;
      let sVal = null;
      let containerId = null;
      let bindedButtonId = null;

      const scan = (obj, depth) => {
        if (!obj || typeof obj !== "object" || depth > 3) return;
        if (typeof obj.sitekey === "string") {
          sitekey = sitekey || obj.sitekey;
          if (obj.size) size = size || obj.size;
          if (obj.callback || obj["promise-callback"]) {
            callback = callback || obj.callback || obj["promise-callback"];
          }
          if (obj.action) action = action || obj.action;
          if (obj.s) sVal = sVal || obj.s;
          if (obj.bind && obj.bind.id) bindedButtonId = bindedButtonId || obj.bind.id;
        }
        if (obj instanceof Element && obj.id && !containerId) {
          containerId = obj.id;
        }
        Object.values(obj).forEach((v) => {
          if (v && typeof v === "object" && !(v instanceof Window)) {
            scan(v, depth + 1);
          }
        });
      };
      scan(client, 0);

      if (!sitekey) return;
      const v3HookAction = actionForKey(sitekey);
      // Only treat as v3 when explicitly loaded via `render=<sitekey>` or executed via
      // `grecaptcha.execute(sitekey, {action})`; v2 widgets may also carry `data-action`.
      const isV3 = renderKeys.has(sitekey) || Boolean(v3HookAction);
      const capturedAction = action || v3HookAction || (!isV3 ? getSaParam() : null);
      const invisible = size === "invisible";
      let captchaType;
      if (isV3) {
        captchaType = enterprise ? "recaptcha_v3_enterprise" : "recaptcha_v3";
      } else if (enterprise) {
        captchaType = "recaptcha_v2_enterprise";
      } else if (invisible) {
        captchaType = "recaptcha_v2_invisible";
      } else {
        captchaType = "recaptcha_v2";
      }

      pushWidget({
        captcha_type: captchaType,
        sitekey,
        action: capturedAction,
        invisible: invisible || isV3,
        enterprise,
        s: sVal,
        container_id: containerId,
        callback: resolveCallback(callback, widgetId),
        binded_button_id: bindedButtonId,
        user_agent: ua,
      });
    });
  }

  // Fallback for DOM widgets rendered before/without `___grecaptcha_cfg`.
  document.querySelectorAll(".g-recaptcha[data-sitekey]").forEach((el) => {
    const sitekey = el.getAttribute("data-sitekey");
    if (!sitekey) return;
    const size = el.getAttribute("data-size");
    const v3HookAction = actionForKey(sitekey);
    const invisible = size === "invisible";
    const isV3 = renderKeys.has(sitekey) || Boolean(v3HookAction);
    const action = el.getAttribute("data-action") || v3HookAction || (!isV3 ? getSaParam() : null);
    let captchaType;
    if (isV3) {
      captchaType = hasEnterpriseScript ? "recaptcha_v3_enterprise" : "recaptcha_v3";
    } else if (hasEnterpriseScript) {
      captchaType = "recaptcha_v2_enterprise";
    } else if (invisible) {
      captchaType = "recaptcha_v2_invisible";
    } else {
      captchaType = "recaptcha_v2";
    }
    pushWidget({
      captcha_type: captchaType,
      sitekey,
      action,
      invisible: invisible || isV3,
      enterprise: hasEnterpriseScript,
      s: el.getAttribute("data-s"),
      container_id: el.id || null,
      callback: el.getAttribute("data-callback") || null,
      binded_button_id: null,
      user_agent: ua,
    });
  });

  // Pure script/hook v3 entries that have no `.g-recaptcha` container.
  renderKeys.forEach((sitekey) => {
    const already = results.some((r) => r.sitekey === sitekey);
    if (!already) {
      pushWidget({
        captcha_type: hasEnterpriseScript ? "recaptcha_v3_enterprise" : "recaptcha_v3",
        sitekey,
        action: actionForKey(sitekey),
        invisible: true,
        enterprise: hasEnterpriseScript,
        s: null,
        container_id: null,
        callback: null,
        binded_button_id: null,
        user_agent: ua,
      });
    }
  });
  v3Actions.forEach((entry) => {
    if (!entry || !entry.sitekey) return;
    const already = results.some((r) => r.sitekey === entry.sitekey);
    if (!already) {
      pushWidget({
        captcha_type: hasEnterpriseScript ? "recaptcha_v3_enterprise" : "recaptcha_v3",
        sitekey: entry.sitekey,
        action: entry.action || null,
        invisible: true,
        enterprise: hasEnterpriseScript,
        s: null,
        container_id: null,
        callback: null,
        binded_button_id: null,
        user_agent: ua,
      });
    }
  });

  return results;
})();
"""

INJECT_RECAPTCHA_JS: str = """
(payload) => {
  const { token, containerId, callback } = payload || {};
  let injected = false;
  const root = containerId ? document.getElementById(containerId) || document : document;
  const fields = root.querySelectorAll('textarea[name="g-recaptcha-response"], #g-recaptcha-response');
  const targets = fields.length
    ? fields
    : document.querySelectorAll('textarea[name="g-recaptcha-response"], #g-recaptcha-response');

  targets.forEach((el) => {
    el.value = token;
    el.innerHTML = token;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    injected = true;
  });

  if (callback) {
    let fn = window[callback];
    if (typeof fn !== "function" && callback.includes(".")) {
      fn = callback.split(".").reduce((acc, part) => (acc ? acc[part] : undefined), window);
    }
    if (typeof fn === "function") {
      try {
        fn(token);
        injected = true;
      } catch (_) {}
    }
  }
  return injected;
}
"""

GET_TURNSTILE_PARAMS_JS: str = """
(() => {
  // Full-page Cloudflare Challenge embeds an internal Turnstile widget; let cloudflare_challenge win.
  if (window._cf_chl_opt || document.querySelector("#challenge-running, #challenge-form")) {
    return [];
  }
  const results = [];
  const seen = new Set();
  const ua = navigator.userAgent;

  document.querySelectorAll(".cf-turnstile[data-sitekey], [data-turnstile-sitekey]").forEach((el) => {
    const sitekey = el.getAttribute("data-sitekey") || el.getAttribute("data-turnstile-sitekey");
    if (!sitekey || seen.has(sitekey)) return;
    seen.add(sitekey);
    results.push({
      sitekey,
      action: el.getAttribute("data-action") || null,
      cdata: el.getAttribute("data-cdata") || null,
      callback: el.getAttribute("data-callback") || null,
      container_id: el.id || null,
      user_agent: ua,
    });
  });

  if (Array.isArray(window.__captchaai_turnstiles)) {
    window.__captchaai_turnstiles.forEach((entry) => {
      if (!entry || !entry.sitekey || seen.has(entry.sitekey)) return;
      seen.add(entry.sitekey);
      results.push({
        sitekey: entry.sitekey,
        action: entry.action || null,
        cdata: entry.cdata || null,
        callback: entry.callback || null,
        container_id: entry.container_id || null,
        user_agent: ua,
      });
    });
  }

  if (results.length === 0) {
    const collectFrames = (root, out) => {
      if (!root || !root.querySelectorAll) return;
      root.querySelectorAll('iframe[src*="challenges.cloudflare.com"]').forEach((f) => out.push(f));
      root.querySelectorAll("*").forEach((el) => {
        if (el.shadowRoot) collectFrames(el.shadowRoot, out);
      });
    };
    const frames = [];
    collectFrames(document, frames);
    frames.forEach((frame) => {
      const m = frame.src.match(/\\/(0x[0-9a-zA-Z_-]+)\\//);
      if (m && !seen.has(m[1])) {
        seen.add(m[1]);
        results.push({
          sitekey: m[1],
          action: null,
          cdata: null,
          callback: null,
          container_id: frame.parentElement ? frame.parentElement.id || null : null,
          user_agent: ua,
        });
      }
    });
  }

  return results;
})();
"""

INJECT_TURNSTILE_JS: str = """
(payload) => {
  const { token, containerId, callback } = payload || {};
  let injected = false;
  const root = containerId ? document.getElementById(containerId) || document : document;
  const fields = root.querySelectorAll(
    'input[name="cf-turnstile-response"], input[name="g-recaptcha-response"], textarea[name="g-recaptcha-response"]'
  );
  const targets = fields.length
    ? fields
    : document.querySelectorAll('input[name="cf-turnstile-response"]');

  targets.forEach((el) => {
    el.value = token;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    injected = true;
  });

  if (callback) {
    let fn = window[callback];
    if (typeof fn !== "function" && callback.includes(".")) {
      fn = callback.split(".").reduce((acc, part) => (acc ? acc[part] : undefined), window);
    }
    if (typeof fn === "function") {
      try {
        fn(token);
        injected = true;
      } catch (_) {}
    }
  }
  return injected;
}
"""

GET_CLOUDFLARE_CHALLENGE_PARAMS_JS: str = """
(() => {
  const isChallenge = Boolean(
    window._cf_chl_opt ||
      document.querySelector(
        '#challenge-running, #challenge-form, script[src*="/cdn-cgi/challenge-platform/"]'
      )
  );
  if (!isChallenge) return null;
  return { detected: true, user_agent: navigator.userAgent };
})();
"""
