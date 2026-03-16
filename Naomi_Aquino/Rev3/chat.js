/*
 * Rammy HR Chatbot — chat.js
 *
 * Features:
 *   - Real API calls to Node.js REST server
 *   - Conversation history (last 8 turns)
 *   - Message timestamps
 *   - Live status dot (green/red) showing backend connectivity
 *   - Close button — minimizes chat to floating bubble
 *   - Options dropdown — Clear conversation, Refresh sources, Contact HR
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
        const res = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(3000) });
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

function createBubbleLauncher() {
    chatContainer.style.display = "none";
    
    const bubble = document.createElement("div");
    bubble.id = "rammy-bubble";
    bubble.innerHTML = `
        <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="white" style="flex-shrink:0;">
            <path d="M20 2H4C2.9 2 2 2.9 2 4v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 12H6l-2 2V4h16v10z"/>
        </svg>
        <span style="font-family:'Quicksand',sans-serif;font-weight:700;font-size:0.85rem;letter-spacing:0.05em;color:white;">QUESTIONS? ASK RAMMY</span>
    `;
    bubble.style.cssText = `
        position: fixed;
        bottom: 24px;
        right: 24px;
        display: flex;
        align-items: center;
        gap: 10px;
        background-color: #6E3061;
        padding: 14px 22px;
        border-radius: 50px;
        cursor: pointer;
        box-shadow: 0 4px 16px rgba(0,0,0,0.25);
        z-index: 1000;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    `;
    bubble.addEventListener("mouseenter", () => {
        bubble.style.transform = "scale(1.04)";
        bubble.style.boxShadow = "0 6px 20px rgba(0,0,0,0.3)";
    });
    bubble.addEventListener("mouseleave", () => {
        bubble.style.transform = "scale(1)";
        bubble.style.boxShadow = "0 4px 16px rgba(0,0,0,0.25)";
    });
    bubble.addEventListener("click", restoreChat);
    document.body.appendChild(bubble);
}

function minimizeChat() {
    chatContainer.style.display = "none";
    createBubbleLauncher();
}

function restoreChat() {
    chatContainer.style.display = "flex";
    const bubble = document.getElementById("rammy-bubble");
    if (bubble) bubble.remove();
    inputField.focus();
}

closeBtn.addEventListener("click", minimizeChat);

// ─── Options Dropdown ─────────────────────────────────────────────────────────

function createDropdown() {
    const existing = document.getElementById("options-dropdown");
    if (existing) { existing.remove(); return; }

    const dropdown = document.createElement("div");
    dropdown.id = "options-dropdown";
    dropdown.style.cssText = `
        position: absolute;
        top: 56px;
        right: 12px;
        background: white;
        border-radius: 0.75rem;
        box-shadow: 0 8px 24px rgba(0,0,0,0.15);
        overflow: hidden;
        z-index: 100;
        min-width: 200px;
        font-family: 'Nunito', sans-serif;
    `;

    const items = [
        { icon: "🗑️", label: "Clear conversation", action: clearConversation },
        { icon: "🔄", label: "Refresh HR sources",  action: refreshSources   },
        { icon: "📧", label: "Contact HR",           action: contactHR        },
    ];

    items.forEach(item => {
        const btn = document.createElement("button");
        btn.style.cssText = `
            width: 100%;
            padding: 0.75rem 1rem;
            display: flex;
            align-items: center;
            gap: 0.6rem;
            font-size: 0.875rem;
            color: #374151;
            border-radius: 0;
            background: white;
            cursor: pointer;
            border-bottom: 1px solid #f3f4f6;
            transition: background 0.15s ease;
        `;
        btn.innerHTML = `<span>${item.icon}</span><span>${item.label}</span>`;
        btn.addEventListener("mouseenter", () => btn.style.background = "#f9fafb");
        btn.addEventListener("mouseleave", () => btn.style.background = "white");
        btn.addEventListener("click", () => {
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

optionsBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    createDropdown();
});

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
        timestamp.style.cssText = `font-size: 0.65rem; color: #9ca3af; font-family: sans-serif;`;

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
    timestamp.style.cssText = `font-size:0.65rem;color:#9ca3af;font-family:sans-serif;`;

    metaRow.appendChild(nameTag);
    metaRow.appendChild(timestamp);
    parent.appendChild(metaRow);

    chatWindow.scrollTop = chatWindow.scrollHeight;
}

function sanitizeHtml(str) {
    const anchors = [];
    let s = String(str);

    // Protect https links
    s = s.replace(/<a\s+href="(https?:\/\/[^"]+)"\s*[^>]*>(.*?)<\/a>/gi,
        (match, href, text) => {
            anchors.push(`<a href="${href}" target="_blank" rel="noopener noreferrer" style="color:#6E3061;word-break:break-word;">${text}</a>`);
            return `\x00ANCHOR${anchors.length - 1}\x00`;
        });

    // Protect mailto and tel links
    s = s.replace(/<a\s+href="(mailto:[^"]+|tel:[^"]+)"\s*[^>]*>(.*?)<\/a>/gi,
        (match, href, text) => {
            anchors.push(`<a href="${href}" style="color:#6E3061;">${text}</a>`);
            return `\x00ANCHOR${anchors.length - 1}\x00`;
        });

    // Escape everything else
    s = s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

    // Restore safe anchors
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
