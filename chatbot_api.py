"""
Rammy HR Chatbot — Python Flask Backend (Optimized)

Changes vs original chatbot.py:
  - Wrapped in Flask so Node.js (or any client) can call it over HTTP.
  - Sources are fetched ONCE on startup and cached; /refresh endpoint reloads them.
  - Removed CLI loop (now an API service).
  - Fixed OpenAI call: client.responses.create → client.chat.completions.create
    (responses.create is not a valid OpenAI Python SDK method).
  - PII check and small-talk logic are unchanged.
  - Chunk scoring is unchanged; phrase-boost table is easier to extend.
  - Performance monitor removed (not meaningful in a server context;
    use a proper APM tool like Datadog or Sentry in production).
  - Added /health endpoint for Node.js to ping.
"""

import os
import re
import threading
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, request
from openai import OpenAI
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

# ─── Config ───────────────────────────────────────────────────────────────────

OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY", "")
OPENAI_ORG_ID    = os.getenv("OPENAI_ORG_ID", "")
OPENAI_PROJECT_ID = os.getenv("OPENAI_PROJECT_ID", "")

MODEL = "gpt-4.1-mini"

ALLOWED_URLS = [
    # ── Core HR ───────────────────────────────────────────────────────────────
    "https://www.wcupa.edu/hr/faqs.aspx",
    "https://www.wcupa.edu/hr/employee-labor-relations.aspx",
    "https://www.wcupa.edu/hr/student-employment.aspx",
    "https://www.wcupa.edu/hr/professional-development.aspx",
    # ── I-9 / Employment Verification ─────────────────────────────────────────
    "https://www.uscis.gov/i-9-central/form-i-9-acceptable-documents",
    # ── Leave ─────────────────────────────────────────────────────────────────
    "https://www.wcupa.edu/hr/FMLA.aspx",
    "https://www.passhe.edu/hr/benefits/life-events/index.html",
    # ── Retirement ────────────────────────────────────────────────────────────
    "https://www.passhe.edu/hr/benefits/retirement/index.html",
    "https://www.passhe.edu/hr/benefits/retirement/voluntary-retirement-plans.html",
    "https://www.passhe.edu/hr/benefits/retirement/tsa.html",
    "https://www.passhe.edu/hr/benefits/retirement/deferred-compensation.html",
    "https://www.passhe.edu/hr/benefits/retirement/arp.html",
    "https://www.passhe.edu/hr/benefits/retirement/sers.html",
    # ── Benefits ──────────────────────────────────────────────────────────────
    "https://www.wcupa.edu/hr/employee-benefits-vs-benefits-by-employee-group.aspx",
    # ── Workers Comp ──────────────────────────────────────────────────────────
    "https://www.wcupa.edu/hr/work-related-injuries.aspx",
    # ── Tuition ───────────────────────────────────────────────────────────────
    "https://www.wcupa.edu/hr/tuition-waiver.aspx",
    "https://www.wcupa.edu/hr/tuition-waiver-information.aspx",
    # ── Payroll ───────────────────────────────────────────────────────────────
    "https://www.wcupa.edu/_information/AFA/fbs/payroll.aspx",
    # ── Parking ───────────────────────────────────────────────────────────────
    "https://www.wcupa.edu/dps/parkingservices/parkingPermits.aspx",
    "https://www.wcupa.edu/dps/parkingservices/employeeRegulations.aspx",
    "https://www.wcupa.edu/dps/parkingservices/faqs.aspx",
    # ── Holidays / Calendar ───────────────────────────────────────────────────
    "https://www.wcupa.edu/registrar/calendar/",
]

OUT_OF_SCOPE_REPLY = "I can not answer that question"

# ─── Qdrant Config ────────────────────────────────────────────────────────────
QDRANT_HOST       = os.getenv("QDRANT_HOST", "qdrant")   # Docker service name
QDRANT_PORT       = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_COLLECTION = "rammy_hr"
EMBED_MODEL       = "all-MiniLM-L6-v2"
QDRANT_TOP_K      = 5   # number of chunks to retrieve per query

PII_WARNING_REPLY = (
    "For your privacy, please do not include personal information in chat. "
    "Please remove names, addresses, emails, phone numbers, ID numbers, or any "
    "government or banking information, then ask again."
)

META_REPLY = (
    "I'm designed to answer HR-related questions for West Chester University employees. "
    "I can help with topics like benefits, retirement plans, payroll, parking permits, "
    "FMLA, employee relations, I-9 documentation, and the Employee Self-Service portal. "
    "If your question falls outside these areas, I may not have the information available."
)

