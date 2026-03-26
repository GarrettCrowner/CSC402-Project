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

    // Show the container first so appended messages are visible
    forceShow();
    const btn = document.getElementById("chat-btn");
    if (btn) btn.style.display = "none";

    if (!_welcomed) {
        _welcomed = true;
        checkStatusAndWelcome();
    }

    setTimeout(() => {
        const input = document.getElementById("chat-user-input");
        if (input) input.focus();
    }, 100);
}

/** Renders an animated "Attempting to connect" bubble with a cycling ... */

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
    p.style.cssText = "color:#111827;margin:0;padding:0;font-size:1rem;line-height:1.5;";
    p.textContent = "Attempting to connect to server…";
    bubble.appendChild(p);

    wrapper.appendChild(bubble);
    cw.appendChild(wrapper);
    cw.scrollTop = cw.scrollHeight;
}

/** On success: remove the connecting bubble silently, then show the welcome.
 *  On failure: remove the bubble and reset so the next open retries. */
function replaceConnecting(isError) {
    const wrapper = document.getElementById("connecting-wrapper");
    if (wrapper) wrapper.remove();

    if (!isError) {
        addHistory("assistant", WELCOME);
        displayMessage("Agent", WELCOME, true); // skipChips=true — topic chips added manually below
        renderQuickReplies(
            ["Benefits & insurance", "Retirement plans", "Payroll & pay stubs", "Leave & FMLA", "Parking permits", "Tuition waiver"],
            "What can I help you with today?",
            WELCOME
        );
    }
    // On error we leave the chat empty — the status dot turns red and
    // _welcomed resets so the next open tries again automatically.
}

function closeChat() {
    if (!isOpen() || _closing) return;
    _closing = true;

    forceHide();

    const btn = document.getElementById("chat-btn");
    if (btn) btn.style.setProperty("display", "flex", "important");

    setTimeout(() => { _closing = false; }, 600);
}

window.restoreChat = function() {};

// ─── Status Dot ───────────────────────────────────────────────────────────────

/** Called on first open — checks health, and only shows the connecting bubble
 *  if the server takes longer than 400ms to respond (avoids flash on fast connections). */
async function checkStatusAndWelcome() {
    const dot = document.getElementById("status-dot");
    let ok = false;

    // Only reveal the connecting bubble if the check takes more than 400ms
    const showTimer = setTimeout(() => showConnecting(), 400);

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

    clearTimeout(showTimer); // cancel bubble if we're already done

    if (ok) {
        replaceConnecting(false);
    } else {
        replaceConnecting(true);
        _welcomed = false; // allow retry on next open
    }
}

/** Periodic background ping — only updates the dot, no UI messages. */
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
        const d = document.getElementById("status-dot");
        if (d) d.style.backgroundColor = "#ef4444";
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
        anchors.push(`<a href="${href}" target="_blank" rel="noopener noreferrer" style="color:#4a1259;word-break:break-word;">${text}</a>`);
        return `\x00A${anchors.length - 1}\x00`;
    });
    s = s.replace(/<a\s+href="(mailto:[^"]+|tel:[^"]+)"[^>]*>(.*?)<\/a>/gi, (_, href, text) => {
        anchors.push(`<a href="${href}" style="color:#4a1259;">${text}</a>`);
        return `\x00A${anchors.length - 1}\x00`;
    });
    s = s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    return s.replace(/\x00A(\d+)\x00/g, (_, i) => anchors[+i]);
}

// ─── Quick-Reply Chip Parsing ─────────────────────────────────────────────────
/**
 * Parses a bot reply for:
 *   1. [OPTIONS: Label A | Label B | Label C]  → chip buttons
 *   2. A trailing question sentence              → "continue?" chip + question text
 *
 * Returns { mainText, options: string[], followUp: string|null }
 */
function parseReply(text) {
    let mainText = text;
    let options = [];
    let followUp = null;

    // 1. Extract [OPTIONS: ...] block (may be anywhere in the text)
    const optionsMatch = mainText.match(/\[OPTIONS:\s*([^\]]+)\]/i);
    if (optionsMatch) {
        options = optionsMatch[1].split("|").map(s => s.trim()).filter(Boolean);
        mainText = mainText.replace(optionsMatch[0], "").trim();
    }

    // 2. Extract a trailing follow-up question (last sentence ending with ?)
    // Requires a prior sentence-ending punctuation so the entire text is never consumed.
    const questionMatch = mainText.match(/(?:[.!?])\s+([A-Z][^.!?\n<]*\?)\s*$/);
    if (questionMatch && !options.length) {
        const q = questionMatch[1].trim();
        if (q.split(" ").length >= 4) { // at least 4 words = real question
            followUp = q;
            mainText = mainText.slice(0, mainText.lastIndexOf(q)).trim();
        }
    }

    return { mainText: mainText.trim(), options, followUp };
}

