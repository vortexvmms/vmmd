(function () {
  "use strict";
  if (window.__VCMS_WORKFLOW__) return;
  window.__VCMS_WORKFLOW__ = true;
  var file = (location.pathname.split("/").pop() || "").toLowerCase();
  var daily = [
    { file: "request.html", label: "Request" },
    { file: "allocation.html", label: "Allocation" },
    { file: "attendance.html", label: "Attendance" },
    { file: "verify.html", label: "End-time" },
    { file: "timesheet.html", label: "Timesheet" }
  ];
  var progress = [
    { file: "camera.html", label: "Photos" },
    { file: "dpr.html", label: "DPR" },
    { file: "dprlist.html", label: "History" },
    { file: "site-dashboard.html", label: "Review" }
  ];
  var procurement = [
    { file: "pr-dashboard.html", label: "PR Board" },
    { file: "pr-new.html", label: "New PR" },
    { file: "pr-import.html", label: "Import PDFs" }
  ];
  var aliases = {
    "camera-photos.html": "camera.html",
    "resource-summary.html": "site-dashboard.html",
    "pr-directory.html": "pr-dashboard.html"
  };
  var activeFile = aliases[file] || file;
  var flow = daily.some(function (x) { return x.file === activeFile; }) ? daily
    : progress.some(function (x) { return x.file === activeFile; }) ? progress
    : procurement.some(function (x) { return x.file === activeFile; }) ? procurement
    : null;
  if (!flow) return;

  var params = new URLSearchParams(location.search);
  var saved = {};
  try { saved = JSON.parse(localStorage.getItem("vcms_work_context") || "{}"); } catch (_) {}
  var context = {
    date: params.get("date") || saved.date || "",
    site_id: params.get("site_id") || saved.site_id || "",
    site_name: params.get("site_name") || saved.site_name || ""
  };
  function url(target) {
    var query = new URLSearchParams();
    if (context.date) query.set("date", context.date);
    if (context.site_id) query.set("site_id", context.site_id);
    if (context.site_name) query.set("site_name", context.site_name);
    return target + (query.toString() ? "?" + query.toString() : "");
  }
  function syncNative() {
    setTimeout(function () {
      var dateInput = document.getElementById("date");
      var siteInput = document.getElementById("site");
      if (dateInput && context.date && dateInput.value !== context.date) {
        dateInput.value = context.date;
        dateInput.dispatchEvent(new Event("change", { bubbles: true }));
      }
      if (siteInput && (context.site_id || context.site_name)) {
        var option = Array.from(siteInput.options || []).find(function (item) {
          return String(item.value) === String(context.site_id)
            || item.textContent.trim() === context.site_name;
        });
        if (option && siteInput.value !== option.value) {
          siteInput.value = option.value;
          siteInput.dispatchEvent(new Event("change", { bubbles: true }));
        }
      }
    }, 700);
  }
  function save() {
    try { localStorage.setItem("vcms_work_context", JSON.stringify(context)); } catch (_) {}
    document.querySelectorAll(".vcms-flow-step").forEach(function (anchor) {
      anchor.href = url(anchor.dataset.file);
    });
    syncNative();
  }
  function install() {
    var main = document.querySelector("main");
    if (!main || document.querySelector(".vcms-flowbar")) return;
    var index = flow.findIndex(function (x) { return x.file === activeFile; });
    var title = flow === daily ? "Daily operations"
      : flow === progress ? "Site progress" : "Procurement";
    var section = document.createElement("section");
    section.className = "vcms-flowbar";
    section.setAttribute("aria-label", "Workflow context");
    var steps = flow.map(function (step, i) {
      var state = i < index ? " done" : i === index ? " current" : "";
      return '<a data-file="' + step.file + '" class="vcms-flow-step' + state
        + '" href="' + url(step.file) + '"><span>' + (i < index ? "✓" : i + 1)
        + '</span>' + step.label + '</a>';
    }).join("");
    section.innerHTML = '<div class="vcms-flow-title"><strong>' + title
      + '</strong><small>Same date and site throughout this workflow</small></div>'
      + '<div class="vcms-flow-context"><label>Date<input id="vcms-context-date" type="date" value="'
      + context.date + '"></label><label>Site<select id="vcms-context-site">'
      + '<option value="">All / choose site</option></select></label></div>'
      + '<nav class="vcms-flow-steps">' + steps + '</nav>';
    main.parentNode.insertBefore(section, main);
    if (document.getElementById("date") && document.getElementById("site")) {
      section.classList.add("native-context");
    }
    bindControls(section);
  }
  function bindControls(section) {
    var dateInput = section.querySelector("#vcms-context-date");
    var siteInput = section.querySelector("#vcms-context-site");
    dateInput.addEventListener("change", function () {
      context.date = dateInput.value;
      save();
    });
    siteInput.addEventListener("change", function () {
      var option = siteInput.options[siteInput.selectedIndex];
      context.site_id = siteInput.value;
      context.site_name = option && option.dataset.name || "";
      save();
    });
    setTimeout(function () {
      if (context.date) return;
      var nativeDate = document.getElementById("date");
      context.date = nativeDate && nativeDate.value
        ? nativeDate.value : new Date().toLocaleDateString("en-CA");
      dateInput.value = context.date;
      save();
    }, 800);
    bindNativeControls(dateInput, siteInput);
    loadSites(siteInput);
  }
  function bindNativeControls(dateInput, siteInput) {
    var nativeDate = document.getElementById("date");
    var nativeSite = document.getElementById("site");
    if (!nativeDate || !nativeSite) return;
    nativeDate.addEventListener("change", function () {
      context.date = nativeDate.value;
      dateInput.value = context.date;
      save();
    });
    nativeSite.addEventListener("change", function () {
      var option = nativeSite.options[nativeSite.selectedIndex];
      context.site_id = nativeSite.value;
      context.site_name = option ? option.textContent.trim() : "";
      var match = Array.from(siteInput.options).find(function (item) {
        return item.value === context.site_id || item.dataset.name === context.site_name;
      });
      if (match) siteInput.value = match.value;
      save();
    });
  }
  function loadSites(siteInput) {
    vmmsApi("/api/v1/sites").then(function (response) {
      return response.ok ? response.json() : [];
    }).then(function (rows) {
      rows.filter(function (site) { return site.status === "active"; })
        .sort(function (a, b) {
          return (a.site_name || "").localeCompare(b.site_name || "");
        }).forEach(function (site) {
          var option = document.createElement("option");
          option.value = site.id;
          option.dataset.name = site.site_name;
          option.textContent = site.site_name;
          siteInput.appendChild(option);
        });
      selectSavedSite(siteInput);
    }).catch(syncNative);
  }
  function selectSavedSite(siteInput) {
    var match = Array.from(siteInput.options).find(function (option) {
      return String(option.value) === String(context.site_id)
        || option.dataset.name === context.site_name;
    });
    if (match) {
      siteInput.value = match.value;
      context.site_id = match.value;
      context.site_name = match.dataset.name;
    }
    save();
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", install, { once: true });
  } else {
    install();
  }
})();
