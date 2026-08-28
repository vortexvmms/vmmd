// VCMS Assistant widget — floating chat that calls /api/v1/assistant.
// Loaded on every signed-in page via core-bundle. Styled with --vcms-* tokens.
// Answers are produced by the backend (Gemini + role-scoped tools); the widget
// only sends the question and renders the reply. No secrets here.
(function () {
  "use strict";
  if (window.__vcmsBotLoaded) return;
  window.__vcmsBotLoaded = true;

  // Only for signed-in users; vmmsApi/getSession come from core.
  function ready() {
    if (typeof vmmsApi !== "function") return false;
    try { if (typeof getSession === "function" && !getSession()) return false; } catch (_) {}
    return true;
  }
  if (!ready()) { return; }

  var CSS =
    "@media screen{" +
    ".vcbot-fab{position:fixed;right:20px;bottom:calc(20px + env(safe-area-inset-bottom,0px));z-index:9997;" +
    "width:58px;height:58px;border-radius:50%;border:0;cursor:pointer;color:var(--vcms-on-brand,#fff);" +
    "background:linear-gradient(135deg,var(--vcms-brand,#C00000),var(--vcms-brand-dark,#960000));" +
    "box-shadow:0 12px 26px -8px rgba(0,0,0,.45);display:grid;place-items:center;transition:transform .18s}" +
    ".vcbot-fab:hover{transform:translateY(-3px) scale(1.04)}.vcbot-fab:active{transform:scale(.93)}" +
    ".vcbot-fab svg{width:27px;height:27px}" +
    ".vcbot-panel{position:fixed;right:20px;bottom:calc(88px + env(safe-area-inset-bottom,0px));z-index:9998;" +
    "width:380px;max-width:calc(100vw - 24px);height:560px;max-height:calc(100vh - 130px);" +
    "background:var(--vcms-surface,#fff);border:1px solid var(--vcms-line,#dce1e8);border-radius:16px;" +
    "box-shadow:0 20px 48px -20px rgba(16,24,40,.5);display:none;flex-direction:column;overflow:hidden}" +
    ".vcbot-panel.on{display:flex}" +
    "@media(max-width:520px){.vcbot-panel{right:0;left:0;bottom:0;width:100%;max-width:100%;height:84vh;max-height:84vh;border-radius:18px 18px 0 0}.vcbot-fab{right:14px;bottom:calc(14px + env(safe-area-inset-bottom,0px))}}" +
    ".vcbot-head{background:linear-gradient(135deg,var(--vcms-brand,#C00000),var(--vcms-brand-dark,#960000));color:var(--vcms-on-brand,#fff);padding:13px 15px;display:flex;align-items:center;gap:10px}" +
    ".vcbot-head b{font-size:14px;display:block;line-height:1.2}.vcbot-head small{font-size:11px;opacity:.85}" +
    ".vcbot-head .x{margin-left:auto;background:rgba(255,255,255,.15);border:0;color:#fff;width:30px;height:30px;border-radius:8px;cursor:pointer;font-size:15px}" +
    ".vcbot-body{flex:1;overflow-y:auto;padding:15px;background:var(--vcms-page,#eef1f5);display:flex;flex-direction:column;gap:10px}" +
    ".vcbot-msg{max-width:85%;padding:10px 13px;border-radius:14px;font-size:13.5px;line-height:1.5;word-wrap:break-word;overflow-wrap:anywhere}" +
    ".vcbot-msg.bot{align-self:flex-start;background:var(--vcms-surface,#fff);border:1px solid var(--vcms-line,#dce1e8);border-bottom-left-radius:5px;color:var(--vcms-ink,#182230)}" +
    ".vcbot-msg.me{align-self:flex-end;background:var(--vcms-brand,#C00000);color:var(--vcms-on-brand,#fff);border-bottom-right-radius:5px}" +
    ".vcbot-msg h4{margin:8px 0 3px;font-size:13px;color:var(--vcms-brand,#C00000)}.vcbot-msg b{font-weight:800}" +
    ".vcbot-msg code{display:block;white-space:pre-wrap;background:var(--vcms-page,#eef1f5);border:1px solid var(--vcms-line,#dce1e8);border-radius:8px;padding:8px;margin:6px 0;font-size:12.5px}" +
    ".vcbot-typing{align-self:flex-start;background:var(--vcms-surface,#fff);border:1px solid var(--vcms-line,#dce1e8);border-radius:14px;padding:11px 14px;display:none}" +
    ".vcbot-typing.on{display:block}.vcbot-typing i{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--vcms-muted,#667085);margin:0 2px;animation:vcbotb 1s infinite}" +
    ".vcbot-typing i:nth-child(2){animation-delay:.15s}.vcbot-typing i:nth-child(3){animation-delay:.3s}" +
    "@keyframes vcbotb{0%,60%,100%{transform:translateY(0);opacity:.4}30%{transform:translateY(-5px);opacity:1}}" +
    ".vcbot-chips{display:flex;flex-wrap:wrap;gap:7px;padding:0 15px 10px;background:var(--vcms-page,#eef1f5)}" +
    ".vcbot-chip{border:1px solid var(--vcms-line,#dce1e8);background:var(--vcms-surface,#fff);color:var(--vcms-ink,#182230);border-radius:999px;padding:7px 11px;font-size:12px;font-weight:700;cursor:pointer}" +
    ".vcbot-chip:hover{border-color:var(--vcms-brand,#C00000);color:var(--vcms-brand,#C00000)}" +
    ".vcbot-in{display:flex;gap:8px;padding:11px;border-top:1px solid var(--vcms-line,#dce1e8);background:var(--vcms-surface,#fff)}" +
    ".vcbot-in input{flex:1;height:44px;border:1px solid var(--vcms-line,#dce1e8);border-radius:11px;padding:0 13px;font-size:14px;background:var(--vcms-surface,#fff);color:var(--vcms-ink,#182230)}" +
    ".vcbot-in input:focus{outline:none;border-color:var(--vcms-brand,#C00000);box-shadow:0 0 0 3px var(--vcms-brand-soft,#f9e6e6)}" +
    ".vcbot-in button{width:44px;height:44px;border:0;border-radius:11px;background:var(--vcms-brand,#C00000);color:#fff;cursor:pointer}.vcbot-in button:disabled{opacity:.5}" +
    ".vcbot-in button svg{width:19px;height:19px}" +
    "@media(prefers-reduced-motion:reduce){.vcbot-fab,.vcbot-typing i{transition:none;animation:none}}" +
    "}";

  var st = document.createElement("style"); st.id = "vcbot-css"; st.textContent = CSS;
  (document.head || document.documentElement).appendChild(st);

  var fab = document.createElement("button");
  fab.className = "vcbot-fab"; fab.setAttribute("aria-label", "Open VCMS Assistant"); fab.type = "button";
  fab.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-8.5 8.5 8.5 8.5 0 0 1-3.8-.9L3 21l1.9-5.7A8.38 8.38 0 0 1 4 11.5 8.5 8.5 0 0 1 12.5 3 8.38 8.38 0 0 1 21 11.5z"/></svg>';

  var panel = document.createElement("div");
  panel.className = "vcbot-panel"; panel.setAttribute("role", "dialog"); panel.setAttribute("aria-label", "VCMS Assistant");
  panel.innerHTML =
    '<div class="vcbot-head"><span><b>VCMS Assistant</b><small>Ask about your site data</small></span>' +
    '<button class="x" type="button" aria-label="Close">✕</button></div>' +
    '<div class="vcbot-body" id="vcbot-body"></div>' +
    '<div class="vcbot-typing" id="vcbot-typing"><i></i><i></i><i></i></div>' +
    '<div class="vcbot-chips" id="vcbot-chips"></div>' +
    '<div class="vcbot-in"><input id="vcbot-input" placeholder="Ask about attendance, OT, DPRs…" autocomplete="off">' +
    '<button id="vcbot-send" type="button" aria-label="Send"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2 11 13M22 2l-7 20-4-9-9-4 20-7z"/></svg></button></div>';

  document.body.appendChild(fab);
  document.body.appendChild(panel);

  var body = panel.querySelector("#vcbot-body");
  var typing = panel.querySelector("#vcbot-typing");
  var chipsBox = panel.querySelector("#vcbot-chips");
  var input = panel.querySelector("#vcbot-input");
  var sendBtn = panel.querySelector("#vcbot-send");
  var busy = false, warmed = false;

  var SUGGESTIONS = [
    "Present today", "OT this month", "Who took the most leave this month?",
    "Sites without DPR", "Draft today's allocation WhatsApp message"
  ];

  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }

  // Minimal, safe markdown: escape first, then bold, headings, code blocks, bullets, line breaks.
  function md(text) {
    var t = esc(text);
    t = t.replace(/```([\s\S]*?)```/g, function (_m, c) { return "<code>" + c.trim() + "</code>"; });
    t = t.replace(/^\s*###\s*(.+)$/gm, "<h4>$1</h4>");
    t = t.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
    t = t.replace(/^\s*[-*]\s+(.+)$/gm, "• $1");
    t = t.replace(/\n/g, "<br>");
    return t;
  }

  function addMsg(html, who) {
    var el = document.createElement("div");
    el.className = "vcbot-msg " + (who || "bot");
    el.innerHTML = who === "me" ? esc(html) : md(html);
    body.appendChild(el); body.scrollTop = body.scrollHeight; return el;
  }

  function renderChips() {
    chipsBox.innerHTML = SUGGESTIONS.map(function (s) { return '<button class="vcbot-chip" type="button">' + esc(s) + "</button>"; }).join("");
    Array.prototype.forEach.call(chipsBox.children, function (b) { b.onclick = function () { send(b.textContent); }; });
  }

  function send(q) {
    q = (q || input.value).trim();
    if (!q || busy) return;
    addMsg(q, "me"); input.value = "";
    chipsBox.style.display = "none";
    busy = true; sendBtn.disabled = true; typing.classList.add("on"); body.scrollTop = body.scrollHeight;
    vmmsApi("/api/v1/assistant", { method: "POST", body: JSON.stringify({ message: q }) })
      .then(function (r) { return r.json(); })
      .then(function (j) { addMsg((j && j.reply) || "Sorry, I didn't get a reply. Please try again.", "bot"); })
      .catch(function () { addMsg("I couldn't reach the assistant. Please check your connection and try again.", "bot"); })
      .then(function () { busy = false; sendBtn.disabled = false; typing.classList.remove("on"); input.focus(); });
  }

  fab.onclick = function () {
    panel.classList.add("on");
    if (!body.dataset.greeted) {
      body.dataset.greeted = "1";
      addMsg("Hello 👷 I'm your VCMS assistant. Ask me about attendance, leave, manhours, resources, or ask me to draft a WhatsApp update. Answers use live data limited to what your role can see. The first reply can take up to a minute.", "bot");
      renderChips();
      // Warm the free backend so the first real answer is quicker.
      if (!warmed) { warmed = true; try { vmmsApi("/api/v1/health"); } catch (_) {} }
    }
    input.focus();
  };
  panel.querySelector(".vcbot-head .x").onclick = function () { panel.classList.remove("on"); };
  sendBtn.onclick = function () { send(); };
  input.addEventListener("keydown", function (e) { if (e.key === "Enter") send(); });
})();
