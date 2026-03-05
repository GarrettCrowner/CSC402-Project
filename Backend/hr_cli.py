import os
import re
import time
import threading
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import psutil
import requests
from bs4 import BeautifulSoup
from openai import OpenAI

# -----------------------------
# CONFIG
# -----------------------------
OPENAI_API_KEY = ""
OPENAI_ORG_ID = ""
OPENAI_PROJECT_ID = ""

MODEL = "gpt-4.1-mini"

ALLOWED_URLS = [
    "https://www.wcupa.edu/hr/faqs.aspx",
    "https://www.uscis.gov/i-9-central/form-i-9-acceptable-documents",
    "https://www.passhe.edu/hr/benefits/life-events/index.html",
    "https://www.passhe.edu/hr/benefits/retirement/voluntary-retirement-plans.html",
    "https://www.wcupa.edu/hr/FMLA.aspx",
    "https://www.wcupa.edu/hr/employee-labor-relations.aspx",
]

OUT_OF_SCOPE_REPLY = "I can not answer that question"

PII_WARNING_REPLY = (
    "For your privacy, please do not include personal information in chat. "
    "Please remove names, addresses, emails, phone numbers, ID numbers, or any "
    "government or banking information, then ask again."
)

IDENTITY_REPLY = (
    "I’m Rammy, the West Chester University mascot and your HR chatbot. "
    "I’m here to help with HR-related questions."
)

# -----------------------------
# SMALL TALK
# -----------------------------
_GREETING_RE = re.compile(
    r"^\s*(hi|hello|hey|good\s+morning|good\s+afternoon|good\s+evening)\b",
    re.IGNORECASE,
)

_HOW_ARE_YOU_RE = re.compile(
    r"^\s*(how\s+are\s+you|hru|how's\s+it\s+going)\b",
    re.IGNORECASE,
)

_GOODBYE_RE = re.compile(
    r"^\s*(bye|goodbye|see\s+ya|later|take\s+care)\b",
    re.IGNORECASE,
)

_WHO_ARE_YOU_RE = re.compile(
    r"^\s*(who are you|what are you|who is rammy|what is rammy)\??\s*$",
    re.IGNORECASE,
)


def small_talk_kind(text: str) -> Optional[str]:
    t = text.strip()
    if _GREETING_RE.search(t):
        return "greeting"
    if _HOW_ARE_YOU_RE.search(t):
        return "how_are_you"
    if _GOODBYE_RE.search(t):
        return "goodbye"
    if _WHO_ARE_YOU_RE.search(t):
        return "identity"
    return None


# -----------------------------
# PII DETECTION
# -----------------------------
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)

PHONE_RE = re.compile(
    r"\b(?:\+?1[\s\-.]?)?(?:\(?\d{3}\)?[\s\-.]?)\d{3}[\s\-.]?\d{4}\b"
)

SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

STREET_ADDRESS_RE = re.compile(
    r"\b\d{1,6}\s+[A-Za-z0-9.\- ]+\s+"
    r"(street|st|avenue|ave|road|rd|lane|ln|drive|dr|court|ct|boulevard|blvd|way|place|pl)\b",
    re.IGNORECASE,
)

NAME_INTRO_RE = re.compile(
    r"\b(my name is|this is)\s+[A-Za-z]+(?:\s+[A-Za-z]+){0,2}\b",
    re.IGNORECASE,
)

LONG_ID_RE = re.compile(r"\b\d{6,}\b")

BANK_CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,16}\b")


def contains_pii(text: str) -> bool:
    if not text or not text.strip():
        return False

    if EMAIL_RE.search(text):
        return True
    if PHONE_RE.search(text):
        return True
    if SSN_RE.search(text):
        return True
    if STREET_ADDRESS_RE.search(text):
        return True
    if BANK_CARD_RE.search(text):
        return True
    if NAME_INTRO_RE.search(text):
        return True
    if LONG_ID_RE.search(text):
        return True

    return False


# -----------------------------
# TEXT CLEANING
# -----------------------------
def normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript", "svg", "header", "footer", "nav"]):
        tag.decompose()

    text = soup.get_text("\n")
    text = normalize_text(text)

    if len(text) > 150000:
        text = text[:150000]

    return text


# -----------------------------
# FETCHING
# -----------------------------
def fetch_sources() -> Dict[str, str]:
    headers = {"User-Agent": "RammyHRBot"}
    pages = {}

    for url in ALLOWED_URLS:
        try:
            r = requests.get(url, headers=headers, timeout=20)
            r.raise_for_status()
            pages[url] = html_to_text(r.text)
        except Exception as e:
            pages[url] = f"FETCH ERROR {e}"

    return pages


