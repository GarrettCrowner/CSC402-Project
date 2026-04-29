"""
Rammy HR Chatbot -- Python Flask Backend (Optimized)

Changes vs original chatbot.py:
  - Wrapped in Flask so Node.js (or any client) can call it over HTTP.
  - Sources are fetched ONCE on startup and cached; /refresh endpoint reloads them.
  - Removed CLI loop (now an API service).
  - Fixed OpenAI call: client.responses.create -> client.chat.completions.create
    (responses.create is not a valid OpenAI Python SDK method).
  - PII check and small-talk logic are unchanged.
  - Chunk scoring is unchanged; phrase-boost table is easier to extend.
  - Performance monitor removed (not meaningful in a server context;
    use a proper APM tool like Datadog or Sentry in production).
  - Added /health endpoint for Node.js to ping.
"""

import os
import re
import json
import threading
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, request, Response, stream_with_context
from openai import OpenAI
from urllib.parse import quote
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
from difflib import get_close_matches


GLOBAL_HISTORY = []
MAX_HISTORY = 20

# --- Guided Eligibility Flow State --------------------------------------------

FLOW_PROGRESS = {
    "intent": None,
    "step": None,
    "group": None,
    "type": None,
    "hours": None
}

INTENT_PHRASES = {
    "health_insurance": [
        "health insurance",
        "insurance",
        "medical coverage",
        "health benefits",
        "benefits",
        "healthcare"
    ],
    "retirement": [
        "retirement",
        "retire",
        "pension",
        "403b",
        "403 b",
        "457",
        "457 plan",
        "retirement contribution",
        "sers",
        "psers",
        "arp"
    ],
    "leave": [
        "leave",
        "leave time",
        "time off",
        "vacation",
        "vacation time",
        "sick time",
        "sick leave",
        "leave accrual",
        "accrual",
        "time earned"
    ],
    "fmla": [
        "fmla",
        "fmla leave",
        "family medical leave",
        "family medical leave act"
    ],
    "fsa": [
        "fsa",
        "flexible spending account",
        "healthcare fsa",
        "dependent care fsa",
        "daycare fsa"
    ],
    "tuition_waiver": [
        "tuition waiver",
        "tuition benefit",
        "free classes",
        "tuition reimbursement"
    ]
}

# --- Config -------------------------------------------------------------------

OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY", "")
OPENAI_ORG_ID    = os.getenv("OPENAI_ORG_ID", "")
OPENAI_PROJECT_ID = os.getenv("OPENAI_PROJECT_ID", "")

MODEL = "gpt-4.1-mini"

ALLOWED_URLS = [
    # -- Core HR ---------------------------------------------
    "https://www.wcupa.edu/hr/faqs.aspx",
    "https://www.wcupa.edu/hr/employee-labor-relations.aspx",
    "https://www.wcupa.edu/hr/student-employment.aspx",
    "https://www.wcupa.edu/hr/professional-development.aspx",
    "https://www.wcupa.edu/hr/why-work-at-wcu.aspx",

    # -- Employment / Applications ---------------------------
    "https://www.schooljobs.com/careers/wcupa",

    # -- I-9 / Verification ----------------------------------
    "https://www.uscis.gov/i-9-central/form-i-9-acceptable-documents",

    # -- Leave -----------------------------------------------
    "https://www.wcupa.edu/hr/FMLA.aspx",
    "https://www.wcupa.edu/hr/leave.aspx",
    "https://www.passhe.edu/hr/benefits/life-events/index.html",
    "https://www.passhe.edu/hr/benefits/leave/index.html",
    "https://www.passhe.edu/hr/benefits/leave/personal-leave.html",
    "https://www.passhe.edu/hr/benefits/leave/sick-leave.html",
    "https://www.passhe.edu/hr/benefits/leave/vacation.html",

    # -- Benefits --------------------------------------------
    "https://www.wcupa.edu/hr/employee-benefits-vs-benefits-by-employee-group.aspx",
    "https://www.passhe.edu/hr/benefits/index.html",
    "https://www.passhe.edu/hr/benefits/healthcare/index.html",
    "https://www.passhe.edu/hr/benefits/healthcare/pebtf.html",
    "https://www.passhe.edu/hr/benefits/healthcare/benefits-summary.html",
    "https://www.passhe.edu/hr/benefits/insurance/index.html",
    "https://www.passhe.edu/hr/benefits/insurance/ltd.html",
    "https://www.passhe.edu/hr/benefits/fsa.html",
    "https://www.passhe.edu/hr/benefits/seap.html",
    "https://www.passhe.edu/hr/benefits/pslf.html",
    "https://www.passhe.edu/hr/benefits/beneficiaries.html",

    # -- FSA / Docs ------------------------------------------
    "https://www.passhe.edu/hr/benefits/documents/fsa/2026-fsa-handbook.pdf",

    # -- Retirement ------------------------------------------
    "https://www.passhe.edu/hr/benefits/retirement/index.html",
    "https://www.passhe.edu/hr/benefits/retirement/voluntary-retirement-plans.html",
    "https://www.passhe.edu/hr/benefits/retirement/tsa.html",
    "https://www.passhe.edu/hr/benefits/retirement/deferred-compensation.html",
    "https://www.passhe.edu/hr/benefits/retirement/arp.html",
    "https://www.passhe.edu/hr/benefits/retirement/sers.html",

    # -- Retirees --------------------------------------------
    "https://www.passhe.edu/hr/benefits/retirees/index.html",
    "https://www.passhe.edu/hr/benefits/retirees/prospective/index.html",

    # -- External Retirement Providers -----------------------
    "https://www.tiaa.org/public/tcm/passhe/home",
    "https://retirementatwork.org/wcupa/",
    "https://sers.pa.gov/members/",
    "https://www.psers.pa.gov/Members/Pages/default.aspx",
    "https://www.empower.com/public/retirement",
    "https://nb.fidelity.com/public/nb/default/home",
    "https://www.fidelity.com",
    "https://www.tiaa.org",

    # -- Tuition ---------------------------------------------
    "https://www.wcupa.edu/hr/tuition-waiver.aspx",
    "https://www.wcupa.edu/hr/tuition-waiver-information.aspx",

    # -- Payroll / Schedule ----------------------------------
    "https://www.wcupa.edu/_information/AFA/fbs/payroll.aspx",
    "https://www.passhe.edu/hr/ooc/paydays-holidays.html",

    # -- Portal / Tools --------------------------------------
    "https://portal.passhe.edu/ijr/portal",

    # -- Healthcare Providers --------------------------------
    "https://www.highmark.com/member/member-guide",
    "https://www.aetna.com/",

    # -- Employee Assistance / SEAP --------------------------
    "https://www.liveandworkwell.com",

    # -- Parking ---------------------------------------------
    "https://www.wcupa.edu/dps/parkingservices/parkingPermits.aspx",
    "https://www.wcupa.edu/dps/parkingservices/employeeRegulations.aspx",
    "https://www.wcupa.edu/dps/parkingservices/faqs.aspx",

    # -- Calendar --------------------------------------------
    "https://www.wcupa.edu/registrar/calendar/"
]

