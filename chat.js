/*
 * Rammy HR Chatbot — chat.js (Embedded Version)
 *
 * Designed to be dropped into any WCU page alongside styling_Rev1.css.
 * The host page provides:
 *   - #chat-btn         — the "Questions? Ask Rammy" pill button
 *   - #chat-container   — the chat window (starts display:none in CSS)
 *   - #chat-header      — header bar
 *   - #chat-close-btn   — X button
 *   - #chat-options-btn — options button
 *   - #message-container — scrollable message area
 *   - #chat-user-form   — wraps input + send button
 *   - #chat-user-input  — text input
 *   - #send-btn         — submit button
 *   - #status-dot       — connectivity indicator (optional)
 *
 * restoreChat() is exposed globally so the host HTML can call it via onclick.
 */

// ─── Config ───────────────────────────────────────────────────────────────────

const API_BASE = "http://localhost:3000/api";

// ─── DOM References ───────────────────────────────────────────────────────────

const chatWindow    = document.getElementById("message-container");
const inputField    = document.getElementById("chat-user-input");
const sendBtn       = document.getElementById("send-btn");
const chatForm      = document.getElementById("chat-user-form");
const chatContainer = document.getElementById("chat-container");
const closeBtn      = document.getElementById("chat-close-btn");
const optionsBtn    = document.getElementById("chat-options-btn");
const chatBtn       = document.getElementById("chat-btn");

// ─── Conversation History ─────────────────────────────────────────────────────

const MAX_HISTORY_TURNS = 4;
let conversationHistory = [];

function addToHistory(role, content) {
    conversationHistory.push({ role, content });
    if (conversationHistory.length > MAX_HISTORY_TURNS * 2) {
        conversationHistory = conversationHistory.slice(-(MAX_HISTORY_TURNS * 2));
    }
}

// ─── Status Dot ───────────────────────────────────────────────────────────────

async function checkStatus() {
    const dot = document.getElementById("status-dot");
    if (!dot) return;
    try {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 3000);
        const res = await fetch(`${API_BASE}/health`, { signal: controller.signal });
        clearTimeout(timer);
        const data = await res.json();
        const online = data.status === "ok" && data.python === "reachable";
        dot.style.backgroundColor = online ? "#22c55e" : "#ef4444";
        dot.title = online ? "Connected" : "Backend unavailable";
    } catch {
        dot.style.backgroundColor = "#ef4444";
        dot.title = "Cannot reach server";
    }
}

window.addEventListener("load", () => {
    checkStatus();
    setInterval(checkStatus, 30000);
});

// ─── Minimize / Restore ───────────────────────────────────────────────────────

let _chatOpen = false;

function minimizeChat() {
    if (!_chatOpen) return;
    _chatOpen = false;
    chatContainer.style.transition = "transform 0.3s ease, opacity 0.3s ease";
    chatContainer.style.transform = "translateY(20px)";
    chatContainer.style.opacity = "0";
    setTimeout(() => {
        chatContainer.style.display = "none";
        chatContainer.style.transform = "";
        chatContainer.style.opacity = "";
        if (chatBtn) chatBtn.style.display = "flex";
    }, 300);
}

window.restoreChat = function() {
    if (_chatOpen) return;
    _chatOpen = true;
    chatContainer.style.display = "flex";
    chatContainer.style.flexDirection = "column";
    chatContainer.style.transform = "translateY(20px)";
    chatContainer.style.opacity = "0";
    chatContainer.style.transition = "transform 0.3s ease, opacity 0.3s ease";
    if (chatBtn) chatBtn.style.display = "none";
    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            chatContainer.style.transform = "translateY(0)";
            chatContainer.style.opacity = "1";
        });
    });
    setTimeout(() => inputField.focus(), 310);
};

// Wire chat button in JS — remove onclick from HTML to avoid WCU JS interference
if (chatBtn) {
    chatBtn.removeAttribute("onclick");
    chatBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        window.restoreChat();
    });
}

if (closeBtn) closeBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    e.preventDefault();
    minimizeChat();
});

// ─── Options Dropdown ─────────────────────────────────────────────────────────