IDENTITY_REPLY = (
    "I'm Rammy, the West Chester University mascot and your HR chatbot. "
    "I'm here to help with HR-related questions."
)

# ─── Small Talk ───────────────────────────────────────────────────────────────

_GREETING_RE    = re.compile(r"^\s*(hi|hello|hey|good\s+morning|good\s+afternoon|good\s+evening)\b", re.IGNORECASE)
_HOW_ARE_YOU_RE = re.compile(r"^\s*(how\s+are\s+you|hru|how's\s+it\s+going)\b", re.IGNORECASE)
_GOODBYE_RE     = re.compile(r"^\s*(bye|goodbye|see\s+ya|later|take\s+care)\b", re.IGNORECASE)

# Short affirmative/continuation replies that need context from history
_AFFIRMATIVE_RE = re.compile(
    r"^\s*(yes|yeah|yep|yup|sure|ok|okay|please|yes please|yes,?\s*please"
    r"|go ahead|tell me more|more detail|more info|that one"
    r"|sounds good|absolutely|definitely|of course|please do"
    r"|no|nope|no thanks|not right now|that.?s all|never mind|i.?m good)\s*[.!]?\s*$",
    re.IGNORECASE,
)
_WHO_ARE_YOU_RE = re.compile(
    r"^\s*(who are you|what are you|who is rammy|what is rammy"
    r"|what model are you|what ai are you|are you (an? )?ai"
    r"|what (version|type) (of )?(ai|model|bot|assistant) are you"
    r"|who made you|who built you|what (powers|drives) you)\??\s*$",
    re.IGNORECASE,
)
_META_RE = re.compile(
    r"(why (can.?t|won.?t|don.?t) you (answer|help)|"
    r"why (is that|are you) out of scope|"
    r"what (can|do) you (answer|help with|know)|"
    r"what (are your|are the) limit|"
    r"what (topics|questions) (do you|can you)|"
    r"why did you say that|what do you mean)",
    re.IGNORECASE,
)


def small_talk_kind(text: str) -> Optional[str]:
    t = text.strip()
    if _GREETING_RE.search(t):    return "greeting"
    if _HOW_ARE_YOU_RE.search(t): return "how_are_you"
    if _GOODBYE_RE.search(t):     return "goodbye"
    if _WHO_ARE_YOU_RE.search(t): return "identity"
    if _META_RE.search(t):        return "meta"
    if _AFFIRMATIVE_RE.match(t):  return "affirmative"
    return None


# ─── PII Detection ────────────────────────────────────────────────────────────

EMAIL_RE          = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE          = re.compile(r"\b(?:\+?1[\s\-.]?)?(?:\(?\d{3}\)?[\s\-.]?)\d{3}[\s\-.]?\d{4}\b")
SSN_RE            = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
STREET_ADDRESS_RE = re.compile(
    r"\b\d{1,6}\s+[A-Za-z0-9.\- ]+\s+"
    r"(street|st|avenue|ave|road|rd|lane|ln|drive|dr|court|ct|boulevard|blvd|way|place|pl)\b",
    re.IGNORECASE,
)
NAME_INTRO_RE = re.compile(r"\b(my name is|this is)\s+[A-Za-z]+(?:\s+[A-Za-z]+){0,2}\b", re.IGNORECASE)
LONG_ID_RE    = re.compile(r"\b\d{6,}\b")
BANK_CARD_RE  = re.compile(r"\b(?:\d[ -]*?){13,16}\b")


def contains_pii(text: str) -> bool:
    if not text or not text.strip():
        return False
    return any(p.search(text) for p in [
        EMAIL_RE, PHONE_RE, SSN_RE, STREET_ADDRESS_RE,
        BANK_CARD_RE, NAME_INTRO_RE, LONG_ID_RE,
    ])


# ─── Text Utilities ───────────────────────────────────────────────────────────

def normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "header", "footer", "nav"]):
        tag.decompose()
    text = normalize_text(soup.get_text("\n"))
    return text[:150_000]  # hard cap


# ─── Source Fetching ──────────────────────────────────────────────────────────

def fetch_sources() -> Dict[str, str]:
    headers = {"User-Agent": "RammyHRBot/2.0"}
    pages: Dict[str, str] = {}
    for url in ALLOWED_URLS:
        try:
            r = requests.get(url, headers=headers, timeout=20)
            r.raise_for_status()
            pages[url] = html_to_text(r.text)
        except Exception as e:
            pages[url] = f"FETCH ERROR: {e}"
    return pages


