# Rammy — WCU HR Chatbot

Rammy is an AI-powered HR assistant for West Chester University. It answers HR-related questions using content sourced from official WCU and PASSHE HR pages, retrieved via semantic vector search and answered by OpenAI's GPT-4.1-mini.

---

## Project Structure

```
rammy-hr-chatbot/
├── frontend/
│   ├── embed.html          # WCU HR page with the chatbot embedded
│   ├── analytics.html      # Analytics dashboard
│   ├── chat.js             # Chat widget logic — rendering, quick-reply chips, API calls
│   └── styling.css         # Scoped styles for the chat widget
│
├── backend/
│   ├── chatbot_api.py      # Python Flask service — all chatbot logic, PDF URL resolution
│   ├── qdrant_setup.py     # One-time script to populate the Qdrant vector database
│   └── requirements.txt    # Python dependencies
│
├── server/
│   ├── server.js           # Node.js API gateway + MinIO PDF proxy
│   └── package.json        # Node.js dependencies
│
├── docker/
│   ├── Dockerfile.python   # Python service container
│   ├── Dockerfile.node     # Node.js service container
│   └── docker-compose.yml  # Orchestrates all four services
│
├── docs/
│   └── Next_Steps.txt      # Active development notes
│
└── .env                    # Secret keys and config (never commit this)
```

