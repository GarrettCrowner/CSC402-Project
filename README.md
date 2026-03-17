# Rammy — WCU HR Chatbot

Rammy is an AI-powered HR chatbot for West Chester University. It answers HR-related questions using content sourced from official WCU and PASSHE HR pages, powered by OpenAI's GPT-4.1-mini.

---

## Architecture

```
Browser (HTML + chat.js)
        │
        ▼
Node.js Express Server  (port 3000)
        │
        ▼
Python Flask Service  (port 5001)
        │
        ▼
OpenAI API (gpt-4.1-mini)
```

---

## Prerequisites

Before you begin, make sure you have the following installed:
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [Git](https://git-scm.com/)
- An OpenAI API key — get one at [platform.openai.com](https://platform.openai.com)

---

## Setup

### 1. Clone the repository

```bash
git clone -b Garrett_Crowner https://github.com/GarrettCrowner/CSC402-Project.git
cd CSC402-Project
```

### 2. Create your .env file

```bash
echo 'OPENAI_API_KEY=sk-your-actual-key-here
OPENAI_ORG_ID=
OPENAI_PROJECT_ID=' > .env
```

Replace `sk-your-actual-key-here` with your real OpenAI API key, then save and close.

> ⚠️ Never share your `.env` file or commit it to GitHub. Your API key is private.

### 3. Start Docker Desktop

Open Docker Desktop and wait for the whale icon in your menu bar to stop animating before continuing.

---

## Running the App

**First time (or after any code changes):**
```bash
docker-compose up --build
```

**Every time after:**
```bash
docker-compose up
```

**Shut down:**
```bash
docker-compose down
```

---

## Opening the Frontend

Once the containers are running, open a new terminal tab and run:

```bash
cd ~/CSC402-project
open embed.html
```

Or open the project folder in VS Code, right-click `embed.html` and select **Open with Live Server**.

---

## Verify Everything is Connected

```bash
curl http://localhost:3000/api/health
```

Expected response:
```json
{ "status": "ok", "python": "reachable" }
```

---

## Common Issues

| Symptom | Fix |
|---|---|
| `Connection refused` on port 3000 | Make sure Docker Desktop is running, then `docker-compose up` |
| `python unreachable` in health check | Run `docker logs rammy-python` to see the error |
| Port already in use | Run `docker-compose down` then `docker-compose up` again |
| `.env not found` error | Make sure you completed Step 2 above |
| Mac AirPlay conflict on port 5000 | Already handled — app uses port 5001 |

---

## Useful Commands

```bash
# View logs for the Python backend
docker logs rammy-python

# View logs for the Node server
docker logs rammy-node

# Force a clean rebuild
docker-compose down
docker system prune -f
docker-compose up --build
```
