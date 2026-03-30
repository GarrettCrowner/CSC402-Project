# Rammy — WCU HR Chatbot

Rammy is an AI-powered HR chatbot for West Chester University. It answers HR-related questions using content sourced from official WCU and PASSHE HR pages, retrieved via semantic vector search and answered by OpenAI's GPT-4.1-mini.

---

## Architecture

```
Browser (embed.html + chat.js)
        │
        ▼
Node.js Express Server  (port 3000)
  Rate limiting · CORS · input validation · proxy
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
  ├── 22 WCU/PASSHE web sources
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
| `chat.js` | Frontend chat widget — message rendering, quick-reply chips, API calls |
| `embed.html` | WCU HR page with the chatbot embedded |
| `styling.css` | Scoped styles for the chat widget |
| `server.js` | Node.js API gateway |
| `chatbot_api.py` | Python Flask backend — all chatbot logic |
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
OPENAI_PROJECT_ID=' > .env
```

Replace `sk-your-actual-key-here` with your real OpenAI API key.

> ⚠️ Never share your `.env` file or commit it to GitHub. Your API key is private.

### 3. Start Docker Desktop

Open Docker Desktop and wait for the whale icon in your menu bar to stop animating.

### 4. Build and start all services

```bash
docker-compose up --build -d
```

> ⏱️ **The first build takes 15–25 minutes.** This is expected — Docker is downloading and installing large machine learning dependencies including PyTorch (~800MB) and sentence-transformers. Subsequent startups with `docker-compose up` (no `--build`) take under 30 seconds because Docker caches the install layer.

### 5. Populate the vector database

This fetches all 22 WCU/PASSHE HR source pages, chunks and embeds them, and uploads them to Qdrant. Run this once after the first build, and again whenever sources change.

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

> The Qdrant and MinIO data both persist in named Docker volumes across restarts — you do **not** need to re-run `qdrant_setup.py` each time.

---

## MinIO — PDF Document Storage

MinIO is an S3-compatible object storage server included in the stack. It allows HR staff to upload PDF documents (handbooks, contracts, benefit guides, etc.) so Rammy can answer questions from them.

> 📭 **No PDFs have been uploaded yet.** Rammy currently draws its knowledge exclusively from the 22 web sources listed below. To extend Rammy's knowledge with PDF documents, follow the steps below.

### Uploading PDFs

1. Open the MinIO web console: [http://localhost:9001](http://localhost:9001)
2. Login: `minioadmin` / `minioadmin`
3. Create a bucket named exactly `documents` (first time only)
4. Click into the bucket → **Upload** → **Upload Files** → select your PDFs
5. Re-run the setup script to index the new documents:

```bash
docker exec rammy-python python qdrant_setup.py
```

Rammy will now answer questions from both the web sources and any uploaded PDFs. Repeat steps 4–5 whenever new documents are added — no code changes needed.

### Verifying MinIO is running

```bash
# Health check
curl http://localhost:9000/minio/health/live

# View logs
docker logs rammy-minio
```

A `200 OK` response from the health check confirms MinIO is operational.

---

## Verify Everything is Connected

```bash
curl http://localhost:3000/api/health
```

Expected response:

```json
{ "status": "ok", "python": "reachable" }
```

You can also check the Qdrant dashboard at [http://localhost:6333/dashboard](http://localhost:6333/dashboard) to confirm the `rammy_hr` collection exists and has points.

---

## Refreshing HR Sources

To re-index web sources and any PDFs in MinIO:

```bash
docker exec rammy-python python qdrant_setup.py
```

You can also trigger a quick reconnect (without re-indexing) from inside the chat window using the ⋮ menu → **Refresh HR sources**, or via:

```bash
curl -X POST http://localhost:3000/api/refresh
```

---

## Common Issues

| Symptom | Fix |
|---|---|
| First build is taking 15–25 minutes | This is normal — PyTorch and ML dependencies are large. Let it finish. |
| `Connection refused` on port 3000 | Make sure Docker Desktop is running, then `docker-compose up` |
| `python unreachable` in health check | Run `docker logs rammy-python` to see the error |
| Port already in use | Run `docker-compose down` then `docker-compose up` again |
| `.env not found` error | Make sure you completed Step 2 above |
| Bot only gives out-of-scope replies | Run `docker exec rammy-python python qdrant_setup.py` — Qdrant is empty |
| `rammy_hr` collection not found | Same as above — Qdrant needs to be populated first |
| MinIO console not loading | Run `docker logs rammy-minio` — confirm it started on port 9001 |
| PDFs not being indexed | Make sure they are in a bucket named exactly `documents`, then re-run `qdrant_setup.py` |
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

PDF sources are managed separately via the MinIO console — see the MinIO section above.
