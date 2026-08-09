(function () {
  "use strict";
  function install() {
    document.body.classList.add("schedule-workspace");
    var tabs = {
      "tab-activities": "Activities",
      "tab-logic": "Relationships",
      "tab-gantt": "Activities & Gantt",
    };
    Object.keys(tabs).forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.textContent = tabs[id];
    });

    var wbs = document.getElementById("wbs-panel");
    if (wbs && !wbs.querySelector(".planner-toolbar")) {
      wbs.insertAdjacentHTML("afterbegin", '<div class="planner-toolbar"><h2>Work Breakdown Structure</h2><span class="muted">Select a row; double-click to edit</span></div>');
      var addWbs = document.getElementById("add");
      if (addWbs) {
        var addWbsHidden = addWbs.classList.contains("hidden");
        addWbs.textContent = "+ WBS";
        addWbs.className = "primary" + (addWbsHidden ? " hidden" : "");
        wbs.querySelector(".planner-toolbar").appendChild(addWbs);
      }
    }
    var tree = document.getElementById("tree");
    if (tree && !document.getElementById("wbs-grid-body")) {
      tree.innerHTML = '<div class="wbs-grid-head"><div></div><div>WBS Code</div><div>WBS Name</div><div>Level</div><div>Actions</div></div><div id="wbs-grid-body"></div>';
    }

    var panel = document.getElementById("activities-panel");
    if (panel) {
      var card = panel.firstElementChild;
      var oldHead = card && card.firstElementChild;
      if (oldHead) {
        var add = document.getElementById("add-activity");
        var toolbar = document.createElement("div");
        toolbar.className = "planner-toolbar";
        toolbar.innerHTML = '<h2>Activities &amp; Milestones</h2><span class="muted">Select a row; double-click to edit</span>';
        if (add) {
          var addHidden = add.classList.contains("hidden");
          add.textContent = "+ Activity";
          add.className = "primary" + (addHidden ? " hidden" : "");
          toolbar.appendChild(add);
        }
        oldHead.replaceWith(toolbar);
      }
      var headings = ["Activity ID","Type","Activity Name","WBS","Original Duration","Start","Finish","Status","Complete",""];
      var row = document.querySelector("#activities-table thead tr");
      if (row) row.innerHTML = headings.map(function (h) { return "<th>" + h + "</th>"; }).join("");
      if (card) { card.classList.remove("bg-white","rounded-2xl","p-4"); }
    }
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", install);
  else install();
})();
