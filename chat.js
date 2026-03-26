/*
 * Rammy HR Chatbot — chat.js
 */

const API_BASE = "http://localhost:3000/api";

let _closing = false;
const WELCOME = "Hi, my name is Rammy. I am here to help with all of your HR questions! What would you like to know?";

// ─── History ──────────────────────────────────────────────────────────────────
let history = [];
function addHistory(role, content) {
    history.push({ role, content });
    if (history.length > 8) history = history.slice(-8);
}

// ─── DOM state helpers ────────────────────────────────────────────────────────
function isOpen() {
    const c = document.getElementById("chat-container");
    return c && c.style.display !== "none";
}

function forceHide() {
    const c = document.getElementById("chat-container");
    if (c) c.setAttribute("style", "display:none!important;");
}

function forceShow() {
    const c = document.getElementById("chat-container");
    if (c) c.setAttribute("style", "display:flex!important;flex-direction:column;");
}

// ─── Open / Close ─────────────────────────────────────────────────────────────
let _welcomed = false;

function openChat() {
    if (isOpen() || _closing) return;

    forceShow();
    const btn = document.getElementById("chat-btn");
    if (btn) btn.style.display = "none";

    if (!_welcomed) {
        _welcomed = true;
        showConnecting();
        checkStatusAndWelcome();
    }

    setTimeout(() => {
        const input = document.getElementById("chat-user-input");
        if (input) input.focus();
    }, 100);
}

/** Renders an animated "Attempting to connect" bubble */
function showConnecting() {
    const cw = document.getElementById("message-container");
    if (!cw) return;

    const wrapper = document.createElement("div");
    wrapper.className = "agent-msg-wrapper";
    wrapper.id = "connecting-wrapper";

    const bubble = document.createElement("div");
    bubble.className = "agent-bubble";
    bubble.style.cssText = "opacity:0.65;font-style:italic;";

    const p = document.createElement("p");
    p.id = "connecting-text";
    p.style.cssText = "color:#111827;margin:0;padding:0;font-size:1rem;line-height:1.5;";
    p.textContent = "Rammy is attempting to connect to the server...";
    bubble.appendChild(p);

    wrapper.appendChild(bubble);
    cw.appendChild(wrapper);
    cw.scrollTop = cw.scrollHeight;
}

/** * UPDATED: Instead of removing the bubble on error, it updates the text 
 * to inform the user the connection failed.
 */
function replaceConnecting(isError) {
    const wrapper = document.getElementById("connecting-wrapper");
    const textNode = document.getElementById("connecting-text");

    if (isError) {
        if (textNode) {
            textNode.textContent = "Connection failed. Please ensure the backend is running.";
            textNode.style.color = "#ef4444"; // Red error text
        }
        _welcomed = false; // Allow retry on next open
    } else {
        if (wrapper) wrapper.remove();
        addHistory("assistant", WELCOME);
        displayMessage("Agent", WELCOME);
    }
}

function closeChat() {
    if (!isOpen() || _closing) return;
    _closing = true;
    forceHide();
    const btn = document.getElementById("chat-btn");
    if (btn) btn.style.setProperty("display", "flex", "important");
    setTimeout(() => { _closing = false; }, 600);
}

// ─── Status Dot ───────────────────────────────────────────────────────────────

async function checkStatusAndWelcome() {
    const dot = document.getElementById("status-dot");
    let ok = false;
    try {
        const controller = new AbortController();
        const t = setTimeout(() => controller.abort(), 5000);
        const res = await fetch(`${API_BASE}/health`, { signal: controller.signal });
        clearTimeout(t);
        const data = await res.json();
        ok = data.status === "ok" && data.python === "reachable";
        if (dot) dot.style.backgroundColor = ok ? "#22c55e" : "#ef4444";
    } catch {
        if (dot) dot.style.backgroundColor = "#ef4444";
    }

    if (ok) {
        replaceConnecting(false);
    } else {
        replaceConnecting(true);
    }
}

async function checkStatus() {
    const dot = document.getElementById("status-dot");
    if (!dot) return;
    try {
        const controller = new AbortController();
        const t = setTimeout(() => controller.abort(), 3000);
        const res = await fetch(`${API_BASE}/health`, { signal: controller.signal });
        clearTimeout(t);
        const data = await res.json();
        dot.style.backgroundColor = (data.status === "ok" && data.python === "reachable") ? "#22c55e" : "#ef4444";
    } catch {
        if (dot) dot.style.backgroundColor = "#ef4444";
    }
}

// ─── Sanitize & Helpers (Unchanged) ───────────────────────────────────────────

