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

// ─── Accessibility Settings ──────────────────────────────────────────────────
const A11Y_KEY      = "rammy_a11y";
const A11Y_DEFAULTS = { fontSize: "medium", contrast: "normal", width: "default" };
const FONT_MAP  = { small: "0.85rem", medium: "1rem", large: "1.15rem", xlarge: "1.3rem" };
const WIDTH_MAP = { narrow: "320px", default: "400px", wide: "520px" };

function loadA11y() {
    try { return Object.assign({}, A11Y_DEFAULTS, JSON.parse(localStorage.getItem(A11Y_KEY) || "{}")); }
    catch { return Object.assign({}, A11Y_DEFAULTS); }
}

function saveA11y(s) {
    try { localStorage.setItem(A11Y_KEY, JSON.stringify(s)); } catch {}
}

function applyA11y(s) {
    const container = document.getElementById("chat-container");
    if (!container) return;

    container.setAttribute("data-width", s.width);
    container.setAttribute("data-font", s.fontSize);

    if (s.contrast === "high") {
        container.setAttribute("data-contrast", "high");
    } else {
        container.removeAttribute("data-contrast");
    }
}

// Apply saved settings on every page load
(function() {
    window.addEventListener("load", () => applyA11y(loadA11y()));
})();

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
        showConnecting();
        // checkStatusAndWelcome handles its own minimum display time internally
        // and calls replaceConnecting when ready — fire and forget here.
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
    p.className = "bubble-text";
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
        displayMessage("Agent", WELCOME);
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

