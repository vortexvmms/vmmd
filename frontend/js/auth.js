// VCMS auth.js — Phase 3
// Handles: login, session storage, token refresh, logout,
// and authenticated calls to the VCMS backend.

const VMMS_SESSION_KEY = "vmms_session";

function saveSession(s) {
  localStorage.setItem(VMMS_SESSION_KEY, JSON.stringify({
    access_token: s.access_token,
    refresh_token: s.refresh_token,
    expires_at: Date.now() + (s.expires_in ? s.expires_in * 1000 : 3600 * 1000),
  }));
}

function getSession() {
  try { return JSON.parse(localStorage.getItem(VMMS_SESSION_KEY)); }
  catch { return null; }
}

function clearSession() {
  localStorage.removeItem(VMMS_SESSION_KEY);
  try { localStorage.removeItem("vmms_ref_cache"); } catch {}
}

// ---- login with email + password (Supabase Auth) ----
async function vmmsLogin(email, password) {
  const r = await fetch(
    `${VMMS_CONFIG.SUPABASE_URL}/auth/v1/token?grant_type=password`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "apikey": VMMS_CONFIG.SUPABASE_PUBLISHABLE,
      },
      body: JSON.stringify({ email, password }),
    }
  );
  const data = await r.json();
  if (!r.ok) {
    const msg = (data.error_description || data.msg || "").toLowerCase();
    if (msg.includes("invalid")) throw new Error("Wrong email or password.");
    throw new Error(data.error_description || data.msg || "Login failed — try again.");
  }
  try { localStorage.removeItem("vmms_ref_cache"); } catch {}   // fresh login → drop any old reference cache
  saveSession(data);
  return data;
}

// ---- refresh an expired session ----
async function vmmsRefresh() {
  const s = getSession();
  if (!s || !s.refresh_token) return false;
  const r = await fetch(
    `${VMMS_CONFIG.SUPABASE_URL}/auth/v1/token?grant_type=refresh_token`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "apikey": VMMS_CONFIG.SUPABASE_PUBLISHABLE,
      },
      body: JSON.stringify({ refresh_token: s.refresh_token }),
    }
  );
  if (!r.ok) { clearSession(); return false; }
  saveSession(await r.json());
  return true;
}

// ---- "server waking up" banner ----
// The backend sleeps on the free tier and can take ~40s to wake on the
// first request. Show a friendly banner so the app never looks frozen.
let _wakeTimer = null, _wakeEl = null, _wakePending = 0;
function _wakeShow() {
  if (!_wakeEl) {
    const st = document.createElement("style");
    st.textContent = "@keyframes vmmsspin{to{transform:rotate(360deg)}}";
    document.head.appendChild(st);
    _wakeEl = document.createElement("div");
    _wakeEl.id = "vmms-wake";
    _wakeEl.style.cssText = "position:fixed;left:0;right:0;bottom:0;z-index:99999;background:#C00000;color:#fff;font:600 14px/1.4 system-ui,-apple-system,sans-serif;padding:12px 16px;display:flex;align-items:center;gap:10px;box-shadow:0 -2px 12px rgba(0,0,0,.18)";
    _wakeEl.innerHTML = '<span style="flex:none;display:inline-block;width:16px;height:16px;border:3px solid rgba(255,255,255,.4);border-top-color:#fff;border-radius:50%;animation:vmmsspin .8s linear infinite"></span><span>Waking up the server… the first load can take up to a minute. Please wait.</span>';
    (document.body || document.documentElement).appendChild(_wakeEl);
  }
  _wakeEl.style.display = "flex";
}
function _wakeHide() { if (_wakeEl) _wakeEl.style.display = "none"; }

