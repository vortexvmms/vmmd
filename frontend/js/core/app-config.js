// ---- Role tiers (Rev 6) — shared by all pages ----
window.VMMS_TIER = {
  full: ["admin", "general_manager", "operation_manager", "hr_assistant"],
  manager: ["main_sup", "wshc_lead"],
  supervisor: ["site_sup", "safety_sup", "wshc", "logistics_sup"],
  payroll: ["payroll"],
};
window.isFull = function (r) { return VMMS_TIER.full.indexOf(r) !== -1; };
window.isManager = function (r) { return VMMS_TIER.manager.indexOf(r) !== -1; };
window.isSupervisor = function (r) { return VMMS_TIER.supervisor.indexOf(r) !== -1; };
window.isCoordinator = function (r) { return isFull(r) || isManager(r); };  // can broadcast messages

// VCMS configuration
window.VMMS_CONFIG = {
  BACKEND_URL: "https://vmms-backend-sg.onrender.com",
  SUPABASE_URL: "https://lqnbdemtgkermhaqfboh.supabase.co",
  SUPABASE_PUBLISHABLE: "sb_publishable_GV2oQS2wP2ltMeg2Teh1Rw_qT3lLGno"
};

// ---- Brand colour grading (applies on every page) ----
// This file loads right after the Tailwind CDN, so overriding the "red"
// ramp here re-colours all bg-red-* / text-red-* utilities app-wide with
// no per-page edits. One unified brand red = #C00000.
if (window.tailwind) {
  tailwind.config = {
    theme: { extend: { colors: { red: {
      50:  "#FDECEC",
      100: "#F9D2D2",
      200: "#F1A3A3",
      300: "#E76F6F",
      400: "#D83C3C",
      500: "#CE1414",
      600: "#C00000",
      700: "#C00000",   // primary buttons + accents  → Vortex brand red
      800: "#A00000",   // hover / darker
      900: "#8A0000",   // deepest (e.g. logout)
      950: "#6E0000"
    } } } }
  };
}

// Header bars sit one shade darker than the brand buttons, for hierarchy.
// (Higher specificity than the utility class, so no !important needed.)
(function () {
  var s = document.createElement("style");
  s.textContent = "header.bg-red-700{background-color:#A00000}";
  document.head.appendChild(s);
})();