function getTimestamp() {
    const d = new Date();
    let h = d.getHours(), m = d.getMinutes().toString().padStart(2, "0");
    const ap = h >= 12 ? "PM" : "AM";
    h = h % 12 || 12;
    return `${h}:${m} ${ap}`;
}

function sanitizeHtml(str) {
    const anchors = [];
    let s = String(str);
    s = s.replace(/<a\s+href="(https?:\/\/[^"]+)"[^>]*>(.*?)<\/a>/gi, (_, href, text) => {
        anchors.push(`<a href="${href}" target="_blank" rel="noopener noreferrer" style="color:#4a1259;word-break:break-word;">${text}</a>`);
        return `\x00A${anchors.length - 1}\x00`;
    });
    s = s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    return s.replace(/\x00A(\d+)\x00/g, (_, i) => anchors[+i]);
}

function parseReply(text) {
    let mainText = text;
    let options = [];
    let followUp = null;
    const optionsMatch = mainText.match(/\[OPTIONS:\s*([^\]]+)\]/i);
    if (optionsMatch) {
        options = optionsMatch[1].split("|").map(s => s.trim()).filter(Boolean);
        mainText = mainText.replace(optionsMatch[0], "").trim();
    }
    const questionMatch = mainText.match(/(?:[.!?])\s+([A-Z][^.!?\n<]*\?)\s*$/);
    if (questionMatch && !options.length) {
        const q = questionMatch[1].trim();
        if (q.split(" ").length >= 4) {
            followUp = q;
            mainText = mainText.slice(0, mainText.lastIndexOf(q)).trim();
        }
    }
    return { mainText: mainText.trim(), options, followUp };
}

function clearQuickReplies() {
    const cw = document.getElementById("message-container");
    if (cw) cw.querySelectorAll(".quick-reply-row").forEach(el => el.remove());
}

function renderQuickReplies(chips, followUpText, botContext) {
    const cw = document.getElementById("message-container");
    if (!cw || !chips.length) return;
    const row = document.createElement("div");
    row.className = "quick-reply-row";
    row.style.cssText = "display:flex;flex-wrap:wrap;gap:0.4rem;padding:0.25rem;align-self:flex-start;max-width:95%;";
    chips.forEach(chipText => {
        const btn = document.createElement("button");
        btn.className = "quick-reply-chip";
        btn.textContent = chipText;
        btn.addEventListener("click", () => handleChat(chipText));
        row.appendChild(btn);
    });
    cw.appendChild(row);
    cw.scrollTop = cw.scrollHeight;
}

// ─── Message Rendering ────────────────────────────────────────────────────────

function displayMessage(role, text) {
    const cw = document.getElementById("message-container");
    if (!cw) return;
    const wrapper = document.createElement("div");
    wrapper.className = role === "You" ? "user-msg-wrapper" : "agent-msg-wrapper";
    const bubble = document.createElement("div");
    bubble.className = role === "You" ? "user-bubble" : "agent-bubble";
    const { mainText, options } = parseReply(text);
    bubble.innerHTML = `<p style="margin:0;font-size:1rem;line-height:1.5;">${sanitizeHtml(mainText)}</p>`;
    wrapper.appendChild(bubble);
    cw.appendChild(wrapper);
    if (options.length) renderQuickReplies(options, null, mainText);
    cw.scrollTop = cw.scrollHeight;
}

function setInputEnabled(on) {
    const i = document.getElementById("chat-user-input");
    const b = document.getElementById("send-btn");
    if (i) i.disabled = !on;
    if (b) b.disabled = !on;
}

async function fetchReply(message) {
    const res = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, history })
    });
    if (!res.ok) throw new Error(`Server error ${res.status}`);
    return (await res.json()).reply;
}

async function handleChat(displayText) {
    const input = document.getElementById("chat-user-input");
    const visibleText = displayText || input?.value.trim();
    if (!visibleText) return;
    if (input) input.value = "";
    clearQuickReplies();
    displayMessage("You", visibleText);
    addHistory("user", visibleText);
    setInputEnabled(false);
    try {
        const reply = await fetchReply(visibleText);
        displayMessage("Agent", reply);
        addHistory("assistant", reply);
    } catch {
        displayMessage("Agent", "Sorry, I'm having trouble connecting.");
    } finally {
        setInputEnabled(true);
    }
}

// ─── Wire Buttons ─────────────────────────────────────────────────────────────
window.addEventListener("load", () => {
    forceHide();
    document.getElementById("chat-btn")?.addEventListener("click", openChat);
    document.getElementById("chat-close-btn")?.addEventListener("click", closeChat);
    const form = document.getElementById("chat-user-form");
    if (form) form.addEventListener("submit", (e) => { e.preventDefault(); handleChat(); });
    checkStatus();
    setInterval(checkStatus, 30000);
});