# -----------------------------
# CHUNKING / KNOWLEDGE
# -----------------------------
def split_into_chunks(text: str, url: str) -> List[Dict[str, str]]:
    chunks = []

    raw_parts = re.split(r"(?<=[\.\?\!])\s+|(?<=:)\s+", text)

    current = []
    current_len = 0
    max_len = 700

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
    all_chunks = []
    for url in ALLOWED_URLS:
        page_text = pages.get(url, "")
        if page_text.startswith("FETCH ERROR"):
            continue
        all_chunks.extend(split_into_chunks(page_text, url))
    return all_chunks


# -----------------------------
# QUERY NORMALIZATION
# -----------------------------
def normalize_question_for_search(q: str) -> str:
    q = q.lower().strip()

    replacements = {
        r"\bchange\b": "update",
        r"\bmodify\b": "update",
        r"\bedit\b": "update",
        r"\bemail address\b": "email",
        r"\bhome address\b": "address",
        r"\bam i able to\b": "",
        r"\bcan i\b": "",
        r"\bhow do i\b": "",
        r"\bhow can i\b": "",
        r"\bwhere do i\b": "",
        r"\bwhat is\b": "",
        r"\bplease\b": "",
    }

    for pattern, repl in replacements.items():
        q = re.sub(pattern, repl, q)

    q = re.sub(r"[^a-z0-9\s]", " ", q)
    q = normalize_text(q)
    return q


def tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def score_chunk(question: str, chunk: str) -> float:
    q_norm = normalize_question_for_search(question)
    c_norm = normalize_question_for_search(chunk)

    q_tokens = tokenize(q_norm)
    c_tokens = set(tokenize(c_norm))

    if not q_tokens:
        return 0.0

    score = 0.0

    for token in q_tokens:
        if token in c_tokens:
            score += 1.0

    phrase_boosts = [
        ("update address", 4.0),
        ("address", 2.0),
        ("email", 2.0),
        ("employee self service", 3.0),
        ("ess", 3.0),
        ("forgiveness form", 3.0),
        ("loan forgiveness", 3.0),
        ("employee group", 3.0),
        ("fmla", 3.0),
    ]

    for phrase, value in phrase_boosts:
        if phrase in q_norm and phrase in c_norm:
            score += value

    return score


