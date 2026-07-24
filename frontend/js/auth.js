// VMMS auth.js — Phase 3
// Handles: login, session storage, token refresh, logout,
// and authenticated calls to the VMMS backend.

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

// ---- call the VMMS backend with the session token ----
// Retries once after a refresh if the token has expired.
async function vmmsApi(path, options = {}) {
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
  if (!_wakeTimer) _wakeTimer = setTimeout(_wakeShow, 2500);
  try {
    let r = await doFetch();
    if (r.status === 401) {
      const ok = await vmmsRefresh();
      if (!ok) throw new Error("NOT_SIGNED_IN");
      r = await doFetch();
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
