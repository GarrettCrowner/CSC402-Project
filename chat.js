/*
 * Rammy HR Chatbot — chat.js
 * Embeddable in any WCU page.
 */

const API_BASE = "http://localhost:3000/api";

let _open = false;
let _closing = false;
const WELCOME = "Hi, my name is Rammy. I am here to help with all of your HR questions! What would you like to know?";

// ─── Conversation History ─────────────────────────────────────────────────────
const MAX_TURNS = 4;
let history = [];
function addHistory(role, content) {
    history.push({ role, content });
    if (history.length > MAX_TURNS * 2) history = history.slice(-(MAX_TURNS * 2));
}

// ─── Open / Close ─────────────────────────────────────────────────────────────
function openChat() {
    if (_open || _closing) return;
    _open = true;

    const container = document.getElementById("chat-container");
    const btn       = document.getElementById("chat-btn");
    const msgs      = document.getElementById("message-container");

    if (msgs && msgs.children.length === 0) {
        addHistory("assistant", WELCOME);
        displayMessage("Agent", WELCOME);
    }

    container.style.display        = "flex";
    container.style.flexDirection  = "column";
    container.style.transform      = "translateY(20px)";
    container.style.opacity        = "0";
    container.style.transition     = "transform 0.3s ease, opacity 0.3s ease";
    if (btn) btn.style.display = "none";

    requestAnimationFrame(() => requestAnimationFrame(() => {
        container.style.transform = "translateY(0)";
        container.style.opacity   = "1";
    }));

    setTimeout(() => {
        const input = document.getElementById("chat-user-input");
        if (input) input.focus();
    }, 310);
}

function closeChat() {
    if (!_open || _closing) return;
    _open    = false;
    _closing = true;
    setTimeout(() => { _closing = false; }, 800);

    const container = document.getElementById("chat-container");
    const btn       = document.getElementById("chat-btn");

    container.style.transition = "transform 0.3s ease, opacity 0.3s ease";
    container.style.transform  = "translateY(20px)";
    container.style.opacity    = "0";

    setTimeout(() => {
        container.style.display   = "none";
        container.style.transform = "";
        container.style.opacity   = "";
        if (btn) btn.style.display = "flex";
    }, 300);
}

// Expose as no-op so WCU JS calling window.restoreChat does nothing
window.restoreChat = function() {};

// ─── Status Dot ───────────────────────────────────────────────────────────────
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
        const dot2 = document.getElementById("status-dot");
        if (dot2) dot2.style.backgroundColor = "#ef4444";
    }
}

// ─── Timestamps ───────────────────────────────────────────────────────────────
function getTimestamp() {
    const d = new Date();
    let h = d.getHours(), m = d.getMinutes().toString().padStart(2,"0");
    const ap = h >= 12 ? "PM" : "AM";
    h = h % 12 || 12;
    return `${h}:${m} ${ap}`;
}

// ─── Sanitize HTML ────────────────────────────────────────────────────────────
function sanitizeHtml(str) {
    const anchors = [];
    let s = String(str);
    s = s.replace(/<a\s+href="(https?:\/\/[^"]+)"[^>]*>(.*?)<\/a>/gi, (_, href, text) => {
        anchors.push(`<a href="${href}" target="_blank" rel="noopener noreferrer" style="color:#6E3061;word-break:break-word;">${text}</a>`);
        return `\x00A${anchors.length-1}\x00`;
    });
    s = s.replace(/<a\s+href="(mailto:[^"]+|tel:[^"]+)"[^>]*>(.*?)<\/a>/gi, (_, href, text) => {
        anchors.push(`<a href="${href}" style="color:#6E3061;">${text}</a>`);
        return `\x00A${anchors.length-1}\x00`;
    });
    s = s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
    return s.replace(/\x00A(\d+)\x00/g, (_, i) => anchors[+i]);
}

// ─── Display Messages ─────────────────────────────────────────────────────────
function displayMessage(role, text) {
    const chatWindow = document.getElementById("message-container");
    if (!chatWindow) return;

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
        meta.style.cssText = "display:flex;align-items:center;gap:0.4rem;margin-top:0.25rem;padding:0 0.25rem;";
        const name = document.createElement("span");
        name.className = "profile-name";
        name.textContent = role === "You" ? "You" : "Rammy";
        const ts = document.createElement("span");
        ts.textContent = getTimestamp();
        ts.style.cssText = "font-size:0.6rem;color:#c4c9d4;font-family:sans-serif;font-style:italic;";
        meta.appendChild(name);
        meta.appendChild(ts);
        wrapper.appendChild(meta);
    }

    chatWindow.appendChild(wrapper);
    chatWindow.scrollTop = chatWindow.scrollHeight;
}

function replaceLoadingBubble(text) {
    const loader = document.getElementById("loading-bubble");
    if (!loader) return;
    const parent = loader.parentElement;
    loader.id = "";
    loader.className = "agent-bubble";
    loader.innerHTML = `<p>${sanitizeHtml(text)}</p>`;
    const meta = document.createElement("div");
    meta.style.cssText = "display:flex;align-items:center;gap:0.4rem;margin-top:0.25rem;padding:0 0.25rem;";
    const name = document.createElement("span");
    name.className = "profile-name";
    name.textContent = "Rammy";
    const ts = document.createElement("span");
    ts.textContent = getTimestamp();
    ts.style.cssText = "font-size:0.6rem;color:#c4c9d4;font-family:sans-serif;font-style:italic;";
    meta.appendChild(name);
    meta.appendChild(ts);
    parent.appendChild(meta);
    document.getElementById("message-container").scrollTop = 99999;
}

function setInputEnabled(on) {
    const i = document.getElementById("chat-user-input");
    const b = document.getElementById("send-btn");
    if (i) i.disabled = !on;
    if (b) b.disabled = !on;
}

