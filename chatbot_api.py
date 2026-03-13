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
    "https://www.wcupa.edu/hr/benefits/workersCompAPSCUF.aspx",
    "https://www.wcupa.edu/hr/benefits/workersCompAFSCME.aspx",
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


# ─── Retrieval ────────────────────────────────────────────────────────────────

# ── Extend this table to boost new topic keywords without touching scoring logic ──
PHRASE_BOOSTS: List[Tuple[str, float]] = [
    # Address / ESS
    ("update address",        4.0),
    ("address",               2.0),
    ("email",                 2.0),
    ("employee self service", 3.0),
    ("ess",                   3.0),
    ("fiori",                 3.0),
    # Loans / forgiveness
    ("forgiveness form",      3.0),
    ("loan forgiveness",      3.0),
    # Employee groups / relations
    ("employee group",        3.0),
    # Leave
    ("fmla",                  3.0),
    ("time off",              2.5),
    ("leave",                 2.0),
    ("sick leave",            2.5),
    # Retirement
    ("retirement",            3.0),
    ("401k",                  3.5),
    ("403b",                  3.5),
    ("457",                   3.0),
    ("arp",                   3.0),
    ("sers",                  3.0),
    ("voluntary retirement",  3.5),
    ("deferred compensation", 3.0),
    ("fidelity",              2.5),
    ("tiaa",                  2.5),
    ("tsa",                   2.5),
    # Parking
    ("parking",               3.0),
    ("parking permit",        4.0),
    ("parking pass",          4.0),
    ("garage pass",           3.5),
    ("e permit",              3.5),
    # Payroll
    ("payroll",               3.0),
    ("direct deposit",        3.5),
    ("pay statement",         3.0),
    ("w-4",                   3.0),
    ("w-2",                   3.0),
    # Benefits
    ("benefits",              2.0),
    ("health insurance",      2.5),
    ("dental",                2.0),
    ("vision",                2.0),
    # Workers comp
    ("workers comp",          4.0),
    ("workers compensation",  4.0),
    ("workplace injury",      4.0),
    ("work injury",           4.0),
    ("incident report",       3.5),
    ("panel physician",       3.5),
    # Tuition
    ("tuition waiver",        4.0),
    ("tuition reimbursement", 4.0),
    ("tuition benefit",       3.5),
    ("tuition",               2.5),
    # Holidays / calendar
    ("holiday",               3.0),
    ("campus closure",        3.5),
    ("academic calendar",     3.0),
    # Professional development
    ("professional development", 3.0),
    ("linkedin learning",     3.0),
    ("training",              2.0),
    # I-9
    ("i-9",                   3.0),
    # Onboarding
    ("new hire",              2.5),
    ("onboarding",            2.5),
]

_QUERY_REPLACEMENTS = [
    (r"\bchange\b",              "update"),
    (r"\bmodify\b",              "update"),
    (r"\bedit\b",                "update"),
    (r"\bemail address\b",       "email"),
    (r"\bhome address\b",        "address"),
    (r"\b401k\b",                "retirement voluntary"),
    (r"\bparking pass\b",        "parking permit"),
    (r"\bhurt at work\b",        "workers compensation injury"),
    (r"\binjured at work\b",     "workers compensation injury"),
    (r"\bwork injury\b",         "workers compensation"),
    (r"\bworkplace accident\b",  "workers compensation injury"),
    (r"\baccident at work\b",    "workers compensation injury"),
    (r"\breport an? injury\b",   "workers compensation"),
    (r"\btuition help\b",        "tuition waiver reimbursement"),
    (r"\btake classes\b",        "tuition waiver"),
    (r"\bgo back to school\b",   "tuition waiver"),
    (r"\bday off\b",             "holiday campus closure"),
    (r"\bdays off\b",            "holiday campus closure"),
    (r"\bschool closed\b",       "campus closure holiday"),
    (r"\bsick\b",                "sick leave fmla"),
    (r"\bvacation\b",            "leave time off"),
    (r"\bpay stub\b",            "pay statement payroll"),
    (r"\bpaycheck\b",            "payroll pay statement"),
    (r"\bhealth (insurance|care|plan|coverage)\b", "benefits health insurance"),
    (r"\bdoctor\b",              "health insurance benefits"),
    (r"\bam i able to\b",        ""),
    (r"\bcan i\b",               ""),
    (r"\bhow do i\b",            ""),
    (r"\bhow can i\b",           ""),
    (r"\bwhere do i\b",          ""),
    (r"\bwhat is\b",             ""),
    (r"\bplease\b",              ""),
]