# ─── Chunking ─────────────────────────────────────────────────────────────────

def split_into_chunks(text: str, url: str, max_len: int = 700) -> List[Dict[str, str]]:
    chunks: List[Dict[str, str]] = []
    raw_parts = re.split(r"(?<=[\.\?\!])\s+|(?<=:)\s+", text)
    current: List[str] = []
    current_len = 0

    for part in raw_parts:
        part = part.strip()
        if not part:
            continue
        if current_len + len(part) > max_len and current:
            chunk_text = " ".join(current).strip()
            if len(chunk_text) > 40:
                chunks.append({"url": url, "text": chunk_text})
            current = [part]
            current_len = len(part)
        else:
            current.append(part)
            current_len += len(part)

    if current:
        chunk_text = " ".join(current).strip()
        if len(chunk_text) > 40:
            chunks.append({"url": url, "text": chunk_text})

    return chunks


def build_chunks(pages: Dict[str, str]) -> List[Dict[str, str]]:
    all_chunks: List[Dict[str, str]] = []
    for url in ALLOWED_URLS:
        page_text = pages.get(url, "")
        if page_text.startswith("FETCH ERROR"):
            continue
        all_chunks.extend(split_into_chunks(page_text, url))
    return all_chunks


# ─── Qdrant Semantic Retrieval ───────────────────────────────────────────────
# Replaces the previous keyword-scoring approach.
# build_context() API is unchanged — the rest of the file is unaffected.

def build_context(question: str, chunks: object = None) -> str:
    """
    Queries Qdrant for the top-K semantically similar chunks, then
    formats them into the same context string the prompts already expect.
    The `chunks` parameter is accepted but ignored (kept for call-site compat).
    """
    global _qdrant_client, _embed_model

    if _qdrant_client is None or _embed_model is None:
        print("[retrieval] Qdrant client or embed model not initialised — falling back to empty context.")
        return ""

    try:
        query_vector = _embed_model.encode(question).tolist()
        response = _qdrant_client.query_points(
            collection_name=QDRANT_COLLECTION,
            query=query_vector,
            limit=QDRANT_TOP_K,
            with_payload=True,
        )
        results = response.points
    except Exception as e:
        print(f"[retrieval] Qdrant search error: {e}")
        return ""

    if not results:
        return ""

    selected = [
        {"url": r.payload.get("url", ""), "text": r.payload.get("text", "")}
        for r in results
        if r.payload.get("text")
    ]

    if not selected:
        return ""

    seen_urls: List[str] = []
    for c in selected:
        if c["url"] and c["url"] not in seen_urls:
            seen_urls.append(c["url"])

    parts = [f"Source {i}: {c['url']}\n{c['text']}" for i, c in enumerate(selected, 1)]
    source_list = "\n".join(f"- {url}" for url in seen_urls)
    return "\n\n".join(parts) + f"\n\nAvailable source URLs:\n{source_list}"


# ─── Prompts ──────────────────────────────────────────────────────────────────

def build_hr_instructions(context: str) -> str:
    return f"""
You are Rammy, the West Chester University mascot and HR assistant. You are warm, approachable, and conversational — like a knowledgeable colleague, not a policy manual.

Rules:
- Only answer HR-related questions using the context provided below.
- Respond naturally in 1-3 sentences. Be concise but friendly.
- ALWAYS end your response with a relevant HTML anchor link using the exact URLs
  listed under "Available source URLs" in the context. Use natural active anchor text.
  Format links exactly like this — no markdown, no raw URLs:
  <a href="https://example.com">Learn more about retirement plans here</a>
  or vary naturally:
  <a href="https://example.com">Visit the WCU Parking page for full details</a>
  <a href="https://example.com">Check out the PASSHE benefits page</a>
- Only use URLs that appear in the "Available source URLs" list — never invent URLs.
- If the answer is simply not in the context, respond with exactly the word: OUTOFSCOPE
- If the question is not HR-related, respond with exactly the word: OUTOFSCOPE
- Treat similar wording as the same intent (e.g. "change address" = "update address").
- Do not show raw URLs. Only use HTML anchor tags for links.
- Do not use markdown formatting, headers, or bullet points.
- Do not make up information not found in the context.

CONVERSATIONAL FOLLOW-UP RULES (very important):
- After answering, ALWAYS ask one natural follow-up question to continue the conversation helpfully.
- Place the follow-up question on its own line at the end, after the anchor link.
- If the topic is broad or has distinct sub-topics (e.g. retirement plans, benefits, parking), offer 2-3 specific options using this exact format on its own line:
  [OPTIONS: Option A label | Option B label | Option C label]
  Example: [OPTIONS: SERS pension plan | ARP (defined contribution) | Voluntary 403(b)/457 plans]
- If the topic is narrow and a simple yes/no or continuation makes sense, end with a short question like:
  "Would you like me to walk you through the steps?"
  "Does that answer your question, or would you like more detail on a specific part?"
  "Are you a faculty/staff member or a student employee? That may affect the details."
- Keep the follow-up question short (1 sentence max). Do not repeat information already given.
- Do NOT add a follow-up if the user's message is a simple yes/no answer or a single-word reply.

Context:
{context}
""".strip()


