# Rammy — Local Startup Guide

## Every time you want to run Rammy, open 3 terminal tabs in this order:

---
Start with Git Clone

### Tab 1 — Python Backend
```bash
cd ~/personal402
source venv/bin/activate
python chatbot_api.py
```
Wait until you see `Running on http://127.0.0.1:5000` before moving to Tab 2.

---

### Tab 2 — Node.js Server
```bash
cd ~/personal402
npm start
```
Wait until you see `Rammy Node.js API running on http://localhost:3000` before opening the frontend.

---

### Tab 3 — Frontend
```bash
open ~/personal402/index.html
```
Or right-click `index.html` in VS Code → **Open with Live Server**

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

## To Shut Down
Press `Ctrl + C` in Tab 1 and Tab 2.
