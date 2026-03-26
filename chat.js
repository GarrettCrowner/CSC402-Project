/*
 * Rammy HR Chatbot — chat.js (Redesigned)
 */

const API_BASE = "http://localhost:3000/api";

let _closing = false;
const WELCOME = "Hi, I'm Rammy! 👋 I'm here to help with all of your WCU HR questions. What would you like to know?";

const SUGGESTIONS = [
  "Benefits & retirement",
  "Time off policies",
  "Training programs",
  "Tuition waiver",
  "Contact HR",
];

// ─── History ──────────────────────────────────────────────────────────────────
let history = [];
function addHistory(role, content) {
  history.push({ role, content });
  if (history.length > 8) history = history.slice(-8);
}

// ─── DOM helpers ─────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);

function isOpen() {
  const c = $("chat-container");
  return c && c.style.display !== "none";
}
function forceHide() {
  const c = $("chat-container");
  if (c) c.setAttribute("style", "display:none!important;");
}
function forceShow() {
  const c = $("chat-container");
  if (c) c.setAttribute("style", "display:flex!important;flex-direction:column;");
}

// ─── Open / Close ─────────────────────────────────────────────────────────────
function openChat() {
  if (isOpen() || _closing) return;
  const msgs = $("message-container");
  if (msgs && msgs.children.length === 0) {
    addHistory("assistant", WELCOME);
    displayMessage("Agent", WELCOME);
  }
  forceShow();
  const btn = $("chat-btn");
  if (btn) btn.style.display = "none";
  setTimeout(() => { const i = $("chat-user-input"); if (i) i.focus(); }, 120);
}

function closeChat() {
  if (!isOpen() || _closing) return;
  _closing = true;
  forceHide();
  const btn = $("chat-btn");
  if (btn) btn.style.setProperty("display", "flex", "important");
  setTimeout(() => { _closing = false; }, 400);
}

window.restoreChat = function () {};

// ─── Status Dot ───────────────────────────────────────────────────────────────
async function checkStatus() {
  const dot = $("status-dot");
  if (!dot) return;
  try {
    const controller = new AbortController();
    const t = setTimeout(() => controller.abort(), 3000);
    const res = await fetch(`${API_BASE}/health`, { signal: controller.signal });
    clearTimeout(t);
    const data = await res.json();
    dot.style.backgroundColor =
      data.status === "ok" && data.python === "reachable" ? "#4ade80" : "#f87171";
    dot.title = data.status === "ok" ? "Online" : "Degraded";
  } catch {
    const d = $("status-dot");
    if (d) { d.style.backgroundColor = "#f87171"; d.title = "Offline"; }
  }
}

// ─── Timestamps ───────────────────────────────────────────────────────────────
function getTimestamp() {
  const d = new Date();
  let h = d.getHours(), m = d.getMinutes().toString().padStart(2, "0");
  const ap = h >= 12 ? "PM" : "AM";
  h = h % 12 || 12;
  return `${h}:${m} ${ap}`;
}

// ─── Sanitize ─────────────────────────────────────────────────────────────────
function sanitizeHtml(str) {
  const anchors = [];
  let s = String(str);
  s = s.replace(/<a\s+href="(https?:\/\/[^"]+)"[^>]*>(.*?)<\/a>/gi, (_, href, text) => {
    anchors.push(`<a href="${href}" target="_blank" rel="noopener noreferrer">${text}</a>`);
    return `\x00A${anchors.length - 1}\x00`;
  });
  s = s.replace(/<a\s+href="(mailto:[^"]+|tel:[^"]+)"[^>]*>(.*?)<\/a>/gi, (_, href, text) => {
    anchors.push(`<a href="${href}">${text}</a>`);
    return `\x00A${anchors.length - 1}\x00`;
  });
  s = s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  return s.replace(/\x00A(\d+)\x00/g, (_, i) => anchors[+i]);
}

