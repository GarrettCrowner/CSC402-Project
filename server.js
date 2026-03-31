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

const PYTHON_BASE_URL = process.env.PYTHON_BASE_URL || "http://127.0.0.1:5001";
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
 * GET /api/document/:filename
 * Proxies a PDF from the Python /document/ endpoint so the browser
 * only ever talks to port 3000 (no direct Flask exposure needed).
 */
app.get("/api/document/:filename", async (req, res) => {
  const { filename } = req.params;
  try {
    const response = await axios.get(
      `${PYTHON_BASE_URL}/document/${encodeURIComponent(filename)}`,
      { responseType: "stream", timeout: 15000 }
    );
    res.setHeader("Content-Type", "application/pdf");
    res.setHeader("Content-Disposition", `inline; filename="${filename}"`);
    res.setHeader("Cache-Control", "private, max-age=3600");
    response.data.pipe(res);
  } catch (err) {
    const status = err.response?.status || 503;
    res.status(status).json({ error: `Could not retrieve document '${filename}'.` });
  }
});

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
 * GET /api/analytics
 * Proxies analytics data from the Python service.
 * Query params: ?limit=N
 */
app.get("/api/analytics", async (req, res) => {
  const limit = req.query.limit || 1000;
  try {
    const response = await axios.get(
      `${PYTHON_BASE_URL}/analytics?limit=${limit}`,
      { timeout: 10000 }
    );
    return res.json(response.data);
  } catch (err) {
    console.error("[/api/analytics] Error:", err.message);
    return res.status(503).json({ error: "Could not fetch analytics." });
  }
});

/**
 * GET /api/pdf/:filename
 * Proxies a PDF file from MinIO so the browser can open it directly
 * without needing MinIO credentials or dealing with CORS.
 *
 * The filename comes from the Qdrant payload url field (after stripping "pdf:").
 * Example: GET /api/pdf/employee-handbook.pdf
 *          → streams the file from MinIO bucket "documents"
 */
app.get("/api/pdf/:filename", async (req, res) => {
  const filename = req.params.filename;

  // Basic guard — no path traversal
  if (!filename || filename.includes("..") || filename.includes("/")) {
    return res.status(400).json({ error: "Invalid filename." });
  }

  const MINIO_HOST   = process.env.MINIO_HOST   || "minio:9000";
  const MINIO_BUCKET = process.env.MINIO_BUCKET || "documents";
  const minioUrl     = `http://${MINIO_HOST}/${MINIO_BUCKET}/${encodeURIComponent(filename)}`;

  try {
    const upstream = await axios.get(minioUrl, {
      responseType: "stream",
      timeout: 15000,
      // MinIO anonymous access works if the bucket policy allows public read.
      // If your bucket is private, add an Authorization header here or
      // use the MinIO SDK with credentials (minio npm package).
    });

    res.setHeader("Content-Type", upstream.headers["content-type"] || "application/pdf");
    res.setHeader("Content-Disposition", `inline; filename="${filename}"`);

    // Stream the PDF directly to the browser
    upstream.data.pipe(res);
  } catch (err) {
    if (err.response?.status === 403 || err.response?.status === 401) {
      // Bucket is private — return a helpful error rather than a silent failure
      return res.status(403).json({
        error: "This PDF is stored in a private MinIO bucket. " +
               "Set the bucket policy to public-read in the MinIO console " +
               "(http://localhost:9001) or configure server-side credentials.",
      });
    }
    if (err.response?.status === 404) {
      return res.status(404).json({ error: `PDF not found: ${filename}` });
    }
    console.error("[/api/pdf] Error fetching from MinIO:", err.message);
    return res.status(502).json({ error: "Could not retrieve PDF from storage." });
  }
});


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