> **Note:** The structure above reflects the recommended organization. See [Folder Organization](#folder-organization) for migration steps.

---

## Architecture

```
Browser (frontend/embed.html + chat.js)
        │
        ├──── PDF links (/api/pdf/*)
        │         │
        │         ▼
        │   Node.js Express Server  (port 3000)
        │     Rate limiting · CORS · input validation · proxy
        │     PDF proxy → MinIO (credentialed, never exposed)
        │
        └──── Chat messages (/api/chat)
                  │
                  ▼
            Node.js Express Server  (port 3000)
                  │
                  ▼
            Python Flask Service  (port 5001)
              PII detection · small-talk routing · context assembly
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

### Services at a Glance

| Service | Port | Purpose |
|---|---|---|
| Node.js (Express) | 3000 | API gateway, rate limiting, PDF proxy |
| Python (Flask) | 5001 | Chatbot logic, vector search, LLM calls |
| Qdrant | 6333 | Vector database — semantic retrieval |
| MinIO | 9000 / 9001 | PDF object storage / web console |

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

> ⚠️ Never commit your `.env` file. Add it to `.gitignore`.

### 3. Start Docker Desktop

Open Docker Desktop and wait for the whale icon to stop animating.

### 4. Build and start all services

```bash
docker-compose up --build -d
```

> ⏱️ **The first build takes 15–25 minutes.** Docker downloads large ML dependencies including PyTorch (~800 MB) and sentence-transformers. Subsequent `docker-compose up` runs take under 30 seconds.

### 5. Populate the vector database

Fetches all WCU/PASSHE HR web sources and any PDFs in MinIO, chunks and embeds them, and uploads to Qdrant. Run once after the first build — and again whenever sources or PDFs change.

```bash
docker exec rammy-python python qdrant_setup.py
```

Expected output:

```
✓ Done. 287 vectors in 'rammy_hr'.
```

### 6. Open the frontend

Open `frontend/embed.html` in your browser, or right-click it in VS Code and select **Open with Live Server**.

---

## Day-to-Day Usage

**Start the app:**
```bash
docker-compose up
```

**Shut down:**
```bash
docker-compose down
```

> Qdrant and MinIO data persist in named Docker volumes — you do **not** need to re-run `qdrant_setup.py` on every restart.

---

## MinIO — PDF Document Storage

MinIO is an S3-compatible object storage server. HR staff can upload PDF documents (handbooks, contracts, benefit guides, collective bargaining agreements, etc.) and Rammy will include them in answers. PDF links in chat responses are clickable and open directly in the browser.

### How PDF Linking Works

When a PDF is indexed, its source is stored as `pdf:filename.pdf` in Qdrant. The Python backend resolves this to a URL (`http://localhost:3000/api/pdf/filename.pdf`) before passing context to the LLM. When a user clicks the link, Node.js fetches the file from MinIO using server-side credentials and streams it to the browser — MinIO credentials are never exposed to the client.

### Uploading PDFs

1. Open the MinIO console: [http://localhost:9001](http://localhost:9001)
2. Log in with `MINIO_USER` / `MINIO_PASS` from `.env` (default: `minioadmin` / `minioadmin`)
3. Create a bucket named exactly `documents` (first time only)
4. Click into the bucket → **Upload** → **Upload Files** → select your PDFs
5. Re-run the setup script to index them:

```bash
docker exec rammy-python python qdrant_setup.py
```

> **Note on filenames:** Spaces in filenames are fully supported (e.g. `Dental Benefits Summary.pdf`). Avoid colons (`:`) as they interfere with URL routing.

### Verifying MinIO

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
```

---

## Refreshing HR Sources

To re-index all web sources and PDFs:

```bash
docker exec rammy-python python qdrant_setup.py
```

Or trigger a refresh without re-indexing from the chat window via ⋮ → **Refresh HR sources**, or:

```bash
curl -X POST http://localhost:3000/api/refresh
```

---

## Health Check

```bash
curl http://localhost:3000/api/health
```

Expected response:

```json
{ "status": "ok", "python": "reachable" }
```

Check the Qdrant dashboard at [http://localhost:6333/dashboard](http://localhost:6333/dashboard) to confirm the `rammy_hr` collection exists.

---

## Analytics

Open `frontend/analytics.html` in your browser to view usage metrics. Data is served from the Python backend via `GET /api/analytics`.

---

## Folder Organization

If your files are currently all in the root directory, reorganize them into the structure shown above:

```bash
mkdir -p frontend backend server docker docs

# Frontend
mv embed.html analytics.html chat.js styling.css frontend/

# Backend
mv chatbot_api.py qdrant_setup.py requirements.txt backend/

# Server
mv server.js package.json server/

# Docker
mv Dockerfile.python Dockerfile.node docker-compose.yml docker/

# Docs
mv Next_Steps.txt docs/
```

> ⚠️ After moving files, update the `context:` and `dockerfile:` paths in `docker-compose.yml` and the `COPY` paths in both Dockerfiles to match the new structure.

---

## Common Issues

| Symptom | Fix |
|---|---|
| First build taking 15–25 minutes | Normal — PyTorch and ML dependencies are large |
| `Connection refused` on port 3000 | Make sure Docker Desktop is running, then `docker-compose up` |
| `python unreachable` in health check | `docker logs rammy-python` to diagnose |
| Port already in use | `docker-compose down` then `docker-compose up` |
| `.env not found` error | Complete Step 2 in the setup instructions |
| Bot only gives out-of-scope replies | Run `qdrant_setup.py` — Qdrant collection is empty |
| Bot deflects after `docker restart rammy-python` | Restarting the container clears the Qdrant collection reference — always run `docker exec rammy-python python qdrant_setup.py` after any restart |
| Logs show `collection 'rammy_hr' not found` | Same as above — run `qdrant_setup.py` |
| `rammy_hr` collection not found | Same as above |
| MinIO console not loading | `docker logs rammy-minio` |
| PDFs not being indexed | Confirm bucket is named exactly `documents`, then re-run `qdrant_setup.py` |
| PDF link returns `Could not retrieve document` | Check `docker logs rammy-python` for MinIO errors |
| PDF filenames with colons failing | Rename the file in MinIO (remove the colon), then re-run `qdrant_setup.py` |
| Mac AirPlay conflict on port 5000 | Already handled — app uses port 5001 |
| `ModuleNotFoundError` | Always run scripts inside Docker: `docker exec rammy-python python <script>.py` |

---

## Useful Commands

```bash
# View logs for each service
docker logs rammy-python
docker logs rammy-node
docker logs rammy-qdrant
docker logs rammy-minio

# Open an interactive shell inside the Python container
docker exec -it rammy-python bash

# Hot-reload Python code without a full rebuild
# WARNING: always re-run qdrant_setup.py after this — the restart clears the collection reference
docker cp backend/chatbot_api.py rammy-python:/app/chatbot_api.py
docker restart rammy-python
docker exec rammy-python python qdrant_setup.py

# Force a full clean rebuild (wipes Qdrant and MinIO volumes)
docker-compose down -v
docker system prune -f
docker-compose up --build -d
docker exec rammy-python python qdrant_setup.py

# Check vector count in Qdrant
curl http://localhost:6333/collections/rammy_hr

# List all PDFs in MinIO
docker exec rammy-python python -c "
from minio import Minio
client = Minio('minio:9000', access_key='minioadmin', secret_key='minioadmin', secure=False)
for o in client.list_objects('documents'):
    print(repr(o.object_name))
"
```

---

## HR Source URLs

Rammy draws web knowledge from the following official pages. To add or remove sources, edit `SOURCE_URLS` in `backend/qdrant_setup.py` and re-run the script.

**WCU HR:** FAQs, Employee & Labor Relations, Student Employment, Professional Development, Why Work at WCU, Job Openings  
**Benefits & Leave:** Employee Benefits by Group, FMLA, PASSHE Life Events, Work-Related Injuries, Tuition Waiver  
**Retirement:** PASSHE Retirement (ARP, SERS, TSA, Deferred Compensation, Voluntary Plans), TIAA, Retirement@Work, SERS, PSERS, Empower, Fidelity  
**Other:** USCIS I-9, Payroll, Parking (Permits, Regulations, FAQs), WCU Academic Calendar  

PDF sources are managed separately via the MinIO console.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Vanilla JS, HTML/CSS |
| API Gateway | Node.js + Express |
| Chatbot Backend | Python + Flask |
| Vector Search | Qdrant + sentence-transformers (`all-MiniLM-L6-v2`) |
| LLM | OpenAI GPT-4.1-mini |
| PDF Storage | MinIO (S3-compatible) |
| Containerization | Docker + Docker Compose |

---

## Contributing

This project is developed as part of CSC402 at West Chester University. See `docs/Next_Steps.txt` for current development priorities.