// ─── Display ──────────────────────────────────────────────────────────────────
function displayMessage(role, text) {
  const cw = $("message-container");
  if (!cw) return;

  const wrapper = document.createElement("div");
  wrapper.className = role === "You" ? "user-msg-wrapper" : "agent-msg-wrapper";

  const bubble = document.createElement("div");

  if (role === "Typing") {
    bubble.className = "agent-bubble typing-indicator";
    bubble.id = "loading-bubble";
    bubble.innerHTML = `<div class="dot"></div><div class="dot"></div><div class="dot"></div>`;
  } else {
    bubble.className = role === "You" ? "user-bubble" : "agent-bubble";
    bubble.innerHTML = `<p>${sanitizeHtml(text)}</p>`;
  }

  wrapper.appendChild(bubble);

  if (role !== "Typing") {
    const meta = document.createElement("div");
    meta.style.cssText = "display:flex;align-items:center;gap:0.35rem;";
    const name = document.createElement("span");
    name.className = "profile-name";
    name.textContent = role === "You" ? "You" : "Rammy";
    const ts = document.createElement("span");
    ts.textContent = getTimestamp();
    ts.style.cssText = "font-size:0.63rem;color:#b0a0c0;font-family:inherit;";
    meta.appendChild(name);
    meta.appendChild(ts);
    wrapper.appendChild(meta);
  }

  cw.appendChild(wrapper);
  cw.scrollTop = cw.scrollHeight;

  // Hide suggestions after first user message
  if (role === "You") {
    const sugg = $("chat-suggestions");
    if (sugg) {
      sugg.style.transition = "opacity 0.25s, max-height 0.3s";
      sugg.style.opacity = "0";
      sugg.style.maxHeight = "0";
      sugg.style.overflow = "hidden";
      sugg.style.padding = "0";
    }
  }
}

function replaceLoadingBubble(text) {
  const loader = $("loading-bubble");
  if (!loader) return;
  const parent = loader.parentElement;
  loader.id = "";
  loader.className = "agent-bubble";
  loader.innerHTML = `<p>${sanitizeHtml(text)}</p>`;
  const meta = document.createElement("div");
  meta.style.cssText = "display:flex;align-items:center;gap:0.35rem;";
  const name = document.createElement("span");
  name.className = "profile-name";
  name.textContent = "Rammy";
  const ts = document.createElement("span");
  ts.textContent = getTimestamp();
  ts.style.cssText = "font-size:0.63rem;color:#b0a0c0;font-family:inherit;";
  meta.appendChild(name);
  meta.appendChild(ts);
  parent.appendChild(meta);
  $("message-container").scrollTop = 99999;
}

function setInputEnabled(on) {
  const i = $("chat-user-input");
  const b = $("send-btn");
  if (i) i.disabled = !on;
  if (b) b.disabled = !on;
}

// ─── Suggestion chips ─────────────────────────────────────────────────────────
function buildSuggestions() {
  const container = $("chat-suggestions");
  if (!container) return;
  SUGGESTIONS.forEach(label => {
    const btn = document.createElement("button");
    btn.className = "cb-suggestion";
    btn.textContent = label;
    btn.addEventListener("click", () => {
      const input = $("chat-user-input");
      if (input) {
        input.value = label;
        handleChat();
      }
    });
    container.appendChild(btn);
  });
}

// ─── API ──────────────────────────────────────────────────────────────────────
async function fetchReply(message) {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, history })
  });
  if (!res.ok) throw new Error(`Server error ${res.status}`);
  return (await res.json()).reply;
}

async function handleChat() {
  const input = $("chat-user-input");
  if (!input) return;
  const text = input.value.trim();
  if (!text) return;
  input.value = "";

  if (text.toLowerCase() === "/refresh") {
    try {
      await fetch(`${API_BASE}/refresh`, { method: "POST" });
      displayMessage("Agent", "Sources are refreshing!");
    } catch {
      displayMessage("Agent", "Could not reach the server.");
    }
    return;
  }

  displayMessage("You", text);
  addHistory("user", text);
  displayMessage("Typing", "");
  setInputEnabled(false);

  try {
    const reply = await fetchReply(text);
    replaceLoadingBubble(reply);
    addHistory("assistant", reply);
  } catch {
    replaceLoadingBubble("Sorry, I'm having trouble connecting right now. Please try again.");
  } finally {
    setInputEnabled(true);
    const i = $("chat-user-input");
    if (i) i.focus();
  }
}