# --- Analytics Config --------------------------------------------------------
ANALYTICS_LOG = os.getenv("ANALYTICS_LOG", "/app/analytics.jsonl")
_analytics_lock = threading.Lock()

TOPIC_KEYWORDS: dict = {
    "greeting":      ["hello","hi","hey","good morning","good afternoon","good evening","what can you do","help me","get started"],
    "benefits":      ["benefit","health","dental","vision","insurance","coverage","medical"],
    "retirement":    ["retire","403b","457","arp","sers","psers","tiaa","pension","deferred","tsa"],
    "payroll":       ["payroll","pay","salary","direct deposit","w-2","w-4","pay stub","paycheck"],
    "leave":         ["fmla","leave","sick","vacation","time off","absence","family"],
    "parking":       ["park","permit","garage","e-permit","pass"],
    "tuition":       ["tuition","waiver","reimburs","class","school","education"],
    "workers_comp":  ["workers comp","injury","hurt","incident","accident","panel physician"],
    "employment":    ["hire","job","opening","position","employ","onboard","i-9"],
    "professional_development": ["training","linkedin","learning","development","workshop","fast"],
    "i9":            ["i-9","i9","verification","document","eligible"],
    "general_hr":    ["hr","human resources","contact","email","phone"],
}

def classify_topic(question: str) -> str:
    q = question.lower()
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(kw in q for kw in keywords):
            return topic
    return "other"

def detect_source_type(reply: str) -> str:
    """Detect whether the answer was sourced from a PDF or a web page."""
    r = reply.lower()
    if "pdf:" in r or "/api/pdf/" in r:
        return "pdf"
    if "http" in r:
        return "web"
    return "unknown"