// ---- reference-data cache (workers / sites / holidays) -------------------
// These lists barely change during a day, but every page was re-fetching them
// on load. We cache the GET responses on the phone for a short window so most
// pages open without hitting the network for them. Any add/edit/delete to the
// same resource clears its cache immediately, and login/logout wipe it, so the
// data is never stale in a way the user would notice.
const VMMS_REF_KEY = "vmms_ref_cache";
const VMMS_REF_TTL = [                       // [path prefix, milliseconds]
  ["/api/v1/holidays", 12 * 3600 * 1000],    // ~yearly changes
  ["/api/v1/sites",    30 * 60 * 1000],      // rarely change
  ["/api/v1/workers",   5 * 60 * 1000],      // occasional adds/leave
];
function _refTtl(path) {
  const m = VMMS_REF_TTL.find(([p]) => path === p || path.startsWith(p + "?"));
  return m ? m[1] : 0;
}
function _refPrefix(path) {                   // for busting on mutations
  const m = VMMS_REF_TTL.find(([p]) => path === p || path.startsWith(p));
  return m ? m[0] : null;
}
function _refRead() {
  try { return JSON.parse(localStorage.getItem(VMMS_REF_KEY)) || {}; }
  catch { return {}; }
}
function _refWrite(o) { try { localStorage.setItem(VMMS_REF_KEY, JSON.stringify(o)); } catch {} }
function vmmsClearRefCache(prefix) {
  if (!prefix) { localStorage.removeItem(VMMS_REF_KEY); return; }
  const o = _refRead(); let changed = false;
  for (const k of Object.keys(o)) if (k.startsWith(prefix)) { delete o[k]; changed = true; }
  if (changed) _refWrite(o);
}

// ---- call the VCMS backend with the session token ----
// Retries once after a refresh if the token has expired.
async function vmmsApi(path, options = {}) {
  const method = (options.method || "GET").toUpperCase();

  // Serve reference GETs from the phone cache when still fresh.
  if (method === "GET") {
    const ttl = _refTtl(path);
    if (ttl) {
      const hit = _refRead()[path];
      if (hit && (Date.now() - hit.t) < ttl) {
        return new Response(hit.b, { status: 200, headers: { "Content-Type": "application/json" } });
      }
    }
  } else {
    // A write to workers/sites/holidays invalidates that resource's cache.
    const pfx = _refPrefix(path);
    if (pfx) vmmsClearRefCache(pfx);
  }

  const doFetch = async () => {
    const s = getSession();
    if (!s) throw new Error("NOT_SIGNED_IN");
    return fetch(`${VMMS_CONFIG.BACKEND_URL}${path}`, {
      ...options,
      headers: {
        ...(options.headers || {}),
        "Authorization": `Bearer ${s.access_token}`,
        "Content-Type": "application/json",
      },
    });
  };
  _wakePending++;
  // Only show the "waking up" banner on a genuine cold start (~40s), not on a
  // normal slow-ish save — otherwise it flashes on every attendance tap and
  // looks like the server is sleeping when it is just busy.
  if (!_wakeTimer) _wakeTimer = setTimeout(_wakeShow, 7000);
  try {
    // A dropped connection / cold-start makes fetch reject with "Failed to fetch".
    // Retry up to twice with a growing pause before surfacing the error.
    let r, lastErr = null;
    for (let attempt = 0; attempt < 3; attempt++) {
      try { r = await doFetch(); lastErr = null; break; }
      catch (netErr) {
        if (netErr && netErr.message === "NOT_SIGNED_IN") throw netErr;
        lastErr = netErr;
        await new Promise(res => setTimeout(res, 1000 * (attempt + 1)));  // 1s, then 2s
      }
    }
    if (lastErr) throw lastErr;
    if (r.status === 401) {
      const ok = await vmmsRefresh();
      if (!ok) throw new Error("NOT_SIGNED_IN");
      r = await doFetch();
    }
    // Store fresh reference GETs for next time (read a clone so we don't
    // consume the body the caller still needs).
    if (method === "GET" && _refTtl(path) && r.ok) {
      try {
        const b = await r.clone().text();
        const o = _refRead(); o[path] = { t: Date.now(), b }; _refWrite(o);
      } catch {}
    }
    return r;
  } finally {
    _wakePending--;
    if (_wakePending <= 0) { clearTimeout(_wakeTimer); _wakeTimer = null; _wakeHide(); }
  }
}

// ---- logout ----
function vmmsLogout() {
  clearSession();
  window.location.href = "login.html";
}

// ---- guard: send to login if no session (use on protected pages) ----
function requireLogin() {
  if (!getSession()) window.location.href = "login.html";
}
