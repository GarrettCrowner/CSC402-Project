# Rammy — WCU HR Chatbot

Rammy is an AI-powered HR chatbot for West Chester University. It answers HR-related questions using content sourced from official WCU and PASSHE HR pages, retrieved via semantic vector search and answered by OpenAI's GPT-4.1-mini.

---

## Architecture

```
Browser (embed.html + chat.js)
        │
        ├──── PDF links (/api/pdf/*)
        │         │
        │         ▼
        │   Node.js Express Server  (port 3000)
        │     Rate limiting · CORS · input validation · proxy
        │     PDF proxy → MinIO (direct, credentialed)
        │
        └──── Chat messages (/api/chat)
                  │
                  ▼
            Node.js Express Server  (port 3000)
                  │
                  ▼
            Python Flask Service  (port 5001)
              PII detection · small talk routing · context assembly
                  │                         │
                  ▼                         ▼
            Qdrant Vector DB           OpenAI API
              (port 6333)              gpt-4.1-mini
              semantic retrieval
                  ▲
                  │
            qdrant_setup.py
              ├── 28 WCU/PASSHE web sources
              └── PDFs from MinIO (port 9000)
                  ▲
                  │
            MinIO Object Storage
              (port 9000 · console port 9001)
              HR PDF documents
```

**Key files:**

| File | Purpose |
|---|---|
| `chat.js` | Frontend chat widget — message rendering, quick-reply chips, API calls, PDF link handling |
| `embed.html` | WCU HR page with the chatbot embedded |
| `styling.css` | Scoped styles for the chat widget |
| `server.js` | Node.js API gateway + direct MinIO PDF proxy |
| `chatbot_api.py` | Python Flask backend — all chatbot logic, PDF URL resolution |
| `qdrant_setup.py` | One-time script to populate the Qdrant vector database |
| `docker-compose.yml` | Orchestrates all four services |
| `Dockerfile.python` | Python service container |
| `Dockerfile.node` | Node.js service container |
| `.dockerignore` | Keeps build context lean — excludes secrets, caches, frontend files |