/** Called on first open — checks health, waits for min display time, then swaps bubble. */
async function checkStatusAndWelcome() {
    const dot = document.getElementById("status-dot");
    let ok = false;
    try {
        const controller = new AbortController();
        const t = setTimeout(() => controller.abort(), 5000);
        const res = await fetch(`${API_BASE}/health`, { signal: controller.signal });
        clearTimeout(t);
        const data = await res.json();
        if (data.status === "ok") {
            ok = true;
            if (dot) dot.style.backgroundColor = "#22c55e";
        } else if (data.status === "loading") {
            // Backend is still initialising the embedding model — retry in 3 s
            if (dot) dot.style.backgroundColor = "#f59e0b"; // amber
            setTimeout(checkStatusAndWelcome, 3000);
            return;
        } else {
            if (dot) dot.style.backgroundColor = "#ef4444";
        }
    } catch {
        if (dot) dot.style.backgroundColor = "#ef4444";
    }

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
        if (data.status === "ok") dot.style.backgroundColor = "#22c55e";
        else if (data.status === "loading") dot.style.backgroundColor = "#f59e0b";
        else dot.style.backgroundColor = "#ef4444";
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

    function stashLink(href, text) {
        const isPdf = href.includes("/api/pdf/");
        const label = isPdf ? "\uD83D\uDCC4 " + text : text;
        if (/^https?:\/\//.test(href)) {
            anchors.push('<a href="' + href + '" target="_blank" rel="noopener noreferrer" style="color:#4a1259;word-break:break-word;">' + label + '</a>');
        } else if (/^mailto:|^tel:/.test(href)) {
            anchors.push('<a href="' + href + '" style="color:#4a1259;">' + text + '</a>');
        } else {
            anchors.push(text);
        }
        return "\x00A" + (anchors.length - 1) + "\x00";
    }

    // Double-quoted:  <a href="...">text</a>
    s = s.replace(/<a\s+href="([^"]+)"[^>]*>([\s\S]*?)<\/a>/gi,
        function(_, href, text) { return stashLink(href, text); });

    // Single-quoted:  <a href='...'>text</a>
    s = s.replace(/<a\s+href='([^']+)'[^>]*>([\s\S]*?)<\/a>/gi,
        function(_, href, text) { return stashLink(href, text); });

    // Escape everything else
    s = s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

    // Restore stashed anchors
    return s.replace(/\x00A(\d+)\x00/g, function(_, i) { return anchors[+i]; });
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

    // Optional: show follow-up question text as a small label above chips
    if (followUpText) {
        const label = document.createElement("div");
        label.className = "quick-reply-label";
        label.textContent = followUpText;
        row.appendChild(label);
    }

    chips.forEach(chipText => {
        const btn = document.createElement("button");
        btn.className = "quick-reply-chip";
        btn.textContent = chipText;
        btn.addEventListener("click", () => {
            // displayText = the chip label shown in the user bubble
            // apiText     = enriched with context so the backend understands the reply.
            // Don't append context if botContext is the welcome message — chips
            // rendered after the greeting are top-level topic starters, not replies.
            const context = (botContext && botContext !== WELCOME)
                ? (followUpText || botContext)
                : (followUpText || "");
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
function displayMessage(role, text) {
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
        if (role !== "You") {
            const { mainText, options, followUp } = parseReply(text);
            bubble.innerHTML = `<p class="bubble-text">${sanitizeHtml(mainText)}</p>`;
            wrapper.appendChild(bubble);
            const meta = document.createElement("div");
            meta.className = "msg-meta";
            const name = document.createElement("span"); name.className = "profile-name"; name.textContent = "Rammy";
            const ts = document.createElement("span"); ts.className = "timestamp"; ts.textContent = getTimestamp();
            meta.appendChild(name); meta.appendChild(ts);
            wrapper.appendChild(meta);
            cw.appendChild(wrapper);
            // Render chips after the wrapper
            if (options.length) renderQuickReplies(options, followUp, mainText);
            cw.scrollTop = cw.scrollHeight;
            return;
        } else {
            bubble.innerHTML = `<p class="bubble-text">${sanitizeHtml(text)}</p>`;
        }
    }
    wrapper.appendChild(bubble);

    if (role !== "Typing") {
        const meta = document.createElement("div");
        meta.className = "msg-meta";
        const name = document.createElement("span");
        name.className = "profile-name";
        name.textContent = role === "You" ? "You" : "Rammy";
        const ts = document.createElement("span");
        ts.className = "timestamp";
        ts.textContent = getTimestamp();
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
    loader.innerHTML = `<p class="bubble-text">${sanitizeHtml(mainText)}</p>`;

    const meta = document.createElement("div");
    meta.className = "msg-meta";
    const name = document.createElement("span");
    name.className = "profile-name";
    name.textContent = "Rammy";
    const ts = document.createElement("span");
    ts.className = "timestamp";
    ts.textContent = getTimestamp();
    meta.appendChild(name);
    meta.appendChild(ts);
    parent.appendChild(meta);

    if (cw) cw.scrollTop = 99999;

    // Render chips after the loading bubble is replaced
    if (options.length) renderQuickReplies(options, followUp, mainText);

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
function openA11yPanel() {
    const existing = document.getElementById("a11y-panel");
    if (existing) { existing.remove(); return; }

    const s = loadA11y();
    const container = document.getElementById("chat-container");
    if (!container) return;

    const panel = document.createElement("div");
    panel.id = "a11y-panel";

    function row(labelText, controlHtml) {
        return `
            <div class="a11y-row">
                <div class="a11y-label">${labelText}</div>
                ${controlHtml}
            </div>
        `;
    }

    function btnGroup(name, options, current) {
        return options.map(([val, lbl]) => {
            const active = val === current;
            return `<button class="a11y-btn${active ? " active" : ""}" data-a11y="${name}" data-val="${val}">${lbl}</button>`;
        }).join("");
    }

    panel.innerHTML = `
        <div class="a11y-header">
            <span class="a11y-title">Accessibility</span>
            <button id="a11y-close" class="a11y-close">✕</button>
        </div>
        ${row("Font size", btnGroup("fontSize",
            [["small","Small"],["medium","Medium"],["large","Large"],["xlarge","X-Large"]], s.fontSize))}
        ${row("Color Mode", btnGroup("contrast",
            [["normal","Light Mode"],["high","Dark Mode"]], s.contrast))}
        ${row("Window width", btnGroup("width",
            [["narrow","Narrow"],["default","Default"],["wide","Wide"]], s.width))}
        <button id="a11y-reset" class="a11y-reset">Reset to default</button>
    `;

    const footer = document.getElementById("chat-footer");
    if (footer) {
        footer.style.position = "relative";
        footer.appendChild(panel);
    } else {
        container.style.position = "relative";
        container.appendChild(panel);
    }

    panel.querySelectorAll("button[data-a11y]").forEach(btn => {
        btn.addEventListener("click", () => {
            const key = btn.getAttribute("data-a11y");
            const val = btn.getAttribute("data-val");
            const updated = loadA11y();
            updated[key] = val;
            saveA11y(updated);
            applyA11y(updated);
            panel.querySelectorAll(`button[data-a11y="${key}"]`).forEach(b => {
                const isActive = b.getAttribute("data-val") === val;
                b.className = isActive ? "a11y-btn active" : "a11y-btn";
            });
        });
    });

    panel.querySelector("#a11y-reset").addEventListener("click", () => {
        saveA11y(Object.assign({}, A11Y_DEFAULTS));
        applyA11y(Object.assign({}, A11Y_DEFAULTS));
        panel.remove();
        openA11yPanel();
    });

    panel.querySelector("#a11y-close").addEventListener("click", () => panel.remove());

    setTimeout(() => {
        document.addEventListener("click", function h(e) {
            if (!panel.contains(e.target)) {
                panel.remove();
                document.removeEventListener("click", h);
            }
        });
    }, 50);
}

function createDropdown() {
    const existing = document.getElementById("options-dropdown");
    if (existing) { existing.remove(); return; }

    const container = document.getElementById("chat-container");
    if (!container) return;

    const dropdown = document.createElement("div");
    dropdown.id = "options-dropdown";

    const items = [
        { icon: "", label: "Clear conversation", fn: () => {
            if (!confirm("Clear conversation?")) return;
            const m = document.getElementById("message-container");
            if (m) m.innerHTML = "";
            history = [];
            _welcomed = false;
            displayMessage("Agent", WELCOME);
            _welcomed = true;
        }},
        { icon: "", label: "Refresh HR sources", fn: async () => {
            try { await fetch(`${API_BASE}/refresh`, { method: "POST" }); displayMessage("Agent", "Refreshing sources…"); }
            catch { displayMessage("Agent", "Could not refresh."); }
        }},
        { icon: "", label: "Contact HR", fn: () => {
            displayMessage("Agent", `Reach WCU HR at <a href="mailto:HRS@wcupa.edu" style="color:#4a1259;">HRS@wcupa.edu</a> or <a href="tel:6104362800" style="color:#4a1259;">610-436-2800</a>.`);
        }},
        { icon: "", label: "Accessibility", fn: () => openA11yPanel() },
    ];

    items.forEach(item => {
        const btn = document.createElement("button");
        btn.className = "dropdown-item";
        const lbl = document.createElement("span");
        lbl.textContent = item.label;
        btn.appendChild(lbl);
        btn.addEventListener("click", () => { dropdown.remove(); item.fn(); });
        dropdown.appendChild(btn);
    });

    container.appendChild(dropdown);

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
