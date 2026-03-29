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
| `docker-compose.yml` | Orchestrates all three services |
| `Dockerfile.python` | Python service container |
| `Dockerfile.node` | Node.js service container |

---

## Prerequisites

Before you begin, make sure you have the following installed:

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

This starts three containers: `rammy-qdrant`, `rammy-python`, and `rammy-node`.

### 5. Populate the vector database

This step fetches all 22 WCU/PASSHE HR source pages, chunks them, embeds them, and uploads them to Qdrant. It only needs to be run once (or whenever the source URLs change).

```bash
docker exec rammy-python python qdrant_setup.py
```

You will see each source URL processed and a final confirmation:

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

**After the first-time setup, every subsequent run is just:**

```bash
docker-compose up
```

**Shut down:**

```bash
docker-compose down
```

> The Qdrant vector data persists in a Docker named volume (`qdrant_storage`) across restarts, so you do **not** need to re-run `qdrant_setup.py` each time.

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

If the WCU HR source pages are updated and you want to re-index them, run the setup script again while the containers are running:

```bash
docker exec rammy-python python qdrant_setup.py
```

This will delete and recreate the Qdrant collection with fresh data. You can also trigger a reconnect (without re-indexing) from inside the chat window using the ⋮ menu → **Refresh HR sources**, or via:

```bash
curl -X POST http://localhost:3000/api/refresh
```

---

## Common Issues

| Symptom | Fix |
|---|---|
| `Connection refused` on port 3000 | Make sure Docker Desktop is running, then `docker-compose up` |
| `python unreachable` in health check | Run `docker logs rammy-python` to see the error |
| Port already in use | Run `docker-compose down` then `docker-compose up` again |
| `.env not found` error | Make sure you completed Step 2 above |
| Bot only gives out-of-scope replies | Run `docker exec rammy-python python qdrant_setup.py` — the vector DB is empty |
| `rammy_hr` collection not found warning | Same as above — Qdrant needs to be populated first |
| Mac AirPlay conflict on port 5000 | Already handled — app uses port 5001 |

---

## Useful Commands

```bash
# View logs for each service
docker logs rammy-python
docker logs rammy-node
docker logs rammy-qdrant

# Run an interactive shell inside the Python container
docker exec -it rammy-python bash

# Force a clean rebuild (also wipes the Qdrant volume)
docker-compose down -v
docker system prune -f
docker-compose up --build -d
docker exec rammy-python python qdrant_setup.py

# Check how many vectors are in Qdrant
curl http://localhost:6333/collections/rammy_hr
```

---

## Source URLs

Rammy draws its knowledge from the following official pages. To add or remove sources, edit the `SOURCE_URLS` list in `qdrant_setup.py` and re-run it.

- WCU HR FAQs
- WCU Employee & Labor Relations
- WCU Student Employment
- WCU Professional Development
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
