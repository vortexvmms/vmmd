/* VCMS natural-language assistant. Loaded once by the shared core bundle on
   every signed-in page. Chat content stays in memory and is never saved to
   localStorage, which prevents operational answers remaining on shared phones. */
(function () {
  "use strict";
  if (window.__VCMS_ASSISTANT_LOADING__) return;
  window.__VCMS_ASSISTANT_LOADING__ = true;

  var page = (location.pathname.split("/").pop() || "").toLowerCase();
  if (["", "index.html", "login.html"].indexOf(page) !== -1) return;

  function ready(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn, { once: true });
  }

  function addMessage(log, text, kind, copyable) {
    var node = document.createElement("div");
    node.className = "vcms-assistant-msg " + (kind === "user" ? "is-user" : "is-bot") + (kind === "error" ? " is-error" : "");
    node.textContent = text;
    if (copyable) {
      var copy = document.createElement("button");
      copy.type = "button";
      copy.className = "vcms-assistant-copy";
      copy.textContent = "Copy answer";
      copy.addEventListener("click", async function () {
        try { await navigator.clipboard.writeText(text); copy.textContent = "Copied ✓"; }
        catch (_) { copy.textContent = "Select and copy the text"; }
        setTimeout(function () { copy.textContent = "Copy answer"; }, 1800);
      });
      node.appendChild(copy);
    }
    log.appendChild(node);
    log.scrollTop = log.scrollHeight;
    return node;
  }

  ready(function () {
    if (document.getElementById("vcms-assistant-fab")) return;
    if (typeof getSession !== "function" || !getSession()) return;

    var css = document.createElement("link");
    css.rel = "stylesheet";
    css.href = "css/assistant.css?v=20260828-1";
    document.head.appendChild(css);

    var fab = document.createElement("button");
    fab.id = "vcms-assistant-fab";
    fab.className = "vcms-assistant-fab no-print";
    fab.type = "button";
    fab.setAttribute("aria-expanded", "false");
    fab.setAttribute("aria-controls", "vcms-assistant-panel");
    fab.setAttribute("aria-label", "Open VCMS Assistant");
    fab.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v8a2.5 2.5 0 0 1-2.5 2.5H10l-5 4v-4.5A2.5 2.5 0 0 1 4 13.5z"/><path d="M8 8h8M8 11.5h5"/></svg><span>Ask VCMS</span>';

    var panel = document.createElement("section");
    panel.id = "vcms-assistant-panel";
    panel.className = "vcms-assistant-panel no-print";
    panel.setAttribute("aria-label", "VCMS Assistant");
    panel.setAttribute("aria-hidden", "true");
    panel.innerHTML = '<header class="vcms-assistant-head"><div class="vcms-assistant-mark" aria-hidden="true">✦</div><div class="vcms-assistant-title"><strong>VCMS Assistant</strong><small>Role-scoped answers from live VCMS data</small></div><button class="vcms-assistant-close" type="button" aria-label="Close assistant">×</button></header><div class="vcms-assistant-log" role="log" aria-live="polite"><div class="vcms-assistant-msg is-bot">Ask about attendance, leave, man-hours, resources, missing DPRs, or request a WhatsApp draft.</div><div class="vcms-assistant-suggestions"><button type="button" class="vcms-assistant-suggestion">Today’s attendance</button><button type="button" class="vcms-assistant-suggestion">Who is on leave today?</button><button type="button" class="vcms-assistant-suggestion">Draft allocation message</button></div></div><form class="vcms-assistant-form"><textarea class="vcms-assistant-input" rows="1" maxlength="1200" placeholder="Ask VCMS…" aria-label="Message to VCMS Assistant"></textarea><button class="vcms-assistant-send" type="submit" aria-label="Send">➤</button><p class="vcms-assistant-note">The first reply can take up to 90 seconds when the server is waking. Review generated messages before sending.</p></form>';
    document.body.appendChild(panel);
    document.body.appendChild(fab);

    var close = panel.querySelector(".vcms-assistant-close");
    var form = panel.querySelector(".vcms-assistant-form");
    var input = panel.querySelector(".vcms-assistant-input");
    var send = panel.querySelector(".vcms-assistant-send");
    var log = panel.querySelector(".vcms-assistant-log");
    var busy = false;

    function setOpen(open) {
      panel.classList.toggle("is-open", open);
      panel.setAttribute("aria-hidden", String(!open));
      fab.setAttribute("aria-expanded", String(open));
      fab.setAttribute("aria-label", open ? "Close VCMS Assistant" : "Open VCMS Assistant");
      if (open) setTimeout(function () { input.focus(); }, 120);
    }
    fab.addEventListener("click", function () { setOpen(!panel.classList.contains("is-open")); });
    close.addEventListener("click", function () { setOpen(false); fab.focus(); });
    document.addEventListener("keydown", function (event) { if (event.key === "Escape" && panel.classList.contains("is-open")) setOpen(false); });

    panel.querySelectorAll(".vcms-assistant-suggestion").forEach(function (button) {
      button.addEventListener("click", function () { input.value = button.textContent; form.requestSubmit(); });
    });
    input.addEventListener("input", function () { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 110) + "px"; });
    input.addEventListener("keydown", function (event) {
      if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); form.requestSubmit(); }
    });

    form.addEventListener("submit", async function (event) {
      event.preventDefault();
      var message = input.value.trim();
      if (!message || busy) return;
      busy = true; send.disabled = true; input.disabled = true;
      addMessage(log, message, "user", false);
      input.value = ""; input.style.height = "auto";
      var thinking = document.createElement("div");
      thinking.className = "vcms-assistant-msg is-bot";
      thinking.innerHTML = '<span class="vcms-assistant-thinking" aria-label="VCMS is checking"><i></i><i></i><i></i></span>';
      log.appendChild(thinking); log.scrollTop = log.scrollHeight;
      try {
        var response = await vmmsApi("/api/v1/assistant", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: message })
        });
        var data = {};
        try { data = await response.json(); } catch (_) {}
        thinking.remove();
        if (!response.ok) {
          var detail = data.detail || (response.status === 429 ? "Please wait a moment before asking again." : "The assistant could not answer. Please retry.");
          addMessage(log, detail, "error", false);
        } else {
          addMessage(log, data.reply || "I couldn't find an answer for that.", data.error ? "error" : "bot", true);
        }
      } catch (_) {
        thinking.remove();
        addMessage(log, "Connection interrupted. Your question was not submitted—please try again.", "error", false);
      } finally {
        busy = false; send.disabled = false; input.disabled = false; input.focus();
      }
    });
  });
})();