---

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [Git](https://git-scm.com/)
- An OpenAI API key — get one at [platform.openai.com](https://platform.openai.com)

---

## First-Time Setup

### 1. Clone the repository

```bash
git clone https://github.com/GarrettCrowner/CSC402-Project.git
cd CSC402-Project
```

### 2. Create your `.env` file

```bash
echo 'OPENAI_API_KEY=sk-your-actual-key-here
OPENAI_ORG_ID=
OPENAI_PROJECT_ID=
MINIO_USER=minioadmin
MINIO_PASS=minioadmin
MINIO_BUCKET=documents' > .env
```

Replace `sk-your-actual-key-here` with your real OpenAI API key.

> ⚠️ Never share your `.env` file or commit it to GitHub. Your API key is private.

### 3. Start Docker Desktop

Open Docker Desktop and wait for the whale icon in your menu bar to stop animating.

### 4. Build and start all services

```bash
docker-compose up --build -d
```

> ⏱️ **The first build takes 15–25 minutes.** Docker is downloading large ML dependencies including PyTorch (~800MB) and sentence-transformers. Subsequent startups with `docker-compose up` (no `--build`) take under 30 seconds.

### 5. Populate the vector database

Fetches all WCU/PASSHE HR source pages and any PDFs in MinIO, chunks and embeds them, and uploads to Qdrant. Run once after the first build, and again whenever sources or PDFs change.

```bash
docker exec rammy-python python qdrant_setup.py
```

You will see each source processed and a final confirmation:

```
✓ Done. 287 vectors in 'rammy_hr'.
```

### 6. Open the frontend

```bash
open embed.html
```

Or right-click `embed.html` in VS Code and select **Open with Live Server**.

---

## Running the App

**After first-time setup, every subsequent run is just:**

```bash
docker-compose up
```

**Shut down:**

```bash
docker-compose down
```

> Qdrant and MinIO data persist in named Docker volumes — you do **not** need to re-run `qdrant_setup.py` each time.

---

## MinIO — PDF Document Storage

MinIO is an S3-compatible object storage server. HR staff can upload PDF documents (handbooks, contracts, benefit guides, collective bargaining agreements, etc.) and Rammy will answer questions from them. PDF links in chat responses are clickable and open the document directly in the browser.

### How PDF linking works

When a PDF is indexed, its source is stored as `pdf:filename.pdf` in Qdrant. The Python backend resolves this to a full URL (`http://localhost:3000/api/pdf/filename.pdf`) before passing context to the LLM. When a user clicks the link, Node.js fetches the file directly from MinIO using server-side credentials and streams it to the browser — MinIO is never exposed directly.

### Uploading PDFs

1. Open the MinIO web console: [http://localhost:9001](http://localhost:9001)
2. Login with your `MINIO_USER` / `MINIO_PASS` from `.env` (default: `minioadmin` / `minioadmin`)
3. Create a bucket named exactly `documents` (first time only)
4. Click into the bucket → **Upload** → **Upload Files** → select your PDFs
5. Re-run the setup script to index the new documents:

```bash
docker exec rammy-python python qdrant_setup.py
```

Repeat steps 4–5 whenever new documents are added — no code changes needed.

> **Note on filenames:** Filenames with spaces are fully supported (e.g. `Dental Benefits Summary.pdf`). Avoid colons (`:`) in filenames as they can interfere with URL routing.

### Verifying MinIO is running

```bash
# Health check — expect 200 OK
curl http://localhost:9000/minio/health/live

# List all indexed PDFs
docker exec rammy-python python -c "
from minio import Minio
client = Minio('minio:9000', access_key='minioadmin', secret_key='minioadmin', secure=False)
for o in client.list_objects('documents'):
    print(o.object_name)
"

# View logs
docker logs rammy-minio
```

---

## Verify Everything is Connected

```bash
curl http://localhost:3000/api/health
```

Expected response:

```json
{ "status": "ok", "python": "reachable" }
```

Check the Qdrant dashboard at [http://localhost:6333/dashboard](http://localhost:6333/dashboard) to confirm the `rammy_hr` collection exists and has points.

---

## Refreshing HR Sources

To re-index web sources and PDFs:

```bash
docker exec rammy-python python qdrant_setup.py
```

Or trigger a reconnect (without re-indexing) from the chat window via ⋮ menu → **Refresh HR sources**, or:

```bash
curl -X POST http://localhost:3000/api/refresh
```

---

## Common Issues

| Symptom | Fix |
|---|---|
| First build taking 15–25 minutes | Normal — PyTorch and ML dependencies are large. Let it finish. |
| `Connection refused` on port 3000 | Make sure Docker Desktop is running, then `docker-compose up` |
| `python unreachable` in health check | Run `docker logs rammy-python` to see the error |
| Port already in use | Run `docker-compose down` then `docker-compose up` again |
| `.env not found` error | Make sure you completed Step 2 above |
| Bot only gives out-of-scope replies | Run `docker exec rammy-python python qdrant_setup.py` — Qdrant is empty |
| `rammy_hr` collection not found | Same as above — Qdrant needs to be populated first |
| MinIO console not loading | Run `docker logs rammy-minio` — confirm it started on port 9001 |
| PDFs not being indexed | Make sure they are in a bucket named exactly `documents`, then re-run `qdrant_setup.py` |
| PDF link opens to `Could not retrieve document` | Run `docker logs rammy-python` — check for MinIO connection errors; confirm the filename in MinIO matches exactly |
| PDF filenames with colons not working | Rename the file in MinIO to remove the colon, then re-run `qdrant_setup.py` |
| Mac AirPlay conflict on port 5000 | Already handled — app uses port 5001 |
| `ModuleNotFoundError` running scripts locally | Always run scripts inside Docker: `docker exec rammy-python python <script>.py` |

---

## Useful Commands

```bash
# View logs for each service
docker logs rammy-python
docker logs rammy-node
docker logs rammy-qdrant
docker logs rammy-minio

# Run an interactive shell inside the Python container
docker exec -it rammy-python bash

# Force a clean rebuild (also wipes Qdrant and MinIO volumes)
docker-compose down -v
docker system prune -f
docker-compose up --build -d
docker exec rammy-python python qdrant_setup.py

# Check how many vectors are in Qdrant
curl http://localhost:6333/collections/rammy_hr

# Check MinIO health
curl http://localhost:9000/minio/health/live

# List all PDFs currently in MinIO
docker exec rammy-python python -c "
from minio import Minio
client = Minio('minio:9000', access_key='minioadmin', secret_key='minioadmin', secure=False)
for o in client.list_objects('documents'):
    print(repr(o.object_name))
"
```

---

## Source URLs

Rammy draws its web knowledge from the following official pages. To add or remove sources, edit the `SOURCE_URLS` list in `qdrant_setup.py` and re-run it.

- WCU HR FAQs
- WCU Employee & Labor Relations
- WCU Student Employment
- WCU Professional Development
- WCU Why Work at WCU
- WCU Job Openings (SchoolJobs)
- USCIS I-9 Acceptable Documents
- WCU FMLA
- PASSHE Life Events
- PASSHE Retirement (index, ARP, SERS, TSA, deferred compensation, voluntary plans)
- WCU Employee Benefits by Group
- WCU Work-Related Injuries
- WCU Tuition Waiver (two pages)
- WCU Payroll
- WCU Parking (permits, regulations, FAQs)
- WCU Academic Calendar
- TIAA, Retirement@Work, SERS, PSERS, Empower, Fidelity (external reference URLs)

PDF sources are managed separately via the MinIO console — see the MinIO section above.
