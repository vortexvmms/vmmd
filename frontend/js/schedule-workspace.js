(function () {
  "use strict";
  function e(v) { return String(v == null ? "" : v).replace(/[&<>"']/g, function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];}); }
  function pid() { return window.vcmsProjectContext && vcmsProjectContext.requireActiveId(); }

  function nextWbsCode(parentCode) {
    var codes = Array.from(document.querySelectorAll("#wbs-grid-body .wbs-code")).map(function(x){ return x.textContent.trim(); });
    if (!parentCode) {
      var top = codes.filter(function(x){ return /^WBS-\d+$/.test(x); }).map(function(x){ return Number(x.slice(4)); });
      return "WBS-" + ((top.length ? Math.max.apply(Math, top) : 0) + 1);
    }
    var prefix = parentCode + ".", nums = codes.filter(function(x){ return x.indexOf(prefix) === 0 && x.slice(prefix.length).indexOf(".") < 0; }).map(function(x){ return Number(x.slice(prefix.length)) || 0; });
    return prefix + ((nums.length ? Math.max.apply(Math, nums) : 0) + 1);
  }

  function startWbsInline() {
    if (document.getElementById("wbs-inline-row")) return;
    var body = document.getElementById("wbs-grid-body"); if (!body) return;
    var selected = body.querySelector(".wbs-row.is-selected"), parentId = selected ? selected.dataset.wbsRow : null;
    var parentCode = selected && selected.querySelector(".wbs-code") ? selected.querySelector(".wbs-code").textContent.trim() : "";
    var depth = selected ? Number(selected.style.getPropertyValue("--depth") || 1) + 1 : 1;
    if (depth > 6) { alert("Maximum WBS depth is 6 levels."); return; }
    var row = document.createElement("div"); row.id="wbs-inline-row"; row.className="wbs-row inline-entry is-selected"; row.style.setProperty("--depth",depth);
    row.innerHTML='<div class="text-center muted">'+depth+'</div><div><input id="wbs-inline-code" class="inline-grid-input code-input" value="'+e(nextWbsCode(parentCode))+'"></div><div class="wbs-name"><input id="wbs-inline-name" class="inline-grid-input" placeholder="Type WBS name"></div><div>'+depth+'</div><div class="wbs-actions"><button id="wbs-inline-save" class="inline-save">Save ↵</button><button id="wbs-inline-cancel">Done / Cancel</button></div>';
    if (selected) selected.insertAdjacentElement("afterend",row); else body.appendChild(row);
    var name=row.querySelector("#wbs-inline-name"), saving=false;
    async function save(addAnother){if(saving)return;var code=row.querySelector("#wbs-inline-code").value.trim().toUpperCase(),value=name.value.trim();if(!code||!value){name.focus();return}saving=true;var r=await vmmsApi("/api/v1/schedule/wbs",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({project_id:pid(),parent_id:parentId,code:code,name:value,description:null})});if(!r.ok){var d=await r.json();alert(d.detail||"Could not add WBS");saving=false;return}window.dispatchEvent(new CustomEvent("vcms:project-changed",{detail:{project:vcmsProjectContext.getActive()}}));if(addAnother)(function waitForSavedRow(tries){var found=Array.from(document.querySelectorAll("#wbs-grid-body .wbs-code")).some(function(x){return x.textContent.trim()===code});if(found)return startWbsInline();if(tries>0)setTimeout(function(){waitForSavedRow(tries-1)},150)})(30)}
    row.querySelector("#wbs-inline-save").onclick=function(){save(false)};row.querySelector("#wbs-inline-cancel").onclick=function(){row.remove()};
    row.onkeydown=function(ev){if(ev.key==="Escape"){ev.preventDefault();row.remove()}else if(ev.key==="Enter"){ev.preventDefault();save(true)}};
    name.focus();
  }

  function nextActivityCode() {
    var nums=Array.from(document.querySelectorAll("#activities-body td:first-child")).map(function(x){var m=x.textContent.match(/(\d+)/);return m?Number(m[1]):0;});
    return "A"+String((nums.length?Math.max.apply(Math,nums):0)+10).padStart(4,"0");
  }

  async function startActivityInline() {
    if (document.getElementById("activity-inline-row")) return;
    var body=document.getElementById("activities-body");if(!body)return;
    document.getElementById("activities-table").classList.remove("hidden");
    document.getElementById("activities-empty").classList.add("hidden");
    var wr=await vmmsApi("/api/v1/schedule/wbs?project_id="+encodeURIComponent(pid()));if(!wr.ok)return alert("Add a WBS before adding activities.");
    var nodes=(await wr.json()).nodes||[];if(!nodes.length)return alert("Add a WBS before adding activities.");
    var today=new Date().toISOString().slice(0,10),row=document.createElement("tr");row.id="activity-inline-row";row.className="inline-entry is-selected";
    row.innerHTML='<td><input id="ai-code" class="inline-grid-input code-input" value="'+e(nextActivityCode())+'"></td><td><select id="ai-type" class="inline-grid-input"><option value="task">Activity</option><option value="milestone">Milestone</option></select></td><td><input id="ai-name" class="inline-grid-input" placeholder="Type activity name"></td><td><select id="ai-wbs" class="inline-grid-input">'+nodes.map(function(n){return'<option value="'+e(n.id)+'">'+e(n.code)+'</option>'}).join("")+'</select></td><td><input id="ai-duration" class="inline-grid-input number-input" type="number" min="0" value="1"></td><td><input id="ai-start" class="inline-grid-input" type="date" value="'+today+'"></td><td><input id="ai-finish" class="inline-grid-input" type="date" value="'+today+'"></td><td class="muted">—</td><td class="muted">—</td><td>Not started</td><td>0%</td><td><button id="ai-save" class="inline-save">Save ↵</button><button id="ai-cancel">Done</button></td>';
    body.prepend(row);var name=row.querySelector("#ai-name"),saving=false;
    row.querySelector("#ai-type").onchange=function(){var milestone=this.value==="milestone";row.querySelector("#ai-duration").value=milestone?0:Math.max(1,Number(row.querySelector("#ai-duration").value)||1);row.querySelector("#ai-duration").disabled=milestone};
    async function save(addAnother){if(saving)return;var value=name.value.trim();if(!value){name.focus();return}saving=true;var type=row.querySelector("#ai-type").value,start=row.querySelector("#ai-start").value;var r=await vmmsApi("/api/v1/schedule/activities",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({project_id:pid(),wbs_id:row.querySelector("#ai-wbs").value,code:row.querySelector("#ai-code").value.trim().toUpperCase(),name:value,description:null,activity_type:type,duration_days:type==="milestone"?0:Number(row.querySelector("#ai-duration").value),planned_start:start,planned_finish:type==="milestone"?start:row.querySelector("#ai-finish").value})});if(!r.ok){var d=await r.json();alert(d.detail||"Could not add activity");saving=false;return}window.dispatchEvent(new CustomEvent("vcms:project-changed",{detail:{project:vcmsProjectContext.getActive()}}));if(addAnother)setTimeout(startActivityInline,250)}
    row.querySelector("#ai-save").onclick=function(){save(false)};row.querySelector("#ai-cancel").onclick=function(){row.remove()};
    row.onkeydown=function(ev){if(ev.key==="Escape"){ev.preventDefault();row.remove()}else if(ev.key==="Enter"&&ev.target.tagName!=="SELECT"){ev.preventDefault();save(true)}};name.focus();
  }
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
    var relationshipTab = document.getElementById("tab-logic");
    if (relationshipTab) relationshipTab.classList.add("desktop-logic-tab-hidden");

    var wbs = document.getElementById("wbs-panel");
    if (wbs && !wbs.querySelector(".planner-toolbar")) {
      wbs.insertAdjacentHTML("afterbegin", '<div class="planner-toolbar"><h2>Work Breakdown Structure</h2><span class="muted">Select a row; double-click to edit</span></div>');
      var addWbs = document.getElementById("add");
      if (addWbs) {
        var addWbsHidden = addWbs.classList.contains("hidden");
        addWbs.textContent = "+ WBS";
        addWbs.className = "primary" + (addWbsHidden ? " hidden" : "");
        wbs.querySelector(".planner-toolbar").appendChild(addWbs);
        addWbs.onclick = startWbsInline;
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
          add.onclick = startActivityInline;
        }
        oldHead.replaceWith(toolbar);
      }
      var headings = ["Activity ID","Type","Activity Name","WBS","Original Duration","Start","Finish","Predecessors","Successors","Status","Complete",""];
      var row = document.querySelector("#activities-table thead tr");
      if (row) row.innerHTML = headings.map(function (h) { return "<th>" + h + "</th>"; }).join("");
      if (card) { card.classList.remove("bg-white","rounded-2xl","p-4"); }
    }
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", install);
  else install();
})();
