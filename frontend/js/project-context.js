/* Canonical VCMS Project context.
   localStorage is a display preference only. The selected ID is accepted only
   after /api/v1/projects returns it for the signed-in user through RLS. */
(function () {
  "use strict";
  var KEY = "vcms_active_project_id";
  var projects = [];
  var active = null;
  var initialized = false;

  function emit() {
    window.dispatchEvent(new CustomEvent("vcms:project-changed", { detail: { project: active } }));
  }

  function savedId() {
    try { return localStorage.getItem(KEY) || ""; } catch (_) { return ""; }
  }

  function remember(id) {
    try {
      if (id) localStorage.setItem(KEY, id);
      else localStorage.removeItem(KEY);
    } catch (_) {}
  }

  function selectAuthorized(id) {
    var match = projects.find(function (p) { return p.id === id; }) || null;
    active = match || projects[0] || null;
    remember(active && active.id);
    emit();
    return active;
  }

  async function init() {
    if (initialized) return active;
    if (typeof vmmsApi !== "function" || typeof getSession !== "function" || !getSession()) return null;
    var response = await vmmsApi("/api/v1/projects?status=active");
    if (!response.ok) throw new Error("Could not load authorized projects");
    projects = await response.json();
    initialized = true;
    return selectAuthorized(savedId());
  }

  function mount(container) {
    if (!container || container.querySelector("#vcms-project-select")) return;
    var wrap = document.createElement("label");
    wrap.id = "vcms-project-context";
    wrap.setAttribute("aria-label", "Active project");
    wrap.innerHTML = '<span class="vcms-project-label">Project</span><select id="vcms-project-select" disabled><option>Loading…</option></select>';
    var logout = container.querySelector(".lo");
    container.insertBefore(wrap, logout || null);
    var select = wrap.querySelector("select");
    init().then(function () {
      select.innerHTML = projects.length
        ? projects.map(function (p) { return '<option value="' + esc(p.id) + '">' + esc(p.project_code + " — " + p.project_name) + '</option>'; }).join("")
        : '<option value="">No active projects</option>';
      select.disabled = !projects.length;
      select.value = active ? active.id : "";
    }).catch(function () {
      select.innerHTML = '<option value="">Projects unavailable</option>';
      select.disabled = true;
    });
    select.addEventListener("change", function () { selectAuthorized(select.value); });
  }

  window.vcmsProjectContext = {
    init: init,
    mount: mount,
    getActive: function () { return active; },
    getActiveId: function () { return active && active.id; },
    getAuthorizedProjects: function () { return projects.slice(); },
    select: selectAuthorized,
    requireActiveId: function () {
      if (!active) throw new Error("Select an active project before continuing");
      return active.id;
    },
  };
})();
