/*
 * Rammy HR Chatbot — chat.js (Fully Wired)
 *
 * Changes vs original:
 *   - API_URL now points at the Node.js REST server (/api/chat)
 *   - Agent.send() makes a real fetch() call instead of simulating a reply
 *   - conversationHistory array keeps the last 8 turns for context
 *   - Error messages surface gracefully in the chat bubble
 *   - Enter key submits the form (no extra JS needed — form submit handles it)
 *   - /refresh command triggers the knowledge-base refresh endpoint
 */

// ─── Config ───────────────────────────────────────────────────────────────────

const API_BASE = "http://localhost:3000/api";   // Node.js REST server

// ─── DOM References ───────────────────────────────────────────────────────────

const chatWindow  = document.getElementById("message-container");
const inputField  = document.getElementById("chat-user-input");
const sendBtn     = document.getElementById("send-btn");
const chatForm    = document.getElementById("chat-user-form");

// ─── Conversation History ─────────────────────────────────────────────────────

// Keeps the last MAX_HISTORY_TURNS * 2 messages (user + assistant pairs)
const MAX_HISTORY_TURNS = 4;
let conversationHistory = [];   // [{ role: "user"|"assistant", content: string }]

function addToHistory(role, content) {
    conversationHistory.push({ role, content });
    // Trim to last 8 messages (4 turns)
    if (conversationHistory.length > MAX_HISTORY_TURNS * 2) {
        conversationHistory = conversationHistory.slice(-(MAX_HISTORY_TURNS * 2));
    }
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
        newBubble.innerHTML = `<p>${escapeHtml(text)}</p>`;
    }

    messageWrapper.appendChild(newBubble);

    if (role !== "Typing") {
        const nameTag = document.createElement("span");
        nameTag.className = "profile-name";
        nameTag.textContent = (role === "You") ? "You" : "Rammy";
        messageWrapper.appendChild(nameTag);
    }

    chatWindow.appendChild(messageWrapper);
    chatWindow.scrollTop = chatWindow.scrollHeight;
}

/** Replace the loading bubble with the final agent reply */
function replaceLoadingBubble(text) {
    const loader = document.getElementById("loading-bubble");
    if (!loader) return;

    const parent = loader.parentElement;
    loader.id = "";
    loader.className = "agent-bubble";
    loader.innerHTML = `<p>${escapeHtml(text)}</p>`;

    const nameTag = document.createElement("span");
    nameTag.className = "profile-name";
    nameTag.textContent = "Rammy";
    parent.appendChild(nameTag);

    chatWindow.scrollTop = chatWindow.scrollHeight;
}

/** Minimal HTML escape to prevent XSS from API responses */
function escapeHtml(str) {
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
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
        body: JSON.stringify({
            message,
            history: conversationHistory,
        }),
    });

    if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.error || `Server error (${response.status})`);
    }

    const data = await response.json();
    return data.reply;
}

async function triggerRefresh() {
    try {
        await fetch(`${API_BASE}/refresh`, { method: "POST" });
        displayMessage("Agent", "Sources are refreshing in the background — I'll be up to date shortly!");
    } catch {
        displayMessage("Agent", "Could not reach the server to refresh sources.");
    }
}

// ─── Core Send Flow ───────────────────────────────────────────────────────────

async function handleChat() {
    const text = inputField.value.trim();
    if (!text) return;

    inputField.value = "";

    // Special command: /refresh
    if (text.toLowerCase() === "/refresh") {
        await triggerRefresh();
        return;
    }

    // Show user message
    displayMessage("You", text);
    addToHistory("user", text);

    // Show typing indicator and lock input
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

// Prefer form submit so Enter key works naturally
if (chatForm) {
    chatForm.addEventListener("submit", (e) => {
        e.preventDefault();
        handleChat();
    });
} else {
    // Fallback if form isn't wrapping the input
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
    const welcomeText =
        "Hi, my name is Rammy. I am here to help with all of your HR questions! What would you like to know?";

    addToHistory("assistant", welcomeText);
    displayMessage("Agent", welcomeText);
};