/**
 * Removes all existing quick-reply chip rows from the message container.
 * Called whenever the user submits a new message so old chips disappear.
 */
function clearQuickReplies() {
    const cw = document.getElementById("message-container");
    if (!cw) return;
    cw.querySelectorAll(".quick-reply-row").forEach(el => el.remove());
}

/**
 * Renders a row of quick-reply chip buttons below the last agent message.
 * Clicking a chip fills the input and submits it.
 */
function renderQuickReplies(chips, followUpText, botContext) {
    const cw = document.getElementById("message-container");
    if (!cw || !chips.length) return;

    const row = document.createElement("div");
    row.className = "quick-reply-row";
    row.style.cssText = [
        "display:flex",
        "flex-wrap:wrap",
        "gap:0.4rem",
        "padding:0.25rem 0.25rem 0.5rem 0.25rem",
        "align-self:flex-start",
        "max-width:95%",
    ].join(";") + ";";

    // Optional: show follow-up question text as a small label above chips
    if (followUpText) {
        const label = document.createElement("div");
        label.style.cssText = "width:100%;font-size:0.72rem;color:#6b7280;font-family:sans-serif;font-style:italic;margin-bottom:0.15rem;padding:0 0.1rem;";
        label.textContent = followUpText;
        row.appendChild(label);
    }

    chips.forEach(chipText => {
        const btn = document.createElement("button");
        btn.className = "quick-reply-chip";
        btn.textContent = chipText;
        btn.style.cssText = [
            "background:white",
            "border:1.5px solid #6e3061",
            "border-radius:1rem",
            "padding:0.35rem 0.75rem",
            "font-size:0.8rem",
            "font-family:var(--cb-font-sans,sans-serif)",
            "color:#6e3061",
            "cursor:pointer",
            "transition:background 0.15s,color 0.15s",
            "white-space:nowrap",
        ].join(";") + ";";

        btn.addEventListener("mouseenter", () => {
            btn.style.background = "#6e3061";
            btn.style.color = "white";
        });
        btn.addEventListener("mouseleave", () => {
            btn.style.background = "white";
            btn.style.color = "#6e3061";
        });
        btn.addEventListener("click", () => {
            // displayText = the chip label shown in the user bubble
            // apiText     = enriched with context so the backend understands the reply
            const context = followUpText || botContext || "";
            const apiText = context
                ? `${chipText} (regarding: "${context.slice(0, 120)}")`
                : chipText;
            handleChat(chipText, apiText);
        });
        row.appendChild(btn);
    });

    cw.appendChild(row);
    cw.scrollTop = cw.scrollHeight;
}

// ─── Display ──────────────────────────────────────────────────────────────────
function displayMessage(role, text, skipChips = false) {
    const cw = document.getElementById("message-container");
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
        // For agent messages, parse out options/follow-ups before displaying
        if (role !== "You" && !skipChips) {
            const { mainText, options, followUp } = parseReply(text);
            bubble.innerHTML = `<p style="color:#111827;margin:0;padding:0;font-size:1rem;line-height:1.5;">${sanitizeHtml(mainText)}</p>`;
            wrapper.appendChild(bubble);
            const meta = document.createElement("div");
            meta.style.cssText = "display:flex;align-items:center;gap:0.4rem;margin-top:0.25rem;padding:0 0.25rem;";
            const name = document.createElement("span"); name.className = "profile-name"; name.textContent = "Rammy";
            const ts = document.createElement("span"); ts.textContent = getTimestamp();
            ts.style.cssText = "font-size:0.6rem;color:#c4c9d4;font-family:sans-serif;font-style:italic;";
            meta.appendChild(name); meta.appendChild(ts);
            wrapper.appendChild(meta);
            cw.appendChild(wrapper);
            // Render chips after the wrapper
            if (options.length) renderQuickReplies(options, followUp, mainText);
            else if (followUp) renderQuickReplies(["Yes, please!", "No thanks"], followUp, mainText);
            cw.scrollTop = cw.scrollHeight;
            return;
        } else {
            bubble.innerHTML = `<p style="color:#111827;margin:0;padding:0;font-size:1rem;line-height:1.5;">${sanitizeHtml(text)}</p>`;
        }
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

    cw.appendChild(wrapper);
    cw.scrollTop = cw.scrollHeight;
}