def build_out_of_scope_prompt(question: str) -> str:
    return f"""
You are Rammy, the West Chester University mascot — friendly, casual, and upbeat.

The user asked: "{question}"

This question is outside your knowledge base. You can only help with WCU HR topics:
benefits, retirement plans (403b, 457, ARP, SERS), payroll, parking permits,
FMLA and leave, workers compensation, tuition waiver, I-9 documentation,
employee relations, professional development, and the Employee Self-Service portal.

Write a short, friendly 1-2 sentence decline in Rammy's voice. Be warm and helpful —
suggest they contact HR directly at HRS@wcupa.edu or 610-436-2800 if it seems relevant.
Do not use bullet points or markdown. Never say "I cannot answer that question" verbatim.
Vary your response naturally — don't use the same phrasing every time.
""".strip()

def build_smalltalk_prompt(user_text: str) -> str:
    return f"""
You are Rammy, the West Chester University Ram mascot.

The user said: {user_text}

Respond in 1-2 sentences. Be warm and friendly but straightforward.
Do not use animal puns, rhymes, or wordplay.
Do not reference cats, paws, or any animal other than rams.
You are a ram — stay on brand.
Do not answer non-HR questions beyond simple small talk.

After your response, ask one short, natural question to invite them to share what HR topic they need help with.
For greetings, offer 2-4 common topic options using this exact format on its own line:
[OPTIONS: Benefits & insurance | Retirement plans | Payroll & pay stubs | Leave & FMLA | Parking permits | Tuition waiver]
""".strip()

# ─── Model Call ───────────────────────────────────────────────────────────────

def ask_model(
    client: OpenAI,
    question: str,
    chunks: List[Dict[str, str]],
    history: List[Dict[str, str]],
) -> str:
    """Return Rammy's reply string. All routing logic lives here."""

    if contains_pii(question):
        return PII_WARNING_REPLY

    kind = small_talk_kind(question)

    if kind == "identity":
        return IDENTITY_REPLY

    if kind == "meta":
        return META_REPLY

    if kind == "affirmative":
        # Re-surface the last assistant turn as the search query so the model
        # has topic context rather than searching cold on "yes please".
        last_assistant = next(
            (m["content"] for m in reversed(history) if m.get("role") == "assistant"),
            None,
        )
        if last_assistant:
            # Use the last assistant reply as the retrieval query
            context = build_context(last_assistant[:300], chunks)
            if context:
                system_prompt = build_hr_instructions(context)
                trimmed_history = history[-4:] if history else []
                messages = (
                    [{"role": "system", "content": system_prompt}]
                    + trimmed_history
                    + [{"role": "user", "content": question}]
                )
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=messages,
                    max_tokens=300,
                    temperature=0.3,
                )
                answer = response.choices[0].message.content.strip()
                if answer and "OUTOFSCOPE" not in answer:
                    return answer
        # No history or no context found — treat as small talk
        kind = "greeting"

    if kind:
        system_prompt = build_smalltalk_prompt(question)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": question},
        ]
    else:
        context = build_context(question, chunks)
        if not context:
            # Generate a friendly, varied decline via GPT
            oos_prompt = build_out_of_scope_prompt(question)
            oos_response = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": oos_prompt}],
                max_tokens=100,
                temperature=0.8,  # Higher temp for natural variation
            )
            return oos_response.choices[0].message.content.strip() or OUT_OF_SCOPE_REPLY

        system_prompt = build_hr_instructions(context)
        trimmed_history = history[-4:] if history else []
        messages = (
            [{"role": "system", "content": system_prompt}]
            + trimmed_history
            + [{"role": "user", "content": question}]
        )

    # ── FIX: use chat.completions.create (not client.responses.create) ──
    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        max_tokens=300,
        temperature=0.3,   # Lower temp = more consistent, factual replies
    )

    answer = response.choices[0].message.content.strip()

    # If GPT returned the out-of-scope sentinel, generate a friendly decline
    if not answer or "OUTOFSCOPE" in answer:
        oos_prompt = build_out_of_scope_prompt(question)
        oos_response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": oos_prompt}],
            max_tokens=100,
            temperature=0.8,
        )
        return oos_response.choices[0].message.content.strip() or OUT_OF_SCOPE_REPLY

    return answer


