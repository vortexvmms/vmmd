// Shared VCMS feedback, loading and API-state components.
(function () {
  let toastTimer;
  function toast(message, type) {
    let el = document.getElementById("vcms-toast");
    if (!el) {
      el = document.createElement("div");
      el.id = "vcms-toast";
      el.setAttribute("role", "status");
      el.setAttribute("aria-live", "polite");
      document.body.appendChild(el);
    }
    el.className = "vcms-toast " + (type || "info");
    el.textContent = message;
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.hidden = true; }, type === "error" ? 6000 : 3200);
  }

  async function errorMessage(response, fallback) {
    if (!response) return fallback || "Could not connect. Check your connection and try again.";
    try {
      const body = await response.clone().json();
      return body.detail || body.message || fallback || "The request could not be completed.";
    } catch (_) {
      return fallback || (response.status === 403 ? "You do not have permission for this action." : "The request could not be completed.");
    }
  }

  function setLoading(target, loading, label) {
    const el = typeof target === "string" ? document.querySelector(target) : target;
    if (!el) return;
    if (loading) {
      if (!el.dataset.vcmsLabel) el.dataset.vcmsLabel = el.textContent || "";
      el.disabled = true;
      el.setAttribute("aria-busy", "true");
      el.classList.add("vcms-is-loading");
      if (label) el.textContent = label;
    } else {
      el.disabled = false;
      el.removeAttribute("aria-busy");
      el.classList.remove("vcms-is-loading");
      if (el.dataset.vcmsLabel) el.textContent = el.dataset.vcmsLabel;
    }
  }

  async function requestJSON(path, options) {
    let response;
    try {
      response = await window.vmmsApi(path, options || {});
    } catch (error) {
      if (error && error.message === "NOT_SIGNED_IN") {
        window.location.replace("login.html");
        throw error;
      }
      const message = "Could not connect. Your changes were not confirmed.";
      toast(message, "error");
      throw new Error(message);
    }
    if (!response.ok) {
      const message = await errorMessage(response);
      toast(message, "error");
      const error = new Error(message);
      error.status = response.status;
      throw error;
    }
    if (response.status === 204) return null;
    return response.json();
  }

  function pageHeader(options) {
    options = options || {};
    const header = document.createElement("header");
    header.className = "vcms-page-header " + (options.className || "");
    const action = options.actionHTML || "";
    const toolbar = options.toolbarHTML ? `<div class="vcms-page-toolbar">${options.toolbarHTML}</div>` : "";
    header.innerHTML = `<div class="vcms-page-header__row"><a class="vcms-page-header__back" href="${window.esc(options.back||"home.html")}" aria-label="Back">‹</a><div class="vcms-page-header__title"><h1>${window.esc(options.title||"VCMS")}</h1>${options.subtitle?`<p>${window.esc(options.subtitle)}</p>`:""}</div>${action}</div>${toolbar}`;
    return header;
  }

  function stateHTML(type, message, actionHTML) {
    const safeType = /^(loading|empty|error)$/.test(type) ? type : "empty";
    return `<div class="vcms-state ${safeType}" role="status"><div>${window.esc(message||"")}${actionHTML||""}</div></div>`;
  }

  function status(label, type) {
    const safeType = /^(success|warning|danger|neutral)$/.test(type) ? type : "neutral";
    return `<span class="vcms-status vcms-status-${safeType}">${window.esc(label||"")}</span>`;
  }

  window.VCMS_UI = { toast, errorMessage, setLoading, requestJSON, pageHeader, stateHTML, status };
})();
