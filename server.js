/**
 * Rammy HR Chatbot — Node.js REST API Server
 * Bridges the Vanilla JS frontend and Python backend via HTTP.
 *
 * Endpoints:
 *   POST /api/chat      → Send a message, get a reply
 *   POST /api/refresh   → Trigger a knowledge-base refresh on the Python side
 *   GET  /api/health    → Heartbeat check
 */

const express = require("express");
const cors = require("cors");
const axios = require("axios");
const rateLimit = require("express-rate-limit");
require("dotenv").config();

const app = express();

// ─── Middleware ────────────────────────────────────────────────────────────────

app.use(express.json());

// Allow requests from your frontend origin only (set FRONTEND_ORIGIN in .env)
app.use(
  cors({
    origin: process.env.FRONTEND_ORIGIN || "*",
    methods: ["GET", "POST"],
  })
);

// Rate limiting — 60 requests per minute per IP
const limiter = rateLimit({
  windowMs: 60 * 1000,
  max: 60,
  standardHeaders: true,
  legacyHeaders: false,
  message: { error: "Too many requests — please slow down." },
});
app.use("/api/", limiter);

// ─── Config ───────────────────────────────────────────────────────────────────

const PYTHON_BASE_URL = process.env.PYTHON_BASE_URL || "http://127.0.0.1:5000";
const PORT = process.env.PORT || 3000;

// ─── Input Validation ─────────────────────────────────────────────────────────

/**
 * Very light server-side guard before forwarding to Python.
 * Python does the real PII check — this just blocks obviously bad payloads.
 */
function validateChatPayload(req, res, next) {
  const { message, history } = req.body;

  if (!message || typeof message !== "string") {
    return res.status(400).json({ error: "message field is required and must be a string." });
  }

  if (message.trim().length === 0) {
    return res.status(400).json({ error: "message cannot be empty." });
  }

  if (message.length > 2000) {
    return res.status(400).json({ error: "message exceeds maximum length of 2000 characters." });
  }

  if (history !== undefined && !Array.isArray(history)) {
    return res.status(400).json({ error: "history must be an array." });
  }

  next();
}

// ─── Routes ───────────────────────────────────────────────────────────────────

/**
 * GET /api/health
 * Quick liveness check. Also pings the Python service.
 */
app.get("/api/health", async (req, res) => {
  try {
    await axios.get(`${PYTHON_BASE_URL}/health`, { timeout: 3000 });
    res.json({ status: "ok", python: "reachable" });
  } catch {
    res.status(503).json({ status: "degraded", python: "unreachable" });
  }
});

/**
 * POST /api/chat
 * Body: { message: string, history?: Array<{ role: string, content: string }> }
 * Returns: { reply: string }
 */
app.post("/api/chat", validateChatPayload, async (req, res) => {
  const { message, history = [] } = req.body;

  // Trim history to last 8 turns before forwarding (mirrors Python's own cap)
  const trimmedHistory = history.slice(-8);

  try {
    const response = await axios.post(
      `${PYTHON_BASE_URL}/chat`,
      { message, history: trimmedHistory },
      { timeout: 30000 } // 30 s — allow time for slow LLM responses
    );

    return res.json({ reply: response.data.reply });
  } catch (err) {
    // Propagate Python-side error messages when available
    if (err.response) {
      const status = err.response.status;
      const detail = err.response.data?.error || "Python service error.";
      return res.status(status).json({ error: detail });
    }

    // Network / timeout
    console.error("[/api/chat] Python unreachable:", err.message);
    return res.status(503).json({
      error: "The chatbot backend is temporarily unavailable. Please try again.",
    });
  }
});

/**
 * POST /api/refresh
 * Triggers a knowledge-base refresh on the Python service.
 * Returns: { message: string }
 */
app.post("/api/refresh", async (req, res) => {
  try {
    const response = await axios.post(`${PYTHON_BASE_URL}/refresh`, {}, { timeout: 60000 });
    return res.json({ message: response.data.message || "Sources refreshed." });
  } catch (err) {
    console.error("[/api/refresh] Error:", err.message);
    return res.status(503).json({ error: "Could not refresh sources." });
  }
});

// ─── Start ────────────────────────────────────────────────────────────────────

app.listen(PORT, () => {
  console.log(`Rammy Node.js API running on http://localhost:${PORT}`);
});