def log_interaction(question: str, reply: str, is_out_of_scope: bool, tokens: dict = None) -> None:
    """Append one JSONL record to the analytics log file."""
    record = {
        "ts":             datetime.now(timezone.utc).isoformat(),
        "question":       question,
        "topic":          classify_topic(question),
        "out_of_scope":   is_out_of_scope,
        "source_type":    detect_source_type(reply),
        "reply_length":   len(reply),
        "tokens_prompt":      (tokens or {}).get("prompt", 0),
        "tokens_completion":  (tokens or {}).get("completion", 0),
        "tokens_total":       (tokens or {}).get("total", 0),
    }
    try:
        with _analytics_lock:
            with open(ANALYTICS_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
    except Exception as e:
        print(f"[analytics] Log write failed: {e}")


OUT_OF_SCOPE_REPLY = "I can not answer that question"

# --- Qdrant Config ------------------------------------------------------------
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

# --- Small Talk ---------------------------------------------------------------

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


# --- PII Detection ------------------------------------------------------------

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

# Known public WCU HR contact details -- never flag these as PII.
_WCU_WHITELIST = [
    "HRS@wcupa.edu",
    "hrs@wcupa.edu",
    "610-436-2800",
    "6104362800",
]

def contains_pii(text: str) -> bool:
    if not text or not text.strip():
        return False
    # Scrub known public WCU HR contacts before checking so Rammy's own
    # replies (bundled into chip `regarding:` context) don't trigger false positives.
    scrubbed = text
    for safe in _WCU_WHITELIST:
        scrubbed = scrubbed.replace(safe, "")
    return any(p.search(scrubbed) for p in [
        EMAIL_RE, PHONE_RE, SSN_RE, STREET_ADDRESS_RE,
        BANK_CARD_RE, NAME_INTRO_RE, LONG_ID_RE,
    ])


# --- Text Utilities -----------------------------------------------------------

def normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript", "svg", "header", "footer", "nav"]):
        tag.decompose()

    parts = []

    for tag in soup.find_all(["p", "li", "a"]):
        text = tag.get_text(strip=True)

        if tag.name == "a" and tag.get("href"):
            href = tag["href"]

            if href.startswith("/"):
                href = "https://www.wcupa.edu" + href

            parts.append(f"{text} (Link: {href})")
        else:
            parts.append(text)

    text = normalize_text("\n".join(parts))
    return text[:150_000]


# --- Source Fetching ----------------------------------------------------------

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


# --- Chunking -----------------------------------------------------------------

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


# --- PDF URL Resolution -------------------------------------------------------

# The Node.js server exposes GET /api/pdf/<filename> as a proxy to MinIO.
# This base URL must be reachable from the user's browser.
PDF_PROXY_BASE = os.getenv("PDF_PROXY_BASE", "http://localhost:3000/api/pdf")


def pdf_label_to_url(source_label: str) -> str:
    """
    Converts a Qdrant payload url like 'pdf:employee-handbook.pdf'
    into a browser-accessible download URL via the Node proxy.
    e.g. -> 'http://localhost:3000/api/pdf/employee-handbook.pdf'
    """
    filename = source_label[len("pdf:"):]  # strip the 'pdf:' prefix
    return f"{PDF_PROXY_BASE}/{quote(filename)}"


# --- Qdrant Semantic Retrieval -----------------------------------------------
# Replaces the previous keyword-scoring approach.
# build_context() API is unchanged -- the rest of the file is unaffected.

def build_context(question: str, chunks: object = None) -> str:
    """
    Queries Qdrant for the top-K semantically similar chunks, then
    formats them into the same context string the prompts already expect.
    The `chunks` parameter is accepted but ignored (kept for call-site compat).
    """
    global _qdrant_client, _embed_model

    if _qdrant_client is None or _embed_model is None:
        print("[retrieval] Qdrant client or embed model not initialised -- falling back to empty context.")
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

    selected = []
    for r in results:
        if not r.payload.get("text"):
            continue
        raw_url = r.payload.get("url", "")
        # Resolve pdf: labels -> real browser-accessible URLs via the Node proxy
        resolved_url = pdf_label_to_url(raw_url) if raw_url.startswith("pdf:") else raw_url
        is_pdf = raw_url.startswith("pdf:")
        selected.append({"url": resolved_url, "text": r.payload.get("text", ""), "raw_url": raw_url, "is_pdf": is_pdf})

    if not selected:
        return ""

    # Re-rank: prefer web sources over PDFs when both cover the topic.
    # PDFs win only if there are no web sources in the result set.
    has_web = any(not c["is_pdf"] for c in selected)
    if has_web:
        selected.sort(key=lambda c: (1 if c["is_pdf"] else 0))

    seen_urls: List[str] = []
    for c in selected:
        if c["url"] and c["url"] not in seen_urls:
            seen_urls.append(c["url"])

    parts = [
    f"Source {i}: {c['url']}\nContent:\n{c['text']}"
    for i, c in enumerate(selected, 1)
    ]
    
    source_list = "\n".join(f"- {url}" for url in seen_urls)
    return "\n\n".join(parts) + f"\n\nAvailable source URLs:\n{source_list}"


# --- Link Sanitisation -------------------------------------------------------

def linkify_contacts(text: str) -> str:
    """
    Post-processing safety net: wraps any bare email addresses and phone numbers
    that slipped through as plain text into proper HTML anchor tags.
    Skips text that is already inside an <a> tag.
    """
    if not text:
        return text

    # Regex patterns as variables to avoid quoting issues
    def _email_link(m):
        # Skip if already inside an anchor tag
        addr  = m.group(1)
        start = max(0, m.start() - 30)
        if "mailto:" in text[start:m.start()] or "href=" in text[start:m.start()]:
            return m.group(0)
        return f'<a href="mailto:{addr}">{addr}</a>'

    def _phone_link(m):
        raw    = m.group(1)
        start  = max(0, m.start() - 20)
        if "tel:" in text[start:m.start()] or "href=" in text[start:m.start()]:
            return m.group(0)
        digits = re.sub(r"[^0-9]", "", raw)
        return f'<a href="tel:{digits}">{raw}</a>'

    text = re.sub(
        r'([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})',
        _email_link, text
    )
    text = re.sub(
        r'(\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4})',
        _phone_link, text
    )

    # Wrap bare URLs (www.example.com or https://example.com) not already in an anchor
    def _url_link(m):
        raw   = m.group(1)
        start = max(0, m.start() - 20)
        # Skip if already inside href= or src=
        if "href=" in text[start:m.start()] or "src=" in text[start:m.start()]:
            return m.group(0)
        href = raw if raw.startswith("http") else "https://" + raw
        return f'<a href="{href}" target="_blank" rel="noopener noreferrer">{raw}</a>'

    # Matches https://, http://, and www. URLs
    URL_BARE = re.compile(r'(?<!["\'=])((?:https?://|www\.)[\w./\-?=&#%+@!:,]+)')
    text = URL_BARE.sub(_url_link, text)

    # Matches bare domains like UnitedConcordia.com or retirementatwork.org
    def _bare_domain_link(m):
        raw   = m.group(1)
        start = max(0, m.start() - 20)
        if "href=" in text[start:m.start()] or "://" in text[start:m.start()]:
            return m.group(0)
        return f'<a href="https://{raw}" target="_blank" rel="noopener noreferrer">{raw}</a>'

    BARE_DOMAIN = re.compile(
        r'(?<![\w@/"\'.])'
        r'([A-Za-z0-9][A-Za-z0-9\-]*'
        r'(?:\.[A-Za-z0-9\-]+)*'
        r'\.(?:com|org|edu|gov|net|io|us))'
        r'(?![\w/])'
    )
    text = BARE_DOMAIN.sub(_bare_domain_link, text)
    return text


# --- Prompts ------------------------------------------------------------------

def build_hr_instructions(context: str) -> str:
    # Detect whether context has real web URLs or only internal pdf: labels.
    has_web_url    = "https://" in context
    has_pdf_source = "pdf:" in context

    if has_web_url:
        link_rule = (
            "- ALWAYS end your response with a relevant HTML anchor link using the exact URLs\n"
            "  listed under \'Available source URLs\' in the context. Use natural active anchor text.\n"
            "  Format links exactly like this - no markdown, no raw URLs:\n"
            "  <a href=\"https://example.com\">Learn more about retirement plans here</a>\n"
            "  or vary naturally:\n"
            "  <a href=\"https://example.com\">Visit the WCU Parking page for full details</a>\n"
            "- If the context includes a specific link for an action (e.g., reset password, apply, login), ALWAYS use that direct link instead of a general page link.\n"
            "- If a line contains '(Link: URL)', treat it as a direct actionable link and prioritize it.\n"
            "- Prefer the most specific link available (e.g., 'Reset Password') over general pages like 'FAQs'.\n"
            "- When mentioning external provider websites (e.g. TIAA, Retirement@Work, SERS, PSERS, Empower, Fidelity),\n"
            "  always format them as HTML anchor links using the exact URL from the source list.\n"
            "  Example: <a href=\"https://retirementatwork.org/wcupa/\">Retirement@Work</a>"
        )
    elif has_pdf_source:
        # Extract all pdf: filenames -- filenames may contain spaces so we match
        # up to the end of the line or a comma, not just non-whitespace chars.
        pdf_names = re.findall(r"pdf:([^\n,]+?)(?=\s*(?:,|\n|$))", context)
        pdf_names = [n.strip() for n in pdf_names if n.strip()]
        pdf_link_examples = ""
        if pdf_names:
            name = pdf_names[0]
            encoded = quote(name)
            label = name.replace("_", " ").replace("-", " ")
            if label.lower().endswith(".pdf"):
                label = label[:-4]
            pdf_link_examples = (
                f'  Example: <a href="{PDF_PROXY_BASE}/{encoded}">{label}</a>\n'
            )
        link_rule = (
            "- This answer comes from an internal HR PDF document.\\n"
            "- End your response with a clickable link to the PDF using this EXACT format\\n"
            "  (double quotes around href, full URL including http://localhost:3000):\\n"
            f"{pdf_link_examples}"
            "- Use the COMPLETE filename exactly as it appears after 'pdf:' in the source -- including spaces.\\n"
            "- Do NOT shorten, truncate, or alter the filename in any way.\\n"
            "- Do NOT invent filenames. Only link files whose 'pdf:' label appears in the context."
        )
    else:
        link_rule = (
            "- If a relevant web URL is available in the context, end with an HTML anchor link.\n"
            "- If no URL is available, omit the link entirely - do not invent one."
        )

    return f"""
You are Rammy, the West Chester University mascot and HR assistant. You are warm, approachable, and conversational - like a knowledgeable colleague, not a policy manual.

Rules:
- Only answer HR-related questions using the context provided below.
- If the user sends a short topic phrase (e.g. "Retirement plans", "Benefits & insurance", "Parking permits"), treat it as a request for a brief overview of that topic -- do NOT return OUTOFSCOPE.
- Respond naturally in 1-3 sentences. Be concise but friendly.
{link_rule}
- If the answer is simply not in the context, respond with exactly the word: OUTOFSCOPE
- If the question is not HR-related, respond with exactly the word: OUTOFSCOPE
- Treat similar wording as the same intent (e.g. "change address" = "update address").
- Do not show raw URLs. Only use HTML anchor tags for links.
- Do not use markdown formatting, headers, or bullet points.
- Do not make up information not found in the context.
- If you mention an email address, ALWAYS wrap it as: <a href="mailto:address">address</a>
- If you mention a phone number, ALWAYS wrap it as: <a href="tel:digits">formatted number</a>
  Example: <a href="tel:6104362800">610-436-2800</a>

CONVERSATIONAL FOLLOW-UP RULES (very important):
- After answering, ALWAYS ask one natural follow-up question to continue the conversation helpfully.
- Place the follow-up question on its own line at the end, after the anchor link (or document citation).
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
You are Rammy, the West Chester University mascot -- friendly, casual, and upbeat.

The user asked: "{question}"

This question is outside your knowledge base. You can only help with WCU HR topics:
benefits, retirement plans (403b, 457, ARP, SERS), payroll, parking permits,
FMLA and leave, workers compensation, tuition waiver, I-9 documentation,
employee relations, professional development, and the Employee Self-Service portal.

Write a short, friendly 1-2 sentence decline in Rammy's voice. Be warm and helpful --
suggest they contact HR directly if it seems relevant -- always formatted as HTML links:
<a href="mailto:HRS@wcupa.edu">HRS@wcupa.edu</a> or <a href="tel:6104362800">610-436-2800</a>
Do not show raw email addresses or phone numbers -- always use HTML anchor tags.
Do not use bullet points or markdown. Never say "I cannot answer that question" verbatim.
Vary your response naturally -- don't use the same phrasing every time.
""".strip()

def build_smalltalk_prompt(user_text: str) -> str:
    return f"""
You are Rammy, the West Chester University Ram mascot.

The user said: {user_text}

Respond in 1-2 sentences. Be warm and friendly but straightforward.
Do not use animal puns, rhymes, or wordplay.
Do not reference cats, paws, or any animal other than rams.
You are a ram -- stay on brand.
Do not answer non-HR questions beyond simple small talk.
If you mention the HR email or phone number, always format them as HTML anchor tags:
<a href="mailto:HRS@wcupa.edu">HRS@wcupa.edu</a> and <a href="tel:6104362800">610-436-2800</a>

After your response, ask one short, natural question to invite them to share what HR topic they need help with.
For greetings, offer 2-4 common topic options using this exact format on its own line:
[OPTIONS: Benefits & insurance | Retirement plans | Payroll & pay stubs | Leave & FMLA | Parking permits | Tuition waiver]
""".strip()


# Intent

# --- Guided Flow Helpers -----------------------------------------------------

def normalize_user_input(text: str) -> str:
    text = text.lower()
    text = re.sub(r'(.)\1{2,}', r'\1', text)
    text = re.sub(r'[^a-z0-9\s\-/]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def strip_regarding_context(text: str) -> str:
    """
    The frontend sends chip clicks like:
    AFSCME (regarding: "To determine your health insurance eligibility...")
    
    For flow detection, only use the actual chip answer.
    Otherwise the word 'eligibility' inside the regarding text can restart the flow.
    """
    return text.split("(regarding:", 1)[0].strip()


ELIGIBILITY_WORDS = [
    "eligible",
    "eligibility",
    "qualify",
    "qualified",
    "qualification",
    "qualifies",
    "do i qualify",
    "can i qualify",
    "am i eligible",
    "am i able",
    "am i allowed"
]


def has_eligibility_language(message: str) -> bool:
    msg = normalize_user_input(message)
    words = msg.split()

    for phrase in ELIGIBILITY_WORDS:
        if phrase in msg:
            return True

    # Misspelling support: eligble, elgiible, eligiblity, qualfy, etc.
    fuzzy_words = [
        "eligible",
        "eligibility",
        "qualify",
        "qualified",
        "qualification"
    ]

    for word in words:
        if get_close_matches(word, fuzzy_words, n=1, cutoff=0.70):
            return True

    return False


def detect_intent(message: str) -> Optional[str]:
    msg = normalize_user_input(message)

    intent_order = ["fmla", "health_insurance", "retirement", "leave", "fsa", "tuition_waiver"]

    for intent in intent_order:
        phrases = INTENT_PHRASES.get(intent, [])

        for phrase in phrases:
            phrase_norm = normalize_user_input(phrase)

            if phrase_norm in msg:
                return intent

            # Good for misspellings like "health insuranc"
            if get_close_matches(msg, [phrase_norm], n=1, cutoff=0.72):
                return intent

    return None


def reset_flow():
    FLOW_PROGRESS.update({
        "intent": None,
        "step": None,
        "group": None,
        "type": None,
        "hours": None
    })

def handle_guided_flow(message: str, history: list) -> Optional[str]:
    if not isinstance(FLOW_PROGRESS, dict):
        return None

    user_text = strip_regarding_context(message)
    message_lower = normalize_user_input(user_text)

    incoming_intent = detect_intent(user_text)
    asking_eligibility = has_eligibility_language(user_text)

    eligibility_intents = {
        "health_insurance",
        "retirement",
        "leave",
        "fmla",
        "fsa"
    }

    if asking_eligibility and incoming_intent in eligibility_intents:
        reset_flow()
        FLOW_PROGRESS["intent"] = incoming_intent
        FLOW_PROGRESS["step"] = None

    if not FLOW_PROGRESS.get("intent"):
        return None

    intent = FLOW_PROGRESS["intent"]

    if asking_eligibility and incoming_intent and incoming_intent != intent:
        reset_flow()
        FLOW_PROGRESS["intent"] = incoming_intent
        FLOW_PROGRESS["step"] = None
        intent = incoming_intent

    # --- Health Insurance Eligibility ----------------------------------------
    if intent == "health_insurance":
        if FLOW_PROGRESS["step"] is None:
            FLOW_PROGRESS["step"] = "group"
            return (
                "To determine your health insurance eligibility, I'll need a bit more information.\n"
                "Which employee group are you in?\n"
                "[OPTIONS: AFSCME | SCUPA | OPEIU | POA/SPFPA | APSCUF Coaches | APSCUF Faculty | Non-Represented]"
            )

        if FLOW_PROGRESS["step"] == "group":
            FLOW_PROGRESS["group"] = message_lower
            FLOW_PROGRESS["step"] = "type"
            return (
                "Are you a permanent or temporary employee?\n"
                "[OPTIONS: Permanent | Temporary]"
            )

        if FLOW_PROGRESS["step"] == "type":
            FLOW_PROGRESS["type"] = message_lower
            FLOW_PROGRESS["step"] = "hours"
            return (
                "Are you full-time or part-time?\n"
                "[OPTIONS: Full-time | Part-time (at least 50% of full-time hours)]"
            )

        if FLOW_PROGRESS["step"] == "hours":
            group    = FLOW_PROGRESS.get("group", "")
            emp_type = FLOW_PROGRESS.get("type", "")
            hours    = message_lower
            reset_flow()
            return f"__SYNTHESIZED__What health insurance benefits and coverage is a {emp_type} {hours} {group} employee eligible for at WCU?"

    # --- Retirement Eligibility ----------------------------------------------
    if intent == "retirement":
        if FLOW_PROGRESS["step"] is None:
            FLOW_PROGRESS["step"] = "retirement_status"
            return (
                "To determine your eligibility for retirement contributions, please choose the option that best describes you:\n"
                "[OPTIONS: Permanent full-time (>=50%) | Temporary >=50% (1+ year) | Faculty >=50% workload | Part-time <50% but 750+ hours]"
            )

        if FLOW_PROGRESS["step"] == "retirement_status":
            emp_type = message_lower
            reset_flow()
            return f"__SYNTHESIZED__What retirement plans and contribution options is a {emp_type} employee eligible for at WCU?"

    # --- Leave Time Eligibility ----------------------------------------------
    if intent == "leave":
        if FLOW_PROGRESS["step"] is None:
            FLOW_PROGRESS["step"] = "hours"
            return (
                "To determine your leave time eligibility, are you full-time or part-time?\n"
                "[OPTIONS: Full-time | Part-time (at least 50% of full-time hours)]"
            )

        if FLOW_PROGRESS["step"] == "hours":
            FLOW_PROGRESS["hours"] = message_lower
            FLOW_PROGRESS["step"] = "group"
            return (
                "Leave benefits can depend on your employee group. Which group are you in?\n"
                "[OPTIONS: AFSCME | APSCUF Coaches | APSCUF Faculty | Non-Represented | OPEIU | SCUPA | POA/SPFPA]"
            )

        if FLOW_PROGRESS["step"] == "group":
            hours = FLOW_PROGRESS.get("hours", "")
            group = message_lower
            reset_flow()
            return f"__SYNTHESIZED__What leave time and vacation accrual benefits is a {hours} {group} employee eligible for at WCU?"

    # --- FMLA Eligibility ----------------------------------------------------
    if intent == "fmla":
        if FLOW_PROGRESS["step"] is None:
            FLOW_PROGRESS["step"] = "group"
            return (
                "To determine your FMLA eligibility, which employee group are you in?\n"
                "[OPTIONS: AFSCME/SEIU/SPFPA/POA | APSCUF Faculty/Coaches | SCUPA | OPEIU | Non-Represented]"
            )

        if FLOW_PROGRESS["step"] == "group":
            FLOW_PROGRESS["group"] = message_lower
            FLOW_PROGRESS["step"] = "time_worked"
            return (
                "Have you worked for at least one year and worked 1,250 hours in the past 12 months?\n"
                "[OPTIONS: Yes | No | Not sure]"
            )

        if FLOW_PROGRESS["step"] == "time_worked":
            group       = FLOW_PROGRESS.get("group", "")
            time_worked = message_lower
            reset_flow()
            return f"__SYNTHESIZED__Is a {group} employee who has worked {time_worked} for one year and 1250 hours eligible for FMLA leave at WCU? What are the details?"

    # --- FSA Eligibility -----------------------------------------------------
    if intent == "fsa":
        if FLOW_PROGRESS["step"] is None:
            FLOW_PROGRESS["step"] = "fsa_type"
            return (
                "Which FSA are you asking about eligibility for?\n"
                "[OPTIONS: Healthcare FSA | Dependent Care FSA]"
            )

        if FLOW_PROGRESS["step"] == "fsa_type":
            fsa_type = message_lower
            reset_flow()
            return f"__SYNTHESIZED__Who is eligible for a {fsa_type} at WCU and how does it work?"

    return None



# --- Model Call ---------------------------------------------------------------

def ask_model(
    client: OpenAI,
    question: str,
    chunks: List[Dict[str, str]],
    history: List[Dict[str, str]],
) -> tuple:
    """Return (reply, tokens) where tokens = {prompt, completion, total}."""
    _tokens = {"prompt": 0, "completion": 0, "total": 0}

    def _extract_tokens(response) -> dict:
        u = getattr(response, "usage", None)
        if not u:
            return {"prompt": 0, "completion": 0, "total": 0}
        return {
            "prompt":     getattr(u, "prompt_tokens", 0),
            "completion": getattr(u, "completion_tokens", 0),
            "total":      getattr(u, "total_tokens", 0),
        }

    # Strip any (regarding: ...) chip context before PII check -- the appended
    # text may contain Rammy's own email/phone output, causing false positives.
    if contains_pii(strip_regarding_context(question)):
        return PII_WARNING_REPLY, _tokens

    kind = small_talk_kind(question)

    if kind == "identity":
        return IDENTITY_REPLY, _tokens

    if kind == "meta":
        return META_REPLY, _tokens

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
                    _tokens = _extract_tokens(response)
                    return answer, _tokens
        # No history or no context found -- treat as small talk
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
            _tokens = _extract_tokens(oos_response)
            return linkify_contacts(oos_response.choices[0].message.content.strip() or OUT_OF_SCOPE_REPLY), _tokens

        system_prompt = build_hr_instructions(context)
        # Strip any leading assistant messages -- OpenAI requires history to
        # start with a user turn. A leading assistant message (e.g. the welcome
        # greeting stored in history) causes GPT to respond with a greeting
        # instead of answering the actual question.
        trimmed_history = history[-4:] if history else []
        while trimmed_history and trimmed_history[0].get("role") != "user":
            trimmed_history = trimmed_history[1:]
        messages = (
            [{"role": "system", "content": system_prompt}]
            + trimmed_history
            + [{"role": "user", "content": question}]
        )

    # -- FIX: use chat.completions.create (not client.responses.create) --
    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        max_tokens=300,
        temperature=0.3,   # Lower temp = more consistent, factual replies
    )

    _tokens = _extract_tokens(response)
    answer = response.choices[0].message.content.strip()
    answer = linkify_contacts(answer)

    # If GPT returned the out-of-scope sentinel, generate a friendly decline
    if not answer or "OUTOFSCOPE" in answer:
        oos_prompt = build_out_of_scope_prompt(question)
        oos_response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": oos_prompt}],
            max_tokens=100,
            temperature=0.8,
        )
        t2 = _extract_tokens(oos_response)
        _tokens = {k: _tokens[k] + t2[k] for k in _tokens}
        return linkify_contacts(oos_response.choices[0].message.content.strip() or OUT_OF_SCOPE_REPLY), _tokens

    return answer, _tokens