function replaceLoadingBubble(text) {
    const loader = document.getElementById("loading-bubble");
    if (!loader) return;
    const parent = loader.parentElement;
    const cw = document.getElementById("message-container");

    const { mainText, options, followUp } = parseReply(text);

    loader.id = "";
    loader.className = "agent-bubble";
    loader.innerHTML = `<p style="color:#111827;margin:0;padding:0;font-size:1rem;line-height:1.5;">${sanitizeHtml(mainText)}</p>`;

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

    if (cw) cw.scrollTop = 99999;

    // Render chips after the loading bubble is replaced
    if (options.length) renderQuickReplies(options, followUp, mainText);
    else if (followUp) renderQuickReplies(["Yes, please!", "No thanks"], followUp, mainText);

    if (cw) cw.scrollTop = 99999;
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
    return (await res.json()).reply;
}

async function handleChat(displayText, apiText) {
    const input = document.getElementById("chat-user-input");
    if (!input) return;

    // displayText = what shows in the bubble (chip label, or raw input)
    // apiText     = what gets sent to the API (may include hidden context)
    const visibleText = displayText || input.value.trim();
    const sendText    = apiText    || visibleText;

    if (!visibleText) return;
    input.value = "";

    if (sendText.toLowerCase() === "/refresh") {
        try { await fetch(`${API_BASE}/refresh`, { method: "POST" }); displayMessage("Agent", "Sources are refreshing!"); }
        catch { displayMessage("Agent", "Could not reach the server."); }
        return;
    }

    clearQuickReplies();
    displayMessage("You", visibleText);   // show only the friendly label
    addHistory("user", sendText);          // store full context in history
    displayMessage("Typing", "");
    setInputEnabled(false);

    try {
        const reply = await fetchReply(sendText);
        replaceLoadingBubble(reply);
        addHistory("assistant", reply);
    } catch {
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

    const items = [
        { icon: "🗑️", label: "Clear conversation", fn: () => {
            if (!confirm("Clear conversation?")) return;
            const m = document.getElementById("message-container");
            if (m) m.innerHTML = "";
            history = [];
            _welcomed = false;
            addHistory("assistant", WELCOME);
            displayMessage("Agent", WELCOME, true); // skipChips=true — topic chips added manually below
            _welcomed = true;
        }},
        { icon: "🔄", label: "Refresh HR sources", fn: async () => {
            try { await fetch(`${API_BASE}/refresh`, { method: "POST" }); displayMessage("Agent", "Refreshing sources…"); }
            catch { displayMessage("Agent", "Could not refresh."); }
        }},
        { icon: "📧", label: "Contact HR", fn: () => {
            displayMessage("Agent", `Reach WCU HR at <a href="mailto:HRS@wcupa.edu" style="color:#4a1259;">HRS@wcupa.edu</a> or <a href="tel:6104362800" style="color:#4a1259;">610-436-2800</a>.`);
        }},
    ];

    items.forEach(item => {
        const btn = document.createElement("button");
        btn.style.cssText = "width:100%!important;padding:0.75rem 1rem!important;display:flex!important;flex-direction:row!important;align-items:center!important;gap:0.6rem!important;font-size:0.875rem!important;color:#374151!important;background:white!important;border:none!important;border-bottom:1px solid #f3f4f6!important;cursor:pointer!important;text-align:left!important;box-sizing:border-box!important;";
        const ico = document.createElement("span");
        ico.textContent = item.icon;
        const lbl = document.createElement("span");
        lbl.style.color = "#374151";
        lbl.textContent = item.label;
        btn.appendChild(ico);
        btn.appendChild(lbl);
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

// ─── Wire Buttons ─────────────────────────────────────────────────────────────
window.addEventListener("load", () => {
    // Force container hidden and button visible
    forceHide();
    const btn = document.getElementById("chat-btn");
    if (btn) btn.style.setProperty("display", "flex", "important");

    // Wire buttons
    document.getElementById("chat-btn")
        ?.addEventListener("click", openChat);
    document.getElementById("chat-close-btn")
        ?.addEventListener("click", closeChat);
    document.getElementById("chat-options-btn")
        ?.addEventListener("click", (e) => { e.stopPropagation(); createDropdown(); });

    const form = document.getElementById("chat-user-form");
    if (form) form.addEventListener("submit", (e) => { e.preventDefault(); handleChat(); });

    checkStatus();
    setInterval(checkStatus, 30000);
});
