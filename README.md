# Rammy — Local Startup Guide
Start with Git clone
## First Time Setup (Do this once)
### 1. Install Python dependencies
```bash
cd ~/personal402
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Install Node.js dependencies
```bash
cd ~/personal402
npm install
```

### 3. Create your .env file and add your API key
```bash
cd ~/personal402
echo 'OPENAI_API_KEY=sk-your-actual-key-here
OPENAI_ORG_ID=
OPENAI_PROJECT_ID=' > .env
```
Then open it and replace `sk-your-actual-key-here` with your real OpenAI API key:
```bash
open .env
```
> ⚠️ Never share your `.env` file or commit it to GitHub. Your API key is private.

---

## Every Time You Want to Run Rammy, Open 3 Terminal Tabs in This Order:

---

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
