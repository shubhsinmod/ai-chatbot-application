/* Embeddable chat widget. Add to any page:
   <script src="https://YOUR-SERVER/widget.js" defer></script>
   Optional attributes: data-title, data-color, data-greeting */
(() => {
  const me = document.currentScript || document.querySelector('script[src*="widget.js"]');
  const api = new URL(me.src).origin;
  const title = me.dataset.title || "Chat with us";
  const color = me.dataset.color || "#1f6f4a";
  const greeting = me.dataset.greeting || "👋 Welcome to Sigmoss Systems Pvt. Ltd.!\n\nWe help food and bakery businesses with technology and consulting solutions.\n\nHow can we help you today?";

  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = host.attachShadow({ mode: "open" });
  root.innerHTML = `
  <style>
    *{box-sizing:border-box;font-family:system-ui,-apple-system,"Segoe UI",sans-serif}
    .fab{position:fixed;right:20px;bottom:20px;width:56px;height:56px;border-radius:50%;border:0;background:${color};color:#fff;cursor:pointer;box-shadow:0 4px 14px rgba(0,0,0,.25);font-size:24px;z-index:2147483000}
    .box{position:fixed;right:20px;bottom:88px;width:360px;max-width:calc(100vw - 24px);height:520px;max-height:calc(100vh - 110px);background:#fff;color:#1b2430;border-radius:12px;box-shadow:0 8px 30px rgba(0,0,0,.25);display:none;flex-direction:column;overflow:hidden;z-index:2147483000}
    .box.open{display:flex}
    header{background:${color};color:#fff;padding:12px 14px;font-weight:600;display:flex;justify-content:space-between;align-items:center}
    header button{background:none;border:0;color:#fff;font-size:20px;cursor:pointer}
    .log{flex:1;overflow:auto;padding:12px;display:flex;flex-direction:column;gap:8px;background:#f6f7f9}
    .m{max-width:85%;padding:9px 12px;border-radius:12px;font-size:14px;line-height:1.45;white-space:pre-wrap;word-wrap:break-word}
    .u{align-self:flex-end;background:${color};color:#fff}
    .b{align-self:flex-start;background:#fff;border:1px solid #e1e5ea}
    .b a{color:${color};font-size:12px;display:block;margin-top:6px}
    form{display:flex;gap:6px;padding:10px;border-top:1px solid #e1e5ea;background:#fff}
    input{flex:1;border:1px solid #cfd5dc;border-radius:8px;padding:9px 10px;font-size:14px}
    form button{border:0;background:${color};color:#fff;border-radius:8px;padding:0 14px;cursor:pointer}
    button:focus-visible,input:focus-visible{outline:2px solid ${color};outline-offset:2px}
    form button:disabled{opacity:.6}
  </style>
  <button class="fab" aria-label="Open chat">&#128172;</button>
  <section class="box" role="dialog" aria-label="${title}">
    <header><span>${title}</span><button aria-label="Close chat">&times;</button></header>
    <div class="log" aria-live="polite"></div>
    <form><input placeholder="Type your question…" maxlength="1000" required aria-label="Your question"><button>Send</button></form>
  </section>`;

  const $ = s => root.querySelector(s);
  const box = $(".box"), log = $(".log"), input = $("input"), send = $("form button");
  const history = [];
  const add = (cls, text) => { const d = document.createElement("div"); d.className = "m " + cls; d.textContent = text; log.appendChild(d); log.scrollTop = log.scrollHeight; return d; };
  add("b", greeting);
  $(".fab").onclick = () => { box.classList.toggle("open"); if (box.classList.contains("open")) input.focus(); };
  $("header button").onclick = () => box.classList.remove("open");

  $("form").onsubmit = async e => {
    e.preventDefault();
    const q = input.value.trim(); if (!q) return;
    input.value = ""; add("u", q);
    const wait = add("b", "Typing…"); send.disabled = true;
    try {
      const r = await fetch(api + "/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: q, history }) });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || "Something went wrong.");
      wait.textContent = data.answer;
      (data.sources || []).slice(0, 2).forEach(s => { const a = document.createElement("a"); a.href = s.url; a.target = "_blank"; a.rel = "noopener"; a.textContent = "Source: " + (s.name || s.url); wait.appendChild(a); });
      history.push({ role: "user", content: q }, { role: "assistant", content: data.answer });
    } catch (err) { wait.textContent = err.message; }
    send.disabled = false; input.focus();
  };
})();