# Pre-compile for speed
_COMPILED_REPLACEMENTS = [(re.compile(p), r) for p, r in _QUERY_REPLACEMENTS]


def normalize_question_for_search(q: str) -> str:
    q = q.lower().strip()
    for pattern, repl in _COMPILED_REPLACEMENTS:
        q = pattern.sub(repl, q)
    q = re.sub(r"[^a-z0-9\s]", " ", q)
    return normalize_text(q)


def tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def score_chunk(question: str, chunk: str) -> float:
    q_norm = normalize_question_for_search(question)
    c_norm = normalize_question_for_search(chunk)
    q_tokens = tokenize(q_norm)
    c_tokens = set(tokenize(c_norm))

    if not q_tokens:
        return 0.0

    score = sum(1.0 for t in q_tokens if t in c_tokens)

    for phrase, value in PHRASE_BOOSTS:
        if phrase in q_norm and phrase in c_norm:
            score += value

    return score


def retrieve_relevant_chunks(
    question: str, chunks: List[Dict[str, str]], top_k: int = 5
) -> List[Dict[str, str]]:
    scored = [(score_chunk(question, c["text"]), c) for c in chunks]
    # Lower threshold from >0 to >=1.5 to filter noise,
    # but keep anything with a phrase boost hit (those are always >= 2.0)
    scored = [(s, c) for s, c in scored if s >= 1.5]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:top_k]]


def build_context(question: str, chunks: List[Dict[str, str]]) -> str:
    selected = retrieve_relevant_chunks(question, chunks)
    if not selected:
        return ""
    parts = [f"Source {i}: {c['url']}\n{c['text']}" for i, c in enumerate(selected, 1)]
    return "\n\n".join(parts)


# ─── Prompts ──────────────────────────────────────────────────────────────────

def build_hr_instructions(context: str) -> str:
    return f"""
You are Rammy, the West Chester University mascot and HR assistant.

Rules:
- Only answer HR-related questions using the context provided below.
- If the context clearly answers the question, respond naturally in 1-3 sentences.
- If the context only partially answers the question, answer what you can and include
  a relevant source link using natural active language — for example:
  "You can find the full details at [WCU Parking Permits](https://www.wcupa.edu/...)" or
  "Learn more here: [PASSHE Retirement Plans](https://www.passhe.edu/...)".
- Only include a link when it genuinely adds value — don't force one into every reply.
- If the answer is simply not in the context, respond with exactly the word: OUTOFSCOPE
- If the question is not HR-related, respond with exactly the word: OUTOFSCOPE
- Treat similar wording as the same intent (e.g. "change address" = "update address").
- Do not mention the context or sources by name.
- Do not use markdown headers or bullet points.
- Do not make up information not found in the context.

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
You are Rammy, the West Chester University mascot.

The user said: {user_text}

Respond naturally like a friendly mascot. Keep it to 1-2 sentences.
You may answer questions about who or what you are.
Do not answer non-HR questions beyond simple small talk.
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

# Module-level cache — loaded once on startup, refreshed via /refresh
_chunks: List[Dict[str, str]] = []
_cache_lock = threading.Lock()
_client: Optional[OpenAI] = None


def _init_client() -> OpenAI:
    kwargs = {"api_key": OPENAI_API_KEY}
    if OPENAI_ORG_ID:
        kwargs["organization"] = OPENAI_ORG_ID
    if OPENAI_PROJECT_ID:
        kwargs["project"] = OPENAI_PROJECT_ID
    return OpenAI(**kwargs)


def _load_sources() -> None:
    global _chunks
    pages = fetch_sources()
    new_chunks = build_chunks(pages)
    with _cache_lock:
        _chunks = new_chunks
    print(f"[startup] Loaded {len(_chunks)} chunks from {len(ALLOWED_URLS)} sources.")


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
    _load_sources()                     # Warm cache on startup

    app.run(host="0.0.0.0", port=5001, debug=False)