# --- Flask App ----------------------------------------------------------------

app = Flask(__name__)

# --- MinIO Helper -------------------------------------------------------------

# Module-level MinIO config (mirrors docker-compose environment variables)
MINIO_HOST   = os.getenv("MINIO_HOST",   "minio:9000")
MINIO_USER   = os.getenv("MINIO_USER",   "minioadmin")
MINIO_PASS   = os.getenv("MINIO_PASS",   "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "documents")

try:
    from minio import Minio as _Minio
    from minio.error import S3Error
    MINIO_AVAILABLE = True
except ImportError:
    MINIO_AVAILABLE = False
    print("[minio] WARNING: minio package not installed -- PDF serving disabled.")

def _get_minio_client():
    """Return a connected Minio client, or None if unavailable."""
    if not MINIO_AVAILABLE:
        return None
    try:
        return _Minio(MINIO_HOST, access_key=MINIO_USER, secret_key=MINIO_PASS, secure=False)
    except Exception as e:
        print(f"[minio] Could not create client: {e}")
        return None


# --- Document Proxy Endpoint --------------------------------------------------

@app.route("/document/<path:filename>", methods=["GET"])
def serve_document(filename):
    """
    Proxies a PDF from MinIO so the browser can open it as a real URL.
    e.g. GET /document/benefits-guide.pdf  ->  streams the PDF bytes.

    This turns the internal  pdf:benefits-guide.pdf  source label into a
    clickable  http://localhost:5001/document/benefits-guide.pdf  link.
    """
    client = _get_minio_client()
    if client is None:
        return jsonify({"error": "Document storage unavailable."}), 503

    try:
        response = client.get_object(MINIO_BUCKET, filename)

        def generate():
            try:
                for chunk in response.stream(32 * 1024):
                    yield chunk
            finally:
                response.close()
                response.release_conn()

        return Response(
            stream_with_context(generate()),
            content_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="{filename}"',
                "Cache-Control": "private, max-age=3600",
            },
        )
    except S3Error as e:
        print(f"[document] MinIO error for '{filename}': {e}")
        return jsonify({"error": f"Document '{filename}' not found."}), 404
    except Exception as e:
        print(f"[document] Unexpected error for '{filename}': {e}")
        return jsonify({"error": "Could not retrieve document."}), 500

