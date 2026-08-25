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

  window.VCMS_UI = { toast, errorMessage, setLoading, requestJSON };
})();
