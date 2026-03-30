"""
Rammy HR Chatbot — Qdrant Setup Script
=======================================
Run this ONCE (or whenever sources change) to populate the Qdrant vector DB.

Usage:
    python qdrant_setup.py

What it does:
  1. Fetches all HR source URLs (same list as chatbot_api.py)
  2. Cleans and chunks the text (sentence-aware, 700-char chunks with overlap)
  3. Embeds each chunk with SentenceTransformer (all-MiniLM-L6-v2)
  4. Upserts all points into Qdrant collection "rammy_hr"

Requirements (add to requirements.txt):
    qdrant-client>=1.9.0
    sentence-transformers>=2.7.0
    pymupdf>=1.24.0    (for PDF support — optional)
    beautifulsoup4     (already present)
    requests           (already present)
"""

import re
import os
from typing import List, Dict

import io
import requests
from bs4 import BeautifulSoup
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, Distance, VectorParams

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    print("[setup] WARNING: pymupdf not installed — PDF ingestion disabled.")

try:
    from minio import Minio
    from minio.error import S3Error
    MINIO_AVAILABLE = True
except ImportError:
    MINIO_AVAILABLE = False
    print("[setup] WARNING: minio not installed — PDF ingestion disabled.")

# ─── Config ───────────────────────────────────────────────────────────────────

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
COLLECTION  = "rammy_hr"
EMBED_MODEL = "all-MiniLM-L6-v2"
CHUNK_MAX_CHARS = 700   # characters per chunk (matches chatbot_api.py split_into_chunks)
CHUNK_OVERLAP   = 150   # character overlap between chunks
BATCH_SIZE      = 50    # upsert batch size