# Module-level state -- initialised once on startup
_chunks: List[Dict[str, str]] = []   # kept for API compat; no longer used for retrieval
_cache_lock = threading.Lock()
_client: Optional[OpenAI] = None
_qdrant_client: Optional[QdrantClient] = None
_embed_model = None   # SentenceTransformer instance
_startup_done = False


@app.before_request
def _ensure_startup():
    """Runs once on the first request -- handles flask run / gunicorn startup."""
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
    Does NOT reload the embedding model if already loaded -- avoids triple-init."""
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
    if _embed_model is None or _qdrant_client is None:
        return jsonify({"status": "loading", "python": "reachable"}), 503
    return jsonify({"status": "ok", "python": "reachable"})


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()

    # Prefer client-sent history (the frontend is the source of truth for
    # conversation context). Fall back to GLOBAL_HISTORY only if the client
    # did not send any -- e.g. during a /refresh ping or legacy callers.
    client_history = data.get("history")
    if isinstance(client_history, list) and client_history:
        history = client_history[-MAX_HISTORY:]
    else:
        global GLOBAL_HISTORY
        history = GLOBAL_HISTORY

    if not message:
        return jsonify({"error": "message is required"}), 400

    # PII check runs before everything else -- including the guided flow --
    # so sensitive data is never processed regardless of intent detection.
    if contains_pii(strip_regarding_context(message)):
        return jsonify({"reply": PII_WARNING_REPLY})

    with _cache_lock:
        current_chunks = list(_chunks)

    guided_reply = handle_guided_flow(message, history)

    if guided_reply:
        # If the flow returned a synthesized query, pass it to ask_model
        # so Qdrant retrieves specific eligibility context rather than
        # returning a vague answer based on the raw chip text.
        if guided_reply.startswith("__SYNTHESIZED__"):
            synthesized_query = guided_reply[len("__SYNTHESIZED__"):]
            try:
                reply, tokens = ask_model(_client, synthesized_query, current_chunks, history)
            except Exception as e:
                print(f"[/chat] Synthesized query error: {e}")
                return jsonify({"error": "Internal error -- please try again."}), 500
            is_oos = any(phrase in reply.lower() for phrase in [
                "outside", "can't help with that", "not able to", "reach out to hr",
                "hrs@wcupa", "contact hr", "610-436-2800"
            ])
            log_interaction(message, reply, is_oos, tokens)
            return jsonify({"reply": reply})
        return jsonify({"reply": guided_reply})

    try:
        reply, tokens = ask_model(_client, message, current_chunks, history)
    except Exception as e:
        print(f"[/chat] Error: {e}")
        return jsonify({"error": "Internal error -- please try again."}), 500

    is_oos = any(phrase in reply.lower() for phrase in [
        "outside", "can't help with that", "not able to", "reach out to hr",
        "hrs@wcupa", "contact hr", "610-436-2800"
    ])
    log_interaction(message, reply, is_oos, tokens)

    return jsonify({"reply": reply})


@app.route("/pdf/<path:filename>", methods=["GET"])
def serve_pdf(filename):
    """
    Fetches a PDF from MinIO using server-side credentials and streams it to the caller.
    Called by the Node.js /api/pdf/* proxy -- credentials never reach the browser.
    Flask's <path:filename> converter URL-decodes the name automatically, so
    'Dental%20Benefits.pdf' arrives here as 'Dental Benefits.pdf'.
    """
    # Block path traversal only
    if ".." in filename:
        return jsonify({"error": "Invalid filename."}), 400

    client = _get_minio_client()
    if client is None:
        return jsonify({"error": "Document storage unavailable -- MinIO not configured."}), 503

    print(f"[/pdf] Fetching '{filename}' from MinIO bucket '{MINIO_BUCKET}'")

    try:
        minio_response = client.get_object(MINIO_BUCKET, filename)

        def generate():
            try:
                for chunk in minio_response.stream(32 * 1024):
                    yield chunk
            finally:
                minio_response.close()
                minio_response.release_conn()

        return Response(
            stream_with_context(generate()),
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="{filename}"',
                "Cache-Control": "private, max-age=3600",
            },
        )
    except Exception as e:
        err = str(e)
        print(f"[/pdf] MinIO error for '{filename}': {e}")
        if "NoSuchKey" in err or "does not exist" in err.lower() or "404" in err:
            return jsonify({"error": f"Document '{filename}' not found in storage."}), 404
        return jsonify({"error": "Could not retrieve document."}), 503


@app.route("/refresh", methods=["POST"])
def refresh():
    threading.Thread(target=_load_sources, daemon=True).start()
    return jsonify({"message": "Source refresh started in background."})


@app.route("/analytics", methods=["GET"])
def analytics():
    """
    Returns analytics data from the JSONL log.
    Query params:
      ?limit=N   -- return only the last N records (default 1000)
    """
    limit = int(request.args.get("limit", 1000))
    records = []
    try:
        with _analytics_lock:
            if os.path.exists(ANALYTICS_LOG):
                with open(ANALYTICS_LOG, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                records.append(json.loads(line))
                            except json.JSONDecodeError:
                                pass
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    records = records[-limit:]

    # -- Aggregate metrics ----------------------------------------------------
    total = len(records)
    oos_count = sum(1 for r in records if r.get("out_of_scope"))

    topic_counts: dict = {}
    source_counts: dict = {}
    hourly_counts: dict = {}

    total_prompt_tokens     = 0
    total_completion_tokens = 0
    total_tokens            = 0
    # gpt-4.1-mini pricing (per 1M tokens, as of 2025)
    COST_PER_1M_PROMPT     = 0.40
    COST_PER_1M_COMPLETION = 1.60

    for r in records:
        topic = r.get("topic", "other")
        topic_counts[topic] = topic_counts.get(topic, 0) + 1

        src = r.get("source_type", "unknown")
        source_counts[src] = source_counts.get(src, 0) + 1

        ts = r.get("ts", "")
        if ts:
            try:
                hour = ts[11:13]  # "HH" from ISO timestamp
                hourly_counts[hour] = hourly_counts.get(hour, 0) + 1
            except Exception:
                pass

        total_prompt_tokens     += r.get("tokens_prompt", 0)
        total_completion_tokens += r.get("tokens_completion", 0)
        total_tokens            += r.get("tokens_total", 0)

    estimated_cost = (
        (total_prompt_tokens     / 1_000_000) * COST_PER_1M_PROMPT +
        (total_completion_tokens / 1_000_000) * COST_PER_1M_COMPLETION
    )

    return jsonify({
        "total_queries":            total,
        "out_of_scope":             oos_count,
        "oos_rate":                 round(oos_count / total * 100, 1) if total else 0,
        "topic_counts":             dict(sorted(topic_counts.items(), key=lambda x: -x[1])),
        "source_counts":            source_counts,
        "hourly_counts":            hourly_counts,
        "recent":                   list(reversed(records[-50:])),  # last 50, newest first
        "total_prompt_tokens":      total_prompt_tokens,
        "total_completion_tokens":  total_completion_tokens,
        "total_tokens":             total_tokens,
        "estimated_cost_usd":       round(estimated_cost, 4),
    })


# --- Entry Point --------------------------------------------------------------

if __name__ == "__main__":
    if not OPENAI_API_KEY:
        raise RuntimeError("Set OPENAI_API_KEY environment variable before starting.")

    _client = _init_client()
    _init_qdrant()       # Connect to Qdrant and load embedding model
    _startup_done = True # Prevent before_request from running init a second time

    app.run(host="0.0.0.0", port=5001, debug=False)