// ─── API ──────────────────────────────────────────────────────────────────────
async function fetchReply(message) {
    const res = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, history })
    });
    if (!res.ok) throw new Error(`Server error ${res.status}`);
    const data = await res.json();
    return data.reply;
}

async function handleChat() {
    const input = document.getElementById("chat-user-input");
    if (!input) return;
    const text = input.value.trim();
    if (!text) return;
    input.value = "";

    if (text.toLowerCase() === "/refresh") {
        try {
            await fetch(`${API_BASE}/refresh`, { method: "POST" });
            displayMessage("Agent", "Sources are refreshing in the background!");
        } catch { displayMessage("Agent", "Could not reach the server."); }
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
    } catch (err) {
        replaceLoadingBubble("Sorry, I'm having trouble connecting. Please try again.");
    } finally {
        setInputEnabled(true);
        const i = document.getElementById("chat-user-input");
        if (i) i.focus();
    }
}

// ─── Options Dropdown ─────────────────────────────────────────────────────────
function createDropdown() {
    const existing = document.getElementById("options-dropdown");
    if (existing) { existing.remove(); return; }

    const header = document.getElementById("chat-header");
    if (!header) return;

    const dropdown = document.createElement("div");
    dropdown.id = "options-dropdown";
    dropdown.style.cssText = "position:absolute!important;top:56px!important;right:12px!important;background:white!important;border-radius:0.75rem!important;box-shadow:0 8px 24px rgba(0,0,0,0.15)!important;overflow:hidden!important;z-index:99999!important;min-width:200px!important;";

    [
        { icon: "🗑️", label: "Clear conversation", fn: () => {
            if (!confirm("Clear conversation?")) return;
            const m = document.getElementById("message-container");
            if (m) m.innerHTML = "";
            history = [];
            addHistory("assistant", WELCOME);
            displayMessage("Agent", WELCOME);
        }},
        { icon: "🔄", label: "Refresh HR sources", fn: async () => {
            try { await fetch(`${API_BASE}/refresh`, { method: "POST" }); displayMessage("Agent", "Refreshing sources…"); }
            catch { displayMessage("Agent", "Could not refresh."); }
        }},
        { icon: "📧", label: "Contact HR", fn: () => {
            displayMessage("Agent", `Reach WCU HR at <a href="mailto:HRS@wcupa.edu" style="color:#6E3061;">HRS@wcupa.edu</a> or <a href="tel:6104362800" style="color:#6E3061;">610-436-2800</a>.`);
        }},
    ].forEach(item => {
        const btn = document.createElement("button");
        btn.style.cssText = "width:100%!important;padding:0.75rem 1rem!important;display:flex!important;flex-direction:row!important;align-items:center!important;gap:0.6rem!important;font-size:0.875rem!important;color:#374151!important;background:white!important;border:none!important;border-bottom:1px solid #f3f4f6!important;cursor:pointer!important;text-align:left!important;box-sizing:border-box!important;";
        const ico = document.createElement("span");
        ico.style.cssText = "flex-shrink:0;pointer-events:none;";
        ico.textContent = item.icon;
        const lbl = document.createElement("span");
        lbl.style.cssText = "pointer-events:none;color:#374151;";
        lbl.textContent = item.label;
        btn.appendChild(ico);
        btn.appendChild(lbl);
        btn.addEventListener("click", (e) => { e.stopPropagation(); dropdown.remove(); item.fn(); });
        dropdown.appendChild(btn);
    });

    header.style.position = "relative";
    header.appendChild(dropdown);

    setTimeout(() => {
        document.addEventListener("click", function h(e) {
            if (!dropdown.contains(e.target)) { dropdown.remove(); document.removeEventListener("click", h); }
        });
    }, 10);
}

// ─── Wire Everything After Page Fully Loads ───────────────────────────────────
window.addEventListener("load", () => {
    // Intercept ALL clicks in capture phase — if click is inside chat-container,
    // stop it from reaching WCU's global handlers
    document.addEventListener("click", (e) => {
        const container = document.getElementById("chat-container");
        if (container && container.contains(e.target)) {
            e.stopPropagation();
        }
    }, true); // true = capture phase, fires before WCU handlers
    // Wire form submit
    const form = document.getElementById("chat-user-form");
    if (form) {
        form.addEventListener("submit", (e) => { e.preventDefault(); handleChat(); });
    }

    // Wire all three buttons by cloning (strips WCU listeners) then re-querying
    ["chat-btn", "chat-close-btn", "chat-options-btn"].forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        const clone = el.cloneNode(true);
        el.parentNode.replaceChild(clone, el);
    });

    // Disable pointer events on all ion-icons so clicks hit the button not the icon
    document.querySelectorAll("#chat-btn ion-icon, #chat-close-btn ion-icon, #chat-options-btn ion-icon, #send-btn ion-icon").forEach(ico => {
        ico.style.pointerEvents = "none";
    });

    // Now wire fresh clones
    const openBtn  = document.getElementById("chat-btn");
    const closeBtn = document.getElementById("chat-close-btn");
    const optsBtn  = document.getElementById("chat-options-btn");

    if (openBtn)  openBtn.addEventListener("click",  (e) => { e.stopPropagation(); openChat(); });
    if (closeBtn) closeBtn.addEventListener("click", (e) => { e.stopPropagation(); e.preventDefault(); closeChat(); });
    if (optsBtn)  optsBtn.addEventListener("click",  (e) => { e.stopPropagation(); createDropdown(); });

    // Pre-load history
    addHistory("assistant", WELCOME);

    // Status dot
    checkStatus();
    setInterval(checkStatus, 30000);
});