function createDropdown() {
    const existing = document.getElementById("options-dropdown");
    if (existing) { existing.remove(); return; }

    const dropdown = document.createElement("div");
    dropdown.id = "options-dropdown";
    dropdown.style.cssText = `
        position: absolute !important;
        top: 56px !important;
        right: 12px !important;
        background: white !important;
        border-radius: 0.75rem !important;
        box-shadow: 0 8px 24px rgba(0,0,0,0.15) !important;
        overflow: hidden !important;
        z-index: 99999 !important;
        min-width: 200px !important;
        font-family: 'Quicksand', sans-serif !important;
    `;

    const items = [
        { icon: "🗑️", label: "Clear conversation", action: clearConversation },
        { icon: "🔄", label: "Refresh HR sources",  action: refreshSources   },
        { icon: "📧", label: "Contact HR",           action: contactHR        },
    ];

    items.forEach(item => {
        const btn = document.createElement("button");
        // Use cssText with !important on every property to override WCU styles
        btn.style.cssText = `
            width: 100% !important;
            padding: 0.75rem 1rem !important;
            display: flex !important;
            flex-direction: row !important;
            align-items: center !important;
            justify-content: flex-start !important;
            gap: 0.6rem !important;
            font-size: 0.875rem !important;
            font-family: 'Quicksand', sans-serif !important;
            color: #374151 !important;
            border-radius: 0 !important;
            background: white !important;
            cursor: pointer !important;
            border: none !important;
            border-bottom: 1px solid #f3f4f6 !important;
            box-sizing: border-box !important;
            text-align: left !important;
            line-height: 1.4 !important;
        `;
        const icon = document.createElement("span");
        icon.textContent = item.icon;
        icon.style.cssText = `display:inline-block !important; flex-shrink:0 !important; font-size:1rem !important;`;
        const label = document.createElement("span");
        label.textContent = item.label;
        label.style.cssText = `display:inline-block !important; color:#374151 !important; font-size:0.875rem !important;`;
        btn.appendChild(icon);
        btn.appendChild(label);
        btn.addEventListener("mouseenter", () => btn.style.background = "#f9fafb");
        btn.addEventListener("mouseleave", () => btn.style.background = "white");
        btn.addEventListener("click", (e) => {
            e.stopPropagation();
            dropdown.remove();
            item.action();
        });
        dropdown.appendChild(btn);
    });

    const header = document.getElementById("chat-header");
    header.style.position = "relative";
    header.appendChild(dropdown);

    setTimeout(() => {
        document.addEventListener("click", function handler(e) {
            if (!dropdown.contains(e.target) && e.target !== optionsBtn) {
                dropdown.remove();
                document.removeEventListener("click", handler);
            }
        });
    }, 10);
}

function clearConversation() {
    if (!confirm("Clear the conversation? This cannot be undone.")) return;
    chatWindow.innerHTML = "";
    conversationHistory = [];
    const welcomeText = "Hi, my name is Rammy. I am here to help with all of your HR questions! What would you like to know?";
    addToHistory("assistant", welcomeText);
    displayMessage("Agent", welcomeText);
}

async function refreshSources() {
    try {
        await fetch(`${API_BASE}/refresh`, { method: "POST" });
        displayMessage("Agent", "Sources are refreshing in the background — I'll be up to date shortly!");
    } catch {
        displayMessage("Agent", "Could not reach the server to refresh sources.");
    }
}

function contactHR() {
    displayMessage("Agent", `You can reach WCU HR directly at <a href="mailto:HRS@wcupa.edu" style="color:#6E3061;">HRS@wcupa.edu</a> or by phone at <a href="tel:6104362800" style="color:#6E3061;">610-436-2800</a>.`);
}

if (optionsBtn) {
    optionsBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        createDropdown();
    });
}

// ─── Timestamps ───────────────────────────────────────────────────────────────

function getTimestamp() {
    const now = new Date();
    let hours = now.getHours();
    const mins = now.getMinutes().toString().padStart(2, "0");
    const ampm = hours >= 12 ? "PM" : "AM";
    hours = hours % 12 || 12;
    return `${hours}:${mins} ${ampm}`;
}

// ─── UI Helpers ───────────────────────────────────────────────────────────────