def retrieve_relevant_chunks(question: str, chunks: List[Dict[str, str]], top_k: int = 5) -> List[Dict[str, str]]:
    scored = []
    for chunk in chunks:
        s = score_chunk(question, chunk["text"])
        if s > 0:
            scored.append((s, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [chunk for _, chunk in scored[:top_k]]


def build_context(question: str, chunks: List[Dict[str, str]]) -> str:
    selected = retrieve_relevant_chunks(question, chunks, top_k=5)

    if not selected:
        return ""

    parts = []
    for i, chunk in enumerate(selected, start=1):
        parts.append(f"Source {i}: {chunk['url']}\n{chunk['text']}")

    return "\n\n".join(parts)


# -----------------------------
# PROMPTS
# -----------------------------
def build_hr_instructions(context: str) -> str:
    return f"""
You are Rammy, the West Chester University mascot.

You are an HR assistant.

Rules:
- Only answer HR-related questions.
- Use only the context provided below.
- If the answer is not in the context, reply exactly: {OUT_OF_SCOPE_REPLY}
- If the question is not HR-related, reply exactly: {OUT_OF_SCOPE_REPLY}
- Treat similar user wording as the same intent. For example:
  - change address = update address
  - modify address = update address
  - can I update my address = how do I update my address
- If the context clearly answers the question, respond naturally in 1-3 sentences.
- Do not mention context or sources.
- Do not use markdown.
- Do not use bullet points.

Context:
{context}
""".strip()


def build_smalltalk_prompt(user_text: str) -> str:
    return f"""
You are Rammy, the West Chester University mascot.

The user said:
{user_text}

Respond naturally like a friendly mascot talking to a person.
Keep it short.
Ready to answer HR-related questions.
Use 1 or 2 sentences.
You may answer questions about who or what you are.
Do not answer non-HR questions beyond simple small talk.
""".strip()


# -----------------------------
# PERFORMANCE MONITOR
# -----------------------------
@dataclass
class PerfStats:
    latency: float
    cpu_max: float
    ram_max: float


def monitor_resources(stop_evt):
    proc = psutil.Process(os.getpid())

    cpu_samples = []
    ram_samples = []

    while not stop_evt.is_set():
        cpu_samples.append(psutil.cpu_percent())
        ram_samples.append(proc.memory_info().rss / (1024 * 1024))
        time.sleep(0.2)

    return {
        "cpu": max(cpu_samples) if cpu_samples else 0,
        "ram": max(ram_samples) if ram_samples else 0,
    }


# -----------------------------
# MODEL CALL
# -----------------------------
def ask_model(client, question: str, chunks: List[Dict[str, str]], history: List[Dict[str, str]]) -> Tuple[str, PerfStats]:
    stop_evt = threading.Event()
    monitor_result = {}

    def run_monitor():
        nonlocal monitor_result
        monitor_result = monitor_resources(stop_evt)

    thread = threading.Thread(target=run_monitor)
    thread.start()

    start = time.perf_counter()

    try:
        if contains_pii(question):
            stop_evt.set()
            thread.join()

            latency = time.perf_counter() - start
            stats = PerfStats(
                latency=latency,
                cpu_max=monitor_result.get("cpu", 0),
                ram_max=monitor_result.get("ram", 0),
            )
            return PII_WARNING_REPLY, stats

        kind = small_talk_kind(question)

        if kind == "identity":
            stop_evt.set()
            thread.join()

            latency = time.perf_counter() - start
            stats = PerfStats(
                latency=latency,
                cpu_max=monitor_result.get("cpu", 0),
                ram_max=monitor_result.get("ram", 0),
            )
            return IDENTITY_REPLY, stats

        if kind:
            system_prompt = build_smalltalk_prompt(question)
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ]
        else:
            context = build_context(question, chunks)

            if not context:
                stop_evt.set()
                thread.join()

                latency = time.perf_counter() - start
                stats = PerfStats(
                    latency=latency,
                    cpu_max=monitor_result.get("cpu", 0),
                    ram_max=monitor_result.get("ram", 0),
                )
                return OUT_OF_SCOPE_REPLY, stats

            system_prompt = build_hr_instructions(context)
            trimmed_history = history[-4:] if history else []

            messages = [{"role": "system", "content": system_prompt}] + trimmed_history + [
                {"role": "user", "content": question}
            ]

        response = client.responses.create(
            model=MODEL,
            input=messages
        )

        answer = response.output_text.strip()

        if not answer:
            answer = OUT_OF_SCOPE_REPLY

    except Exception as e:
        answer = f"Error: {e}"

    stop_evt.set()
    thread.join()

    latency = time.perf_counter() - start

    stats = PerfStats(
        latency=latency,
        cpu_max=monitor_result.get("cpu", 0),
        ram_max=monitor_result.get("ram", 0),
    )

    return answer, stats


# -----------------------------
# MAIN
# -----------------------------
def main():
    api_key = OPENAI_API_KEY

    if not api_key:
        print("Add your API key to the OPENAI_API_KEY environment variable.")
        return

    client_kwargs = {"api_key": api_key}
    if OPENAI_ORG_ID:
        client_kwargs["organization"] = OPENAI_ORG_ID
    if OPENAI_PROJECT_ID:
        client_kwargs["project"] = OPENAI_PROJECT_ID

    client = OpenAI(**client_kwargs)

    print("Fetching HR sources...")
    pages = fetch_sources()
    chunks = build_chunks(pages)

    print("Rammy HR chatbot ready\n")

    conversation_history = []

    while True:
        try:
            question = input("You: ").strip()

            if not question:
                continue

            if question.lower() == "/refresh":
                print("Refreshing sources...")
                pages = fetch_sources()
                chunks = build_chunks(pages)
                print("Updated\n")
                continue

            answer, stats = ask_model(client, question, chunks, conversation_history)

            print("\nRammy:", answer)

            if answer != PII_WARNING_REPLY:
                conversation_history.append({"role": "user", "content": question})
                conversation_history.append({"role": "assistant", "content": answer})

                if len(conversation_history) > 8:
                    conversation_history = conversation_history[-8:]

            print(
                f"\nLatency {stats.latency:.2f}s | CPU {stats.cpu_max:.1f}% | RAM {stats.ram_max:.1f}MB\n"
            )

        except KeyboardInterrupt:
            print("\nSession ended")
            break


if __name__ == "__main__":
    main()
