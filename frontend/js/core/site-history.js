(function () {
  "use strict";

  function todayIso() {
    var d = new Date();
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
  }

  function isPastDate(value) {
    return /^\d{4}-\d{2}-\d{2}$/.test(value || "") && value < todayIso();
  }

  function forOperationalDate(sites, date, referencedIds, options) {
    var rows = Array.isArray(sites) ? sites : [];
    var refs = new Set((referencedIds || []).filter(Boolean).map(String));
    var includeAllHistorical = !!(options && options.includeAllHistorical);
    if (!isPastDate(date)) return rows.filter(function (site) { return site.status === "active"; });
    if (includeAllHistorical) return rows.slice();
    return rows.filter(function (site) { return site.status === "active" || refs.has(String(site.id)); });
  }

  function label(site) {
    var suffix = site && site.status && site.status !== "active" ? " (Archived)" : "";
    return String((site && site.site_name) || "") + suffix;
  }

  window.VCMS_SITES = Object.freeze({
    isPastDate: isPastDate,
    forOperationalDate: forOperationalDate,
    label: label
  });
})();