function displayMessage(role, text) {
    const messageWrapper = document.createElement("div");
    messageWrapper.className = (role === "You") ? "user-msg-wrapper" : "agent-msg-wrapper";

    const newBubble = document.createElement("div");

    if (role === "Typing") {
        newBubble.className = "agent-bubble typing-indicator";
        newBubble.id = "loading-bubble";
        newBubble.innerHTML = `<div class="dot"></div><div class="dot"></div><div class="dot"></div>`;
    } else {
        newBubble.className = (role === "You") ? "user-bubble" : "agent-bubble";
        newBubble.innerHTML = `<p>${sanitizeHtml(text)}</p>`;
    }

    messageWrapper.appendChild(newBubble);

    if (role !== "Typing") {
        const metaRow = document.createElement("div");
        metaRow.style.cssText = `
            display: flex;
            align-items: center;
            gap: 0.4rem;
            margin-top: 0.25rem;
            padding: 0 0.25rem;
        `;

        const nameTag = document.createElement("span");
        nameTag.className = "profile-name";
        nameTag.textContent = (role === "You") ? "You" : "Rammy";

        const timestamp = document.createElement("span");
        timestamp.textContent = getTimestamp();
        timestamp.style.cssText = `font-size:0.6rem;color:#c4c9d4;font-family:sans-serif;font-style:italic;letter-spacing:0.02em;`;

        metaRow.appendChild(nameTag);
        metaRow.appendChild(timestamp);
        messageWrapper.appendChild(metaRow);
    }

    chatWindow.appendChild(messageWrapper);
    chatWindow.scrollTop = chatWindow.scrollHeight;
}

function replaceLoadingBubble(text) {
    const loader = document.getElementById("loading-bubble");
    if (!loader) return;

    const parent = loader.parentElement;
    loader.id = "";
    loader.className = "agent-bubble";
    loader.innerHTML = `<p>${sanitizeHtml(text)}</p>`;

    const metaRow = document.createElement("div");
    metaRow.style.cssText = `display:flex;align-items:center;gap:0.4rem;margin-top:0.25rem;padding:0 0.25rem;`;

    const nameTag = document.createElement("span");
    nameTag.className = "profile-name";
    nameTag.textContent = "Rammy";

    const timestamp = document.createElement("span");
    timestamp.textContent = getTimestamp();
    timestamp.style.cssText = `font-size:0.6rem;color:#c4c9d4;font-family:sans-serif;font-style:italic;letter-spacing:0.02em;`;

    metaRow.appendChild(nameTag);
    metaRow.appendChild(timestamp);
    parent.appendChild(metaRow);

    chatWindow.scrollTop = chatWindow.scrollHeight;
}

function sanitizeHtml(str) {
    const anchors = [];
    let s = String(str);

    s = s.replace(/<a\s+href="(https?:\/\/[^"]+)"\s*[^>]*>(.*?)<\/a>/gi,
        (match, href, text) => {
            anchors.push(`<a href="${href}" target="_blank" rel="noopener noreferrer" style="color:#6E3061;word-break:break-word;">${text}</a>`);
            return `\x00ANCHOR${anchors.length - 1}\x00`;
        });

    s = s.replace(/<a\s+href="(mailto:[^"]+|tel:[^"]+)"\s*[^>]*>(.*?)<\/a>/gi,
        (match, href, text) => {
            anchors.push(`<a href="${href}" style="color:#6E3061;">${text}</a>`);
            return `\x00ANCHOR${anchors.length - 1}\x00`;
        });

    s = s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    return s.replace(/\x00ANCHOR(\d+)\x00/g, (_, i) => anchors[parseInt(i)]);
}

function setInputEnabled(enabled) {
    inputField.disabled = !enabled;
    sendBtn.disabled    = !enabled;
}

// ─── API Calls ────────────────────────────────────────────────────────────────

async function fetchReply(message) {
    const response = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, history: conversationHistory }),
    });
    if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.error || `Server error (${response.status})`);
    }
    const data = await response.json();
    return data.reply;
}

// ─── Core Send Flow ───────────────────────────────────────────────────────────

async function handleChat() {
    const text = inputField.value.trim();
    if (!text) return;
    inputField.value = "";

    if (text.toLowerCase() === "/refresh") {
        await refreshSources();
        return;
    }

    displayMessage("You", text);
    addToHistory("user", text);
    displayMessage("Typing", "");
    setInputEnabled(false);

    try {
        const reply = await fetchReply(text);
        replaceLoadingBubble(reply);
        addToHistory("assistant", reply);
    } catch (err) {
        console.error("Chat error:", err);
        replaceLoadingBubble("Sorry, I'm having trouble connecting right now. Please try again.");
    } finally {
        setInputEnabled(true);
        inputField.focus();
    }
}

// ─── Event Listeners ──────────────────────────────────────────────────────────

if (chatForm) {
    chatForm.addEventListener("submit", (e) => {
        e.preventDefault();
        handleChat();
    });
} else {
    sendBtn.addEventListener("click", handleChat);
    inputField.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleChat();
        }
    });
}

// ─── Startup ──────────────────────────────────────────────────────────────────

window.onload = () => {
    const welcomeText = "Hi, my name is Rammy. I am here to help with all of your HR questions! What would you like to know?";
    addToHistory("assistant", welcomeText);
    displayMessage("Agent", welcomeText);
};