// ─── Options Dropdown ─────────────────────────────────────────────────────────
function createDropdown() {
  const existing = $("options-dropdown");
  if (existing) { existing.remove(); return; }

  const header = $("chat-header");
  if (!header) return;

  const dropdown = document.createElement("div");
  dropdown.id = "options-dropdown";

  const items = [
    {
      icon: "🗑️", label: "Clear conversation", fn: () => {
        if (!confirm("Clear conversation?")) return;
        const m = $("message-container");
        if (m) m.innerHTML = "";
        history = [];
        // Restore suggestions
        const sugg = $("chat-suggestions");
        if (sugg) {
          sugg.style.opacity = "1";
          sugg.style.maxHeight = "60px";
          sugg.style.padding = "";
        }
        addHistory("assistant", WELCOME);
        displayMessage("Agent", WELCOME);
      }
    },
    {
      icon: "🔄", label: "Refresh HR sources", fn: async () => {
        try {
          await fetch(`${API_BASE}/refresh`, { method: "POST" });
          displayMessage("Agent", "Refreshing HR sources…");
        } catch {
          displayMessage("Agent", "Could not refresh sources.");
        }
      }
    },
    {
      icon: "📧", label: "Contact HR directly", fn: () => {
        displayMessage("Agent", `Reach WCU HR at <a href="mailto:HRS@wcupa.edu">HRS@wcupa.edu</a> or <a href="tel:6104362800">610-436-2800</a>.`);
      }
    },
  ];

  items.forEach((item, idx) => {
    const btn = document.createElement("button");
    btn.style.cssText = `
      width:100%;padding:0.7rem 1rem;display:flex;align-items:center;gap:0.6rem;
      font-size:0.85rem;color:#2d1a3e;background:white;border:none;cursor:pointer;
      text-align:left;box-sizing:border-box;font-family:inherit;font-weight:500;
      transition:background 0.15s;
      ${idx < items.length - 1 ? "border-bottom:1px solid #f0ebf5;" : ""}
    `;
    btn.onmouseenter = () => btn.style.background = "#f7f2fc";
    btn.onmouseleave = () => btn.style.background = "white";
    btn.innerHTML = `<span style="font-size:1rem">${item.icon}</span><span>${item.label}</span>`;
    btn.addEventListener("click", () => { dropdown.remove(); item.fn(); });
    dropdown.appendChild(btn);
  });

  header.style.position = "relative";
  header.appendChild(dropdown);

  setTimeout(() => {
    document.addEventListener("click", function h(e) {
      if (!dropdown.contains(e.target)) {
        dropdown.remove();
        document.removeEventListener("click", h);
      }
    });
  }, 50);
}

// ─── Init ─────────────────────────────────────────────────────────────────────
window.addEventListener("load", () => {
  forceHide();
  const btn = $("chat-btn");
  if (btn) btn.style.setProperty("display", "flex", "important");

  $("chat-btn")?.addEventListener("click", openChat);
  $("chat-close-btn")?.addEventListener("click", closeChat);
  $("chat-options-btn")?.addEventListener("click", e => { e.stopPropagation(); createDropdown(); });

  const form = $("chat-user-form");
  if (form) form.addEventListener("submit", e => { e.preventDefault(); handleChat(); });

  // Keyboard shortcut: Escape to close
  document.addEventListener("keydown", e => {
    if (e.key === "Escape" && isOpen()) closeChat();
  });

  buildSuggestions();
  addHistory("assistant", WELCOME);
  checkStatus();
  setInterval(checkStatus, 30000);
});