# ─── Flask App ────────────────────────────────────────────────────────────────

app = Flask(__name__)

# Module-level state — initialised once on startup
_chunks: List[Dict[str, str]] = []   # kept for API compat; no longer used for retrieval
_cache_lock = threading.Lock()
_client: Optional[OpenAI] = None
_qdrant_client: Optional[QdrantClient] = None
_embed_model = None   # SentenceTransformer instance
_startup_done = False


@app.before_request
def _ensure_startup():
    """Runs once on the first request — handles flask run / gunicorn startup."""
    global _startup_done, _client
    if _startup_done:
        return
    _startup_done = True
    if OPENAI_API_KEY:
        _client = _init_client()
    else:
        print("[startup] WARNING: OPENAI_API_KEY not set.")
    _init_qdrant()


def _init_qdrant() -> None:
    """Connect to Qdrant and load the embedding model. Safe to call multiple times."""
    global _qdrant_client, _embed_model
    try:
        _qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        # Verify the collection exists
        try:
            info = _qdrant_client.get_collection(QDRANT_COLLECTION)
            count = getattr(info, 'points_count', None) or getattr(getattr(info, 'result', info), 'points_count', '?')
            print(f"[qdrant] Connected. Collection '{QDRANT_COLLECTION}' has {count} points.")
        except Exception:
            print(f"[qdrant] WARNING: collection '{QDRANT_COLLECTION}' not found. "
                  f"Run qdrant_setup.py first.")
    except Exception as e:
        print(f"[qdrant] Connection failed: {e}")
        _qdrant_client = None

    try:
        print(f"[qdrant] Loading embedding model '{EMBED_MODEL}'...")
        _embed_model = SentenceTransformer(EMBED_MODEL)
        print(f"[qdrant] Embedding model ready.")
    except Exception as e:
        print(f"[qdrant] Failed to load embedding model: {e}")
        _embed_model = None


def _init_client() -> OpenAI:
    kwargs = {"api_key": OPENAI_API_KEY}
    if OPENAI_ORG_ID:
        kwargs["organization"] = OPENAI_ORG_ID
    if OPENAI_PROJECT_ID:
        kwargs["project"] = OPENAI_PROJECT_ID
    return OpenAI(**kwargs)


def _load_sources() -> None:
    """Re-connects to Qdrant (e.g. after running qdrant_setup.py externally).
    Does NOT reload the embedding model if already loaded — avoids triple-init."""
    global _qdrant_client
    try:
        _qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        try:
            info = _qdrant_client.get_collection(QDRANT_COLLECTION)
            count = getattr(info, 'points_count', None) or getattr(getattr(info, 'result', info), 'points_count', '?')
            print(f"[refresh] Reconnected. Collection has {count} points.")
        except Exception:
            print(f"[refresh] WARNING: collection '{QDRANT_COLLECTION}' still not found. "
                  f"Run qdrant_setup.py first.")
    except Exception as e:
        print(f"[refresh] Qdrant reconnect failed: {e}")
        _qdrant_client = None
    print("[refresh] Qdrant connection refreshed.")


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    history = data.get("history") or []

    if not message:
        return jsonify({"error": "message is required"}), 400

    with _cache_lock:
        current_chunks = list(_chunks)

    try:
        reply = ask_model(_client, message, current_chunks, history)
    except Exception as e:
        print(f"[/chat] Error: {e}")
        return jsonify({"error": "Internal error — please try again."}), 500

    return jsonify({"reply": reply})


@app.route("/refresh", methods=["POST"])
def refresh():
    threading.Thread(target=_load_sources, daemon=True).start()
    return jsonify({"message": "Source refresh started in background."})


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not OPENAI_API_KEY:
        raise RuntimeError("Set OPENAI_API_KEY environment variable before starting.")

    _client = _init_client()
    _init_qdrant()       # Connect to Qdrant and load embedding model
    _startup_done = True # Prevent before_request from running init a second time

    app.run(host="0.0.0.0", port=5001, debug=False)