# ─── MinIO Config ────────────────────────────────────────────────────────────
MINIO_HOST   = os.getenv("MINIO_HOST",   "localhost:9000")
MINIO_USER   = os.getenv("MINIO_USER",   "minioadmin")
MINIO_PASS   = os.getenv("MINIO_PASS",   "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "documents")

# Full URL list — keep in sync with chatbot_api.py ALLOWED_URLS
SOURCE_URLS = [
    # Core HR
    "https://www.wcupa.edu/hr/faqs.aspx",
    "https://www.wcupa.edu/hr/employee-labor-relations.aspx",
    "https://www.wcupa.edu/hr/student-employment.aspx",
    "https://www.wcupa.edu/hr/professional-development.aspx",
    # I-9
    "https://www.uscis.gov/i-9-central/form-i-9-acceptable-documents",
    # Leave
    "https://www.wcupa.edu/hr/FMLA.aspx",
    "https://www.passhe.edu/hr/benefits/life-events/index.html",
    # Retirement
    "https://www.passhe.edu/hr/benefits/retirement/index.html",
    "https://www.passhe.edu/hr/benefits/retirement/voluntary-retirement-plans.html",
    "https://www.passhe.edu/hr/benefits/retirement/tsa.html",
    "https://www.passhe.edu/hr/benefits/retirement/deferred-compensation.html",
    "https://www.passhe.edu/hr/benefits/retirement/arp.html",
    "https://www.passhe.edu/hr/benefits/retirement/sers.html",
    # Benefits
    "https://www.wcupa.edu/hr/employee-benefits-vs-benefits-by-employee-group.aspx",
    # Workers Comp
    "https://www.wcupa.edu/hr/work-related-injuries.aspx",
    # Tuition
    "https://www.wcupa.edu/hr/tuition-waiver.aspx",
    "https://www.wcupa.edu/hr/tuition-waiver-information.aspx",
    # Payroll
    "https://www.wcupa.edu/_information/AFA/fbs/payroll.aspx",
    # Parking
    "https://www.wcupa.edu/dps/parkingservices/parkingPermits.aspx",
    "https://www.wcupa.edu/dps/parkingservices/employeeRegulations.aspx",
    "https://www.wcupa.edu/dps/parkingservices/faqs.aspx",
    # Holidays / Calendar
    "https://www.wcupa.edu/registrar/calendar/",
    # Employment
    "https://www.wcupa.edu/hr/why-work-at-wcu.aspx",
    "https://www.schooljobs.com/careers/wcupa",
    # External Retirement / Benefits providers
    # Included as reference URLs — content may be partial if sites require auth
    "https://www.tiaa.org/public/tcm/passhe/home",
    "https://retirementatwork.org/wcupa/",
    "https://sers.pa.gov/members/",
    "https://www.psers.pa.gov/Members/Pages/default.aspx",
    "https://www.empower.com/public/retirement",
    "https://nb.fidelity.com/public/nb/default/home",
]

# ─── Text Utilities ───────────────────────────────────────────────────────────

def normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()

def html_to_text(html: str) -> str:
    """Full-page extraction — strips scripts, styles, nav, etc."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "header", "footer", "nav"]):
        tag.decompose()
    return normalize_text(soup.get_text("\n"))[:150_000]

# ─── PDF Extraction ──────────────────────────────────────────────────────────

def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract and clean all text from a PDF byte string using PyMuPDF."""
    if not PYMUPDF_AVAILABLE:
        return ""
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages = []
        for page in doc:
            text = page.get_text()
            if text.strip():
                pages.append(normalize_text(text))
        return " ".join(pages)
    except Exception as e:
        print(f"    [pdf] Extraction error: {e}")
        return ""


# ─── Chunking ─────────────────────────────────────────────────────────────────

def split_into_chunks(text: str, url: str) -> List[Dict[str, str]]:
    """
    Sentence-aware chunking with character overlap.
    Splits on sentence boundaries, accumulates up to CHUNK_MAX_CHARS,
    then starts a new chunk reusing the last CHUNK_OVERLAP characters
    for context continuity.
    """
    chunks: List[Dict[str, str]] = []
    # Split on sentence-ending punctuation followed by whitespace
    parts = re.split(r"(?<=[\.\?\!])\s+|(?<=:)\s+", text)
    current: List[str] = []
    current_len = 0

    for part in parts:
        part = part.strip()
        if not part:
            continue
        if current_len + len(part) > CHUNK_MAX_CHARS and current:
            chunk_text = " ".join(current).strip()
            if len(chunk_text) > 40:
                chunks.append({"url": url, "text": chunk_text})
            # Carry the last ~CHUNK_OVERLAP chars into the next chunk for overlap
            overlap_text = chunk_text[-CHUNK_OVERLAP:]
            current = [overlap_text, part]
            current_len = len(overlap_text) + len(part)
        else:
            current.append(part)
            current_len += len(part)

    if current:
        chunk_text = " ".join(current).strip()
        if len(chunk_text) > 40:
            chunks.append({"url": url, "text": chunk_text})

    return chunks

# ─── Ingestion ────────────────────────────────────────────────────────────────

def fetch_and_chunk_all() -> List[Dict[str, str]]:
    headers = {"User-Agent": "RammyHRBot/2.0"}
    all_chunks: List[Dict[str, str]] = []

    for url in SOURCE_URLS:
        try:
            r = requests.get(url, headers=headers, timeout=20)
            r.raise_for_status()
            text = html_to_text(r.text)
            chunks = split_into_chunks(text, url)
            all_chunks.extend(chunks)
            print(f"  ✓ {url}  ({len(chunks)} chunks)")
        except Exception as e:
            print(f"  ✗ {url}  ERROR: {e}")

    return all_chunks

def fetch_and_chunk_pdfs() -> List[Dict[str, str]]:
    """
    Connects to MinIO, lists all PDFs in MINIO_BUCKET,
    extracts text from each, and returns chunks ready for embedding.
    Skips gracefully if MinIO or PyMuPDF are unavailable.
    """
    if not MINIO_AVAILABLE or not PYMUPDF_AVAILABLE:
        print("  [minio] Skipping PDF ingestion — minio or pymupdf not available.")
        return []

    try:
        client = Minio(MINIO_HOST, access_key=MINIO_USER, secret_key=MINIO_PASS, secure=False)
    except Exception as e:
        print(f"  [minio] Could not connect: {e}")
        return []

    # Create bucket if it doesn't exist yet
    try:
        if not client.bucket_exists(MINIO_BUCKET):
            client.make_bucket(MINIO_BUCKET)
            print(f"  [minio] Created bucket '{MINIO_BUCKET}' (empty — upload PDFs via http://localhost:9001).")
            return []
    except S3Error as e:
        print(f"  [minio] Bucket check failed: {e}")
        return []

    all_chunks: List[Dict[str, str]] = []
    pdf_count = 0

    try:
        objects = list(client.list_objects(MINIO_BUCKET))
    except S3Error as e:
        print(f"  [minio] Could not list objects: {e}")
        return []

    pdfs = [obj for obj in objects if obj.object_name.lower().endswith(".pdf")]

    if not pdfs:
        print(f"  [minio] Bucket '{MINIO_BUCKET}' exists but contains no PDFs.")
        return []

    for obj in pdfs:
        name = obj.object_name
        print(f"  Processing PDF: {name}...")
        try:
            response = client.get_object(MINIO_BUCKET, name)
            pdf_bytes = response.read()
            response.close()
            response.release_conn()
        except S3Error as e:
            print(f"    ✗ Could not fetch '{name}': {e}")
            continue

        text = extract_pdf_text(pdf_bytes)
        if not text.strip():
            print(f"    ✗ No text extracted from '{name}' — skipping.")
            continue

        # Use a descriptive source label so the LLM can cite it
        source_label = f"pdf:{name}"
        chunks = split_into_chunks(text, source_label)
        all_chunks.extend(chunks)
        pdf_count += 1
        print(f"    ✓ {len(chunks)} chunks from '{name}'")

    print(f"  [minio] Processed {pdf_count} PDF(s) → {len(all_chunks)} chunks total.")
    return all_chunks


def build_and_upload():
    print(f"\n── Qdrant Setup: Rammy HR Chatbot ──")
    print(f"Connecting to Qdrant at {QDRANT_HOST}:{QDRANT_PORT}...")
    qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

    print(f"Loading embedding model '{EMBED_MODEL}'...")
    model = SentenceTransformer(EMBED_MODEL)

    print(f"\nFetching and chunking {len(SOURCE_URLS)} web sources...")
    chunks = fetch_and_chunk_all()

    print(f"\nFetching and chunking PDFs from MinIO...")
    pdf_chunks = fetch_and_chunk_pdfs()
    chunks.extend(pdf_chunks)

    print(f"\nTotal chunks: {len(chunks)} ({len(chunks) - len(pdf_chunks)} web + {len(pdf_chunks)} PDF)")

    if not chunks:
        print("No chunks produced — aborting.")
        return

    print(f"\nEmbedding {len(chunks)} chunks...")
    texts = [c["text"] for c in chunks]
    embeddings = model.encode(texts, batch_size=64, show_progress_bar=True)
    vector_size = embeddings.shape[1]

    # Always recreate the collection so a re-run gives a clean slate
    print(f"\nRecreating Qdrant collection '{COLLECTION}' (vector size: {vector_size})...")
    try:
        qdrant.delete_collection(COLLECTION)
        print(f"  Deleted existing collection '{COLLECTION}'.")
    except Exception:
        pass  # Collection didn't exist yet — that's fine
    qdrant.create_collection(
        collection_name=COLLECTION,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )

    print(f"Uploading in batches of {BATCH_SIZE}...")
    points = [
        PointStruct(
            id=i,
            vector=embeddings[i].tolist(),
            payload={"text": chunks[i]["text"], "url": chunks[i]["url"]},
        )
        for i in range(len(chunks))
    ]

    for i in range(0, len(points), BATCH_SIZE):
        batch = points[i : i + BATCH_SIZE]
        qdrant.upsert(collection_name=COLLECTION, points=batch)
        print(f"  Uploaded {i + len(batch)}/{len(points)}")

    print(f"\n✓ Done. {len(points)} vectors in '{COLLECTION}'.")

if __name__ == "__main__":
    build_and_upload()
