// Apply the cached company theme before page CSS is painted.
(function () {
  "use strict";
  try {
    var raw = localStorage.getItem("vcms_company_appearance_v1");
    var saved = raw ? JSON.parse(raw) : null;
    if (!saved || !/^#[0-9a-f]{6}$/i.test(saved.primary || "")) return;

    function rgb(hex) {
      hex = hex.slice(1);
      return [0, 2, 4].map(function (i) { return parseInt(hex.slice(i, i + 2), 16); });
    }
    function mix(hex, target, weight) {
      var a = rgb(hex), b = rgb(target);
      return "#" + a.map(function (value, i) {
        return Math.round(value + (b[i] - value) * weight).toString(16).padStart(2, "0");
      }).join("");
    }
    function valid(value, fallback) {
      return /^#[0-9a-f]{6}$/i.test(value || "") ? value : fallback;
    }

    var primary = saved.primary;
    var secondary = valid(saved.secondary, "#273142");
    var page = valid(saved.page, "#F2F4F7");
    var surface = valid(saved.surface, "#FFFFFF");
    var ink = valid(saved.ink, "#182230");
    var c = rgb(primary);
    var onBrand = (c[0] * 299 + c[1] * 587 + c[2] * 114) / 1000 >= 155 ? "#111827" : "#FFFFFF";
    var root = document.documentElement.style;
    var values = {
      "--vcms-brand": primary,
      "--vcms-brand-dark": mix(primary, "#000000", 0.22),
      "--vcms-brand-hover": mix(primary, "#000000", 0.13),
      "--vcms-brand-soft": mix(primary, "#FFFFFF", 0.90),
      "--vcms-brand-border": mix(primary, "#FFFFFF", 0.62),
      "--vcms-on-brand": onBrand,
      "--vcms-secondary": secondary,
      "--vcms-accent": valid(saved.accent, "#D6A32F"),
      "--vcms-page": page,
      "--vcms-surface": surface,
      "--vcms-ink": ink,
      "--brand": primary,
      "--brand2": mix(primary, "#000000", 0.22),
      "--bg": page,
      "--ink": ink,
      "--line": mix(secondary, "#FFFFFF", 0.82)
    };
    Object.keys(values).forEach(function (name) { root.setProperty(name, values[name]); });
    document.documentElement.setAttribute("data-brand", saved.preset || "custom");
    document.documentElement.setAttribute("data-vcms-theme-boot", "ready");
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = values["--vcms-brand-dark"];
  } catch (_) { /* The full theme loader will use safe defaults. */ }
})();
