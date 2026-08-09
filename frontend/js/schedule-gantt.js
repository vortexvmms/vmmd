(function () {
  "use strict";

  var activities = [], baselines = [], wbs = [], canEdit = false;

  function e(v) {
    return String(v == null ? "" : v).replace(/[&<>"']/g, function (c) {
      return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];
    });
  }
  function pid() { return vcmsProjectContext.requireActiveId(); }
  function day(v) { return new Date(v + "T00:00:00Z"); }
  function iso(v) { return v.toISOString().slice(0, 10); }
  function diff(a, b) { return Math.round((day(b) - day(a)) / 86400000); }
  function inRange(value, start, finish) { return value >= start && value <= finish; }

  function dateRange(start, finish) {
    var result = [], cursor = day(start), end = day(finish);
    while (cursor <= end) {
      result.push(iso(cursor));
      cursor.setUTCDate(cursor.getUTCDate() + 1);
    }
    return result;
  }

  function monthGroups(dates) {
    var groups = [];
    dates.forEach(function (value) {
      var key = value.slice(0, 7), last = groups[groups.length - 1];
      if (!last || last.key !== key) {
        var date = day(value);
        groups.push({key:key, label:date.toLocaleDateString("en-GB", {month:"short", year:"numeric", timeZone:"UTC"}), count:1});
      } else last.count += 1;
    });
    return groups;
  }

  async function load() {
    await vcmsProjectContext.init();
    var id = pid(), rs = await Promise.all([
      vmmsApi("/api/v1/me"),
      vmmsApi("/api/v1/schedule/activities?project_id=" + encodeURIComponent(id)),
      vmmsApi("/api/v1/schedule/baselines?project_id=" + encodeURIComponent(id)),
      vmmsApi("/api/v1/schedule/wbs?project_id=" + encodeURIComponent(id))
    ]);
    var me = await rs[0].json();
    canEdit = isFull(me.role) || isManager(me.role);
    activities = (await rs[1].json()).activities || [];
    baselines = (await rs[2].json()).baselines || [];
    wbs = (await rs[3].json()).nodes || [];
    document.getElementById("calculate-schedule").classList.toggle("hidden", !canEdit);
    document.getElementById("create-baseline").classList.toggle("hidden", !canEdit || !activities.some(function (a) { return a.early_start; }));
    var select = document.getElementById("baseline-select"), current = select.value;
    select.innerHTML = '<option value="">None</option>' + baselines.map(function (b) {
      return '<option value="' + e(b.id) + '">' + e(b.name) + " — " + e(b.data_date) + "</option>";
    }).join("");
    if (baselines.some(function (b) { return b.id === current; })) select.value = current;
    render();
  }

  function render() {
    var rows = activities.filter(function (a) { return a.early_start && a.early_finish; });
    document.getElementById("gantt-empty").classList.toggle("hidden", rows.length > 0);
    if (!rows.length) { document.getElementById("gantt-chart").innerHTML = ""; return; }

    var selected = baselines.find(function (b) { return b.id === document.getElementById("baseline-select").value; });
    var snapshots = {}, wbsCodes = {};
    if (selected) (selected.baseline_activity_snapshots || []).forEach(function (x) { snapshots[x.activity_id] = x; });
    wbs.forEach(function (node) { wbsCodes[node.id] = node.code; });

    var starts = rows.map(function (a) { return a.early_start; });
    var finishes = rows.map(function (a) { return a.early_finish; });
    Object.keys(snapshots).forEach(function (id) {
      var snapshot = snapshots[id];
      if (snapshot.early_start) starts.push(snapshot.early_start);
      if (snapshot.early_finish) finishes.push(snapshot.early_finish);
    });
    var min = starts.sort()[0], max = finishes.sort().slice(-1)[0], dates = dateRange(min, max);
    var weekdays = ["S","M","T","W","T","F","S"];

    var fixed = '<th rowspan="3" class="fixed-head sticky-col col-wbs">WBS</th>' +
      '<th rowspan="3" class="fixed-head sticky-col col-code">Activity ID</th>' +
      '<th rowspan="3" class="fixed-head sticky-col col-name">Activity</th>' +
      '<th rowspan="3" class="fixed-head sticky-col col-start">Start</th>' +
      '<th rowspan="3" class="fixed-head sticky-col col-finish">Finish</th>';
    var months = monthGroups(dates).map(function (group) {
      return '<th class="month-head" colspan="' + group.count + '">' + e(group.label) + "</th>";
    }).join("");
    var numbers = dates.map(function (value) {
      var weekend = [0,6].indexOf(day(value).getUTCDay()) >= 0;
      return '<th class="gantt-day' + (weekend ? " weekend" : "") + '">' + value.slice(8) + "</th>";
    }).join("");
    var letters = dates.map(function (value) {
      var n = day(value).getUTCDay(), weekend = n === 0 || n === 6;
      return '<th class="gantt-day' + (weekend ? " weekend" : "") + '">' + weekdays[n] + "</th>";
    }).join("");

    var body = rows.map(function (activity) {
      var snapshot = snapshots[activity.id];
      var milestone = activity.activity_type === "milestone" || (Number(activity.duration_days) === 0 && activity.early_start === activity.early_finish);
      var cells = dates.map(function (value) {
        var n = day(value).getUTCDay(), weekend = n === 0 || n === 6;
        var active = inRange(value, activity.early_start, activity.early_finish);
        var baseline = snapshot && snapshot.early_start && snapshot.early_finish && inRange(value, snapshot.early_start, snapshot.early_finish);
        var current = "";
        if (milestone && value === activity.early_start) current = '<span class="gantt-milestone" title="Milestone"></span>';
        else if (active) current = '<span class="gantt-current' + (activity.is_critical ? " critical" : "") + (value === activity.early_start ? " bar-start" : "") + (value === activity.early_finish ? " bar-end" : "") + '" title="' + e(activity.is_critical ? "Critical activity" : "Current schedule") + '"></span>';
        return '<td class="gantt-day' + (weekend ? " weekend" : "") + '"><div class="gantt-track">' +
          (baseline ? '<span class="gantt-baseline" title="Baseline"></span>' : "") + current + "</div></td>";
      }).join("");
      return '<tr><td class="fixed-cell sticky-col col-wbs" title="' + e(wbsCodes[activity.wbs_id] || "") + '">' + e(wbsCodes[activity.wbs_id] || "—") + '</td>' +
        '<td class="fixed-cell sticky-col col-code"><strong>' + e(activity.code) + '</strong></td>' +
        '<td class="fixed-cell sticky-col col-name" title="' + e(activity.name) + '">' + e(activity.name) + '</td>' +
        '<td class="fixed-cell sticky-col col-start">' + e(activity.early_start) + '</td>' +
        '<td class="fixed-cell sticky-col col-finish">' + e(activity.early_finish) + '</td>' + cells + "</tr>";
    }).join("");

    document.getElementById("gantt-chart").innerHTML = '<table class="gantt-table"><thead><tr>' + fixed + months +
      '</tr><tr>' + numbers + '</tr><tr>' + letters + '</tr></thead><tbody>' + body + "</tbody></table>";
  }

  async function calculate() {
    var response = await vmmsApi("/api/v1/schedule/calculate", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({project_id:pid()})});
    if (!response.ok) { var data = await response.json(); return alert(data.detail || "Calculation failed"); }
    await load();
  }
  async function baseline() {
    var name = prompt("Baseline name", "Original Baseline"); if (!name) return;
    var dataDate = prompt("Data date (YYYY-MM-DD)", new Date().toISOString().slice(0,10)); if (!dataDate) return;
    var response = await vmmsApi("/api/v1/schedule/baselines", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({project_id:pid(), name:name, data_date:dataDate})});
    if (!response.ok) return alert("Could not create baseline");
    await load();
  }
  function show() {
    ["wbs-panel","activities-panel","logic-panel","calendars-panel","resources-panel"].forEach(function (id) { document.getElementById(id).classList.add("hidden"); });
    document.getElementById("gantt-panel").classList.remove("hidden");
    document.querySelectorAll(".schedule-tabs button").forEach(function (button) { button.classList.remove("active"); });
    document.getElementById("tab-gantt").classList.add("active");
    document.getElementById("add").classList.add("hidden");
    load();
  }

  document.getElementById("tab-gantt").onclick = show;
  document.getElementById("calculate-schedule").onclick = calculate;
  document.getElementById("create-baseline").onclick = baseline;
  document.getElementById("baseline-select").onchange = render;
  window.addEventListener("vcms:project-changed", load);
  load();
  var progressScript = document.createElement("script");
  progressScript.src = "js/schedule-progress.js";
  document.body.appendChild(progressScript);
})();
