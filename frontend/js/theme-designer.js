// VCMS Custom Theme Designer (admin-only). Mounts into #vcms-theme-designer on settings.html.
// Stores only validated --vcms-* tokens. Base 6 colours persist to /api/v1/appearance
// (all users, existing path); the richer token bundle is versioned in localStorage and
// painted site-wide by the core "theme-ext" block until the backend token bundle ships.
(function () {
  "use strict";
  var MOUNT = document.getElementById("vcms-theme-designer");
  if (!MOUNT) return;

  var BKEY = "vcms_theme_bundle_v1";
  var FONTS = {
    system: "system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif",
    arial: "Arial,Helvetica,sans-serif",
    arialnarrow: "'Arial Narrow',Arial,sans-serif",
    inter: "Inter,system-ui,Arial,sans-serif",
    georgia: "Georgia,'Times New Roman',serif",
    mono: "ui-monospace,SFMono-Regular,Menlo,monospace"
  };
  var DENSITY = { compact: { h: 42, pad: 12 }, standard: { h: 46, pad: 16 }, spacious: { h: 52, pad: 22 } };
  var ANIM = { none: 0, subtle: 0.6, standard: 1, smooth: 1.35 };

  function hexok(v) { return /^#[0-9A-Fa-f]{6}$/.test(v); }
  function clampN(v, lo, hi) { v = +v; if (isNaN(v)) v = lo; return Math.min(hi, Math.max(lo, v)); }
  function rgb(h) { h = h.slice(1); return [0, 2, 4].map(function (i) { return parseInt(h.substr(i, 2), 16); }); }
  function mix(h, t, w) { var a = rgb(h), b = rgb(t); return "#" + a.map(function (v, i) { return Math.round(v + (b[i] - v) * w).toString(16).padStart(2, "0"); }).join(""); }
  function readable(h) { var c = rgb(h); return (c[0] * 299 + c[1] * 587 + c[2] * 114) / 1000 >= 150 ? "#111827" : "#FFFFFF"; }
  function lum(h) { var c = rgb(h).map(function (v) { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }); return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]; }
  function contrast(a, b) { var l1 = lum(a), l2 = lum(b); return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05); }
  function clone(o) { return JSON.parse(JSON.stringify(o)); }

  var PRESETS = {
    "Vortex Executive (default)": {
      colors: { brand: "#C00000", secondary: "#273142", accent: "#D6A32F", page: "#EEF1F5", surface: "#FFFFFF", ink: "#182230", muted: "#667085", heading: "#101828", line: "#DCE1E8", success: "#15803D", warning: "#B45309", danger: "#B91C1C", info: "#175CD3", sidebar: "#0E131E", sidebarInk: "#B7C0D0", thead: "#151C2C", theadInk: "#FFFFFF", rowAlt: "#F7F8FB" },
      shapes: { btnRadius: 11, inputRadius: 10, cardRadius: 16, modalRadius: 16, borderW: 1, shadow: 0.6, density: "standard" },
      type: { font: "arial", fsBase: 14, fsH: 18, fwH: 800, fwBtn: 800 },
      anim: { level: "standard", tspeed: 220, hover: "lift", press: "scale" }
    },
    "Industrial Navy": {
      colors: { brand: "#175CD3", secondary: "#202B3C", accent: "#00A3A3", page: "#EEF3F8", surface: "#FFFFFF", ink: "#172B4D", muted: "#5B6B85", heading: "#0F2044", line: "#D5DEEA", success: "#0E7C66", warning: "#B7791F", danger: "#C0362C", info: "#175CD3", sidebar: "#111A2E", sidebarInk: "#AEBBD3", thead: "#1B2942", theadInk: "#FFFFFF", rowAlt: "#F4F7FB" },
      shapes: { btnRadius: 10, inputRadius: 10, cardRadius: 14, modalRadius: 14, borderW: 1, shadow: 0.5, density: "standard" },
      type: { font: "system", fsBase: 14, fsH: 18, fwH: 800, fwBtn: 700 },
      anim: { level: "subtle", tspeed: 200, hover: "lift", press: "scale" }
    },
    "Construction Amber": {
      colors: { brand: "#C2410C", secondary: "#29313D", accent: "#1E6F68", page: "#F7F3ED", surface: "#FFFFFF", ink: "#252A32", muted: "#6B6256", heading: "#1F2937", line: "#E3DACF", success: "#3F7A34", warning: "#B45309", danger: "#B4231F", info: "#2563EB", sidebar: "#241B12", sidebarInk: "#CDBFAE", thead: "#33281C", theadInk: "#FFFFFF", rowAlt: "#FBF7F1" },
      shapes: { btnRadius: 9, inputRadius: 9, cardRadius: 12, modalRadius: 14, borderW: 1, shadow: 0.55, density: "spacious" },
      type: { font: "georgia", fsBase: 15, fsH: 19, fwH: 700, fwBtn: 800 },
      anim: { level: "smooth", tspeed: 260, hover: "glow", press: "sink" }
    }
  };
  var DEFAULT_NAME = "Vortex Executive (default)";

  function readBundle() { try { return JSON.parse(localStorage.getItem(BKEY) || "null"); } catch (_) { return null; } }
  function seedBundle() { return { version: 1, active: DEFAULT_NAME, themes: clone(PRESETS) }; }

  var bundle = readBundle() || seedBundle();
  // make sure the 3 presets always exist (recovery)
  Object.keys(PRESETS).forEach(function (n) { if (!bundle.themes[n]) bundle.themes[n] = clone(PRESETS[n]); });
  if (!bundle.themes[bundle.active]) bundle.active = DEFAULT_NAME;

  var activeName = bundle.active;
  var working = clone(bundle.themes[activeName]);
  var savedSnapshot = clone(working);

  /* ---- live apply to the whole page via --vcms-* vars ---- */
  function applyLive(t) {
    // base 6 through the shared appearance engine (same path Save persists)
    if (window.VCMS_APPEARANCE) {
      try {
        window.VCMS_APPEARANCE.applyBrand({
          preset: "custom", primary: t.colors.brand, secondary: t.colors.secondary,
          accent: t.colors.accent, page: t.colors.page, surface: t.colors.surface, ink: t.colors.ink
        });
      } catch (_) {}
    }
    // extended tokens: stash a preview bundle + let the core ext block paint them
    var preview = { version: bundle.version, active: "__preview__", themes: { __preview__: t } };
    try { sessionStorage.setItem("vcms_theme_preview", JSON.stringify(preview)); } catch (_) {}
    paintExtended(t);
    markDirty(); guard(t);
  }

  // Paint the extended vars directly (mirrors core theme-ext so preview is instant).
  function paintExtended(t) {
    var rs = document.documentElement.style, C = t.colors, S = t.shapes, T = t.type, A = t.anim;
    function s(k, v) { if (v) rs.setProperty(k, v); }
    document.documentElement.setAttribute("data-vcms-theme", "on");
    ["ink", "muted", "line", "surface", "page", "secondary", "accent"].forEach(function (k) { if (hexok(C[k])) s("--vcms-" + k, C[k]); });
    if (hexok(C.success)) { s("--vcms-success", C.success); s("--vcms-success-soft", mix(C.success, "#FFFFFF", 0.88)); }
    if (hexok(C.warning)) { s("--vcms-warning", C.warning); s("--vcms-warning-soft", mix(C.warning, "#FFFFFF", 0.88)); }
    if (hexok(C.danger)) { s("--vcms-danger", C.danger); s("--vcms-danger-soft", mix(C.danger, "#FFFFFF", 0.90)); }
    if (hexok(C.info)) { s("--vcms-info", C.info); s("--vcms-info-soft", mix(C.info, "#FFFFFF", 0.90)); }
    if (hexok(C.heading)) s("--vcms-heading", C.heading);
    if (hexok(C.sidebar)) s("--vcms-sidebar-bg", C.sidebar);
    if (hexok(C.sidebarInk)) s("--vcms-sidebar-ink", C.sidebarInk);
    if (hexok(C.thead)) s("--vcms-thead-bg", C.thead);
    if (hexok(C.theadInk)) s("--vcms-thead-ink", C.theadInk);
    if (hexok(C.rowAlt)) s("--vcms-row-alt", C.rowAlt);
    if (hexok(C.brand) && hexok(C.sidebar)) s("--vcms-sidebar-active", mix(C.brand, C.sidebar, 0.35));
    s("--vcms-card-radius", clampN(S.cardRadius, 0, 28) + "px");
    s("--vcms-btn-radius", clampN(S.btnRadius, 0, 22) + "px");
    s("--vcms-input-radius", clampN(S.inputRadius, 0, 22) + "px");
    s("--vcms-modal-radius", clampN(S.modalRadius, 0, 28) + "px");
    s("--vcms-border-w", clampN(S.borderW, 0, 3) + "px");
    s("--vcms-radius", clampN(S.cardRadius, 0, 28) + "px");
    var d = DENSITY[S.density] || DENSITY.standard; s("--vcms-control-h", d.h + "px"); s("--vcms-pad", d.pad + "px");
    if (FONTS[T.font]) s("--vcms-font", FONTS[T.font]);
    s("--vcms-fs-h", clampN(T.fsH, 16, 26) + "px");
    s("--vcms-anim", (A.level in ANIM) ? ANIM[A.level] : 1);
    s("--vcms-tspeed", clampN(A.tspeed, 120, 400) + "ms");
    document.documentElement.setAttribute("data-anim", A.level || "standard");
  }

  function guard(t) {
    var pairs = [[t.colors.ink, t.colors.surface, "Body vs card"], [t.colors.ink, t.colors.page, "Body vs page"], [readable(t.colors.brand), t.colors.brand, "Primary button"], [t.colors.theadInk, t.colors.thead, "Table header"]];
    var bad = pairs.filter(function (p) { return contrast(p[0], p[1]) < 4.5; }).map(function (p) { return p[2]; });
    var b = MOUNT.querySelector("#th-save");
    if (b) { if (bad.length) { b.disabled = true; b.style.opacity = 0.5; b.textContent = "⚠ Fix contrast: " + bad.join(", "); } else { b.disabled = false; b.style.opacity = 1; b.textContent = "Save & apply site-wide"; } }
  }
  function isDirty() { return JSON.stringify(working) !== JSON.stringify(savedSnapshot); }
  function markDirty() { var d = MOUNT.querySelector("#th-dirty"); if (d) d.style.display = isDirty() ? "inline-block" : "none"; }

  /* ---- controls ---- */
  function colorRow(k, label) { return '<div class="thr"><label>' + label + '</label><span class="thc"><input type="text" value="' + working.colors[k] + '" data-hex="' + k + '"><input type="color" value="' + working.colors[k] + '" data-col="' + k + '"></span></div>'; }
  function rangeRow(grp, k, label, lo, hi, step, unit) { return '<div class="thr"><label>' + label + '</label><span class="thc"><input type="range" min="' + lo + '" max="' + hi + '" step="' + (step || 1) + '" value="' + working[grp][k] + '" data-rng="' + grp + '.' + k + '" data-lo="' + lo + '" data-hi="' + hi + '"><b class="thv" id="v-' + grp + '-' + k + '">' + working[grp][k] + (unit || "") + '</b></span></div>'; }
  function segRow(grp, k, label, opts) { return '<div class="thr"><label>' + label + '</label><span class="thseg">' + opts.map(function (o) { return '<button class="' + (working[grp][k] === o[0] ? "on" : "") + '" data-seg="' + grp + "." + k + '" data-val="' + o[0] + '">' + o[1] + "</button>"; }).join("") + "</span></div>"; }
  function selRow(grp, k, label, opts) { return '<div class="thr"><label>' + label + '</label><select data-sel="' + grp + "." + k + '">' + opts.map(function (o) { return '<option value="' + o[0] + '" ' + (String(working[grp][k]) === String(o[0]) ? "selected" : "") + ">" + o[1] + "</option>"; }).join("") + "</select></div>"; }

  function html() {
    return '' +
      '<style>' +
      '#vcms-theme-designer{--a:#C00000}' +
      '.thd-top{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px;align-items:center}' +
      '.thd-top select{flex:1;min-width:150px;min-height:42px;border:1px solid var(--vcms-line);border-radius:9px;padding:0 10px;background:var(--vcms-surface);color:var(--vcms-ink);font-weight:700}' +
      '.thd-chip{border:1px solid var(--vcms-line);background:var(--vcms-surface);color:var(--vcms-ink);border-radius:9px;padding:9px 11px;font-size:12px;font-weight:800;cursor:pointer}' +
      '.thd-chip.warn{color:var(--vcms-danger);border-color:var(--vcms-danger)}' +
      '.thd-grp{border:1px solid var(--vcms-line);border-radius:12px;margin-bottom:10px;overflow:hidden;background:var(--vcms-surface)}' +
      '.thd-grp>summary{cursor:pointer;list-style:none;padding:12px 13px;font-size:12px;font-weight:800;letter-spacing:.05em;text-transform:uppercase;color:var(--vcms-muted)}' +
      '.thd-grp>summary::-webkit-details-marker{display:none}.thd-grp .thb{padding:2px 13px 12px}' +
      '.thr{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:8px 0;border-top:1px solid var(--vcms-line)}' +
      '.thr:first-child{border-top:0}.thr label{font-size:13px;color:var(--vcms-ink);flex:1}' +
      '.thc{display:flex;gap:7px;align-items:center}' +
      '.thc input[type=text]{width:86px;font-family:monospace;font-size:12px;border:1px solid var(--vcms-line);border-radius:7px;padding:6px 7px;background:var(--vcms-surface);color:var(--vcms-ink)}' +
      '.thc input[type=color]{width:38px;height:32px;border:1px solid var(--vcms-line);border-radius:7px;background:none;padding:2px;cursor:pointer}' +
      '.thc input[type=range]{width:130px;accent-color:var(--vcms-brand)}' +
      '.thv{font-size:12px;color:var(--vcms-muted);font-family:monospace;min-width:44px;text-align:right}' +
      '.thseg{display:flex;gap:4px;background:var(--vcms-page);border:1px solid var(--vcms-line);border-radius:9px;padding:3px}' +
      '.thseg button{border:0;background:none;color:var(--vcms-muted);font-size:12px;font-weight:800;padding:6px 9px;border-radius:6px;cursor:pointer}' +
      '.thseg button.on{background:var(--vcms-brand);color:#fff}' +
      '.thd-grp select{border:1px solid var(--vcms-line);border-radius:8px;padding:6px 8px;background:var(--vcms-surface);color:var(--vcms-ink);font-size:13px;min-width:130px}' +
      '.thsub{font-size:11px;font-weight:800;letter-spacing:.06em;text-transform:uppercase;color:var(--vcms-muted);margin:10px 0 2px}' +
      '.thd-actions{display:flex;gap:8px;margin-top:12px}' +
      '.thd-actions .b{flex:1}' +
      '.thd-note{font-size:11px;color:var(--vcms-muted);margin-top:8px;line-height:1.5}' +
      '#th-dirty{display:none;width:8px;height:8px;border-radius:50%;background:#F5A623;margin-right:2px}' +
      '</style>' +
      '<div class="settings-card mb-8">' +
      '<div class="flex items-start gap-3 mb-3"><div class="flex-1"><p class="font-bold text-gray-900 text-sm">Custom theme designer</p><p class="text-xs text-gray-500 mt-1">Applied to the whole website. Status green / amber / red and role permissions stay fixed. Supervisors do not see these controls.</p></div><span class="vcms-status vcms-status-neutral">Admin</span></div>' +
      '<div class="thd-top">' +
      '<select id="th-select"></select>' +
      '<button class="thd-chip" id="th-dup">Duplicate</button>' +
      '<button class="thd-chip" id="th-ren">Rename</button>' +
      '<button class="thd-chip warn" id="th-del">Delete</button>' +
      '</div>' +
      '<details class="thd-grp" open><summary>Colours</summary><div class="thb" id="th-colours"></div></details>' +
      '<details class="thd-grp"><summary>Shapes &amp; density</summary><div class="thb" id="th-shapes"></div></details>' +
      '<details class="thd-grp"><summary>Typography</summary><div class="thb" id="th-type"></div></details>' +
      '<details class="thd-grp"><summary>Animation</summary><div class="thb" id="th-anim"></div></details>' +
      '<div class="thd-actions">' +
      '<button class="vcms-btn vcms-btn-tertiary b" id="th-restore">↺ Restore defaults</button>' +
      '<button class="vcms-btn vcms-btn-tertiary b" id="th-cancel">✕ Cancel</button>' +
      '</div>' +
      '<button class="vcms-btn vcms-btn-primary w-full" id="th-save" style="margin-top:8px"><span id="th-dirty"></span>Save &amp; apply site-wide</button>' +
      '<p class="thd-note" id="th-note"></p>' +
      '</div>';
  }

  function renderControls() {
    MOUNT.querySelector("#th-colours").innerHTML =
      '<p class="thsub">Brand &amp; surfaces</p>' + colorRow("brand", "Primary / brand") + colorRow("secondary", "Secondary") + colorRow("accent", "Accent") + colorRow("page", "Page background") + colorRow("surface", "Card &amp; panel") +
      '<p class="thsub">Text</p>' + colorRow("heading", "Headings") + colorRow("ink", "Body text") + colorRow("muted", "Muted text") + colorRow("line", "Borders &amp; dividers") +
      '<p class="thsub">Navigation &amp; tables</p>' + colorRow("sidebar", "Sidebar / header") + colorRow("sidebarInk", "Sidebar text") + colorRow("thead", "Table header") + colorRow("rowAlt", "Alternating row") +
      '<p class="thsub">Status</p>' + colorRow("success", "Success") + colorRow("warning", "Warning") + colorRow("danger", "Error") + colorRow("info", "Information");
    MOUNT.querySelector("#th-shapes").innerHTML =
      rangeRow("shapes", "btnRadius", "Button radius", 0, 22, 1, "px") + rangeRow("shapes", "inputRadius", "Input radius", 0, 22, 1, "px") + rangeRow("shapes", "cardRadius", "Card radius", 0, 28, 1, "px") + rangeRow("shapes", "modalRadius", "Modal radius", 0, 28, 1, "px") + rangeRow("shapes", "borderW", "Border thickness", 0, 3, 1, "px") + rangeRow("shapes", "shadow", "Shadow intensity", 0, 1.4, 0.05, "") + segRow("shapes", "density", "Density", [["compact", "Compact"], ["standard", "Standard"], ["spacious", "Spacious"]]);
    MOUNT.querySelector("#th-type").innerHTML =
      selRow("type", "font", "Font family", [["system", "System UI"], ["arial", "Arial"], ["arialnarrow", "Arial Narrow"], ["inter", "Inter"], ["georgia", "Georgia (serif)"], ["mono", "Monospace"]]) + rangeRow("type", "fsBase", "Base font size", 12, 17, 1, "px") + rangeRow("type", "fsH", "Heading size", 16, 26, 1, "px") + selRow("type", "fwH", "Heading weight", [[600, "Semi-bold"], [700, "Bold"], [800, "Extra-bold"]]) + selRow("type", "fwBtn", "Button / label weight", [[600, "Semi-bold"], [700, "Bold"], [800, "Extra-bold"]]);
    MOUNT.querySelector("#th-anim").innerHTML =
      segRow("anim", "level", "Animation level", [["none", "Off"], ["subtle", "Subtle"], ["standard", "Standard"], ["smooth", "Smooth"]]) + rangeRow("anim", "tspeed", "Transition speed", 120, 400, 10, "ms") + selRow("anim", "hover", "Card hover", [["none", "None"], ["lift", "Lift"], ["glow", "Glow"]]) + selRow("anim", "press", "Button press", [["none", "None"], ["scale", "Scale"], ["sink", "Sink"]]) +
      '<p class="thd-note">The device Reduce-Motion setting always overrides this and disables animation.</p>';
  }

  function bindOnce() {
    MOUNT.addEventListener("input", function (e) {
      var el = e.target;
      if (el.dataset.hex !== undefined) { var v = el.value.toUpperCase(); if (hexok(v)) { working.colors[el.dataset.hex] = v; var cp = MOUNT.querySelector('[data-col="' + el.dataset.hex + '"]'); if (cp) cp.value = v; applyLive(working); } }
      else if (el.dataset.col !== undefined) { working.colors[el.dataset.col] = el.value.toUpperCase(); var tx = MOUNT.querySelector('[data-hex="' + el.dataset.col + '"]'); if (tx) tx.value = el.value.toUpperCase(); applyLive(working); }
      else if (el.dataset.rng !== undefined) { var p = el.dataset.rng.split("."), val = clampN(el.value, +el.dataset.lo, +el.dataset.hi); working[p[0]][p[1]] = val; var lbl = MOUNT.querySelector("#v-" + p[0] + "-" + p[1]); if (lbl) lbl.textContent = val + (p[1].indexOf("Radius") > -1 || p[1] === "borderW" || p[1].indexOf("fs") === 0 ? "px" : (p[1] === "tspeed" ? "ms" : "")); applyLive(working); }
    });
    MOUNT.addEventListener("change", function (e) {
      var el = e.target;
      if (el.dataset.sel !== undefined) { var p = el.dataset.sel.split("."); var v = el.value; working[p[0]][p[1]] = isNaN(+v) ? v : +v; applyLive(working); }
    });
    MOUNT.addEventListener("click", function (e) {
      var el = e.target.closest("[data-seg],button"); if (!el) return;
      if (el.dataset.seg !== undefined) { var p = el.dataset.seg.split("."); working[p[0]][p[1]] = el.dataset.val; [].forEach.call(el.parentNode.children, function (b) { b.classList.remove("on"); }); el.classList.add("on"); applyLive(working); return; }
      switch (el.id) {
        case "th-dup": duplicateTheme(); break;
        case "th-ren": renameTheme(); break;
        case "th-del": deleteTheme(); break;
        case "th-restore": restoreDefaults(); break;
        case "th-cancel": cancelChanges(); break;
        case "th-save": saveTheme(); break;
      }
    });
    MOUNT.querySelector("#th-select").addEventListener("change", function (e) {
      if (isDirty() && !confirm("Discard unsaved changes and switch theme?")) { renderSelect(); return; }
      activeName = e.target.value; working = clone(bundle.themes[activeName]); savedSnapshot = clone(working);
      renderControls(); applyLive(working);
    });
  }

  function renderSelect() {
    MOUNT.querySelector("#th-select").innerHTML = Object.keys(bundle.themes).map(function (n) { return '<option value="' + n + '" ' + (n === activeName ? "selected" : "") + ">" + n + (n === DEFAULT_NAME ? " ★" : "") + "</option>"; }).join("");
  }
  function persist() { try { localStorage.setItem(BKEY, JSON.stringify(bundle)); } catch (_) {} }

  function duplicateTheme() {
    var name = prompt("Name for the duplicated theme:", activeName.replace(/\s*\(default\)/, "") + " copy"); if (!name) return;
    name = name.slice(0, 40); if (bundle.themes[name]) { alert("A theme with that name exists."); return; }
    bundle.themes[name] = clone(working); activeName = name; working = clone(bundle.themes[name]); savedSnapshot = clone(working);
    persist(); renderSelect(); renderControls(); applyLive(working);
  }
  function renameTheme() {
    if (PRESETS[activeName]) { alert("Preset themes cannot be renamed. Duplicate to make an editable copy."); return; }
    var name = prompt("Rename theme:", activeName); if (!name || name === activeName) return; name = name.slice(0, 40);
    if (bundle.themes[name]) { alert("That name is taken."); return; }
    bundle.themes[name] = bundle.themes[activeName]; delete bundle.themes[activeName]; if (bundle.active === activeName) bundle.active = name; activeName = name;
    persist(); renderSelect();
  }
  function deleteTheme() {
    if (PRESETS[activeName]) { alert("Preset themes cannot be deleted. Duplicate it first."); return; }
    if (!confirm('Delete theme "' + activeName + '"? This cannot be undone.')) return;
    delete bundle.themes[activeName]; activeName = DEFAULT_NAME; working = clone(bundle.themes[activeName]); savedSnapshot = clone(working);
    persist(); renderSelect(); renderControls(); applyLive(working);
  }
  function restoreDefaults() {
    if (!confirm("Reset the current theme to the Vortex Executive default values?")) return;
    working = clone(PRESETS[DEFAULT_NAME]); renderControls(); applyLive(working);
  }
  function cancelChanges() {
    working = clone(savedSnapshot); renderControls(); applyLive(working);
    note("Unsaved changes discarded.");
  }
  function note(m) { var n = MOUNT.querySelector("#th-note"); if (n) n.textContent = m; }

  function saveTheme() {
    var C = working.colors;
    if (contrast(C.ink, C.surface) < 4.5 || contrast(readable(C.brand), C.brand) < 4.5) { alert("This combination is not readable enough to save. Adjust text or background colour."); return; }
    if (!confirm('Apply "' + activeName + '" to the whole site for all users?\n\nColours apply for everyone. Shapes, fonts and animation apply on your devices now and for all users once the backend theme update is live. Safety colours and permissions are unchanged.')) return;
    bundle.themes[activeName] = clone(working); bundle.active = activeName; bundle.version = (bundle.version || 1) + 1;
    persist(); savedSnapshot = clone(working); markDirty();
    var payload = { preset: "custom", primary: C.brand, secondary: C.secondary, accent: C.accent, page: C.page, surface: C.surface, ink: C.ink };
    if (window.VCMS_APPEARANCE) { try { window.VCMS_APPEARANCE.setBrand(payload); } catch (_) {} }
    var btn = MOUNT.querySelector("#th-save");
    function done(msg) { note(msg); if (window.VCMS_UI && VCMS_UI.toast) VCMS_UI.toast("Theme saved · v" + bundle.version, "success"); }
    if (typeof vmmsApi === "function") {
      if (window.VCMS_UI) VCMS_UI.setLoading(btn, true, "Saving…");
      vmmsApi("/api/v1/appearance", { method: "PATCH", body: JSON.stringify(payload) })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (d) { if (d && window.VCMS_APPEARANCE) VCMS_APPEARANCE.setBrand(d); done("Saved & applied site-wide · version v" + bundle.version + ". Cached devices refresh on next open."); })
        .catch(function () { done("Saved on this device · colour sync to server will retry."); })
        .finally(function () { if (window.VCMS_UI) VCMS_UI.setLoading(btn, false); paintExtended(working); });
    } else { done("Saved on this device · version v" + bundle.version + "."); }
  }

  /* ---- admin gate, then render ---- */
  function start() {
    var old = document.getElementById("company-theme"); if (old) old.style.display = "none";
    MOUNT.innerHTML = html();
    renderSelect(); renderControls(); bindOnce(); applyLive(working); savedSnapshot = clone(working); markDirty();
    note("Active theme: " + activeName + " · saved version v" + (bundle.version || 1));
  }

  function gate() {
    if (typeof vmmsApi !== "function") { setTimeout(gate, 300); return; }
    vmmsApi("/api/v1/me").then(function (r) { return r.ok ? r.json() : null; }).then(function (me) {
      var full = window.isFull ? isFull(me && me.role) : (me && me.role === "admin");
      if (me && full) start(); else { MOUNT.style.display = "none"; }
    }).catch(function () { MOUNT.style.display = "none"; });
  }
  gate();
})();
