# 🤖 Browser Agent — Setup Guide

## Quick Start (Windows)

### 1. Install dependencies (once)

Open **cmd.exe** (not PowerShell) and run:

```cmd
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
npm install -g @modelcontextprotocol/server-puppeteer
```

> ⚠️ If npm fails in PowerShell with "execution policy" error, use **cmd.exe** instead.

### 2. Set your API key

Open `.env` and paste your key:
```
ANTHROPIC_API_KEY=sk-ant-YOUR_KEY_HERE
```
Get your key at: https://console.anthropic.com → API Keys

### 3. Start

Double-click **`start.bat`** — or via cmd:

```cmd
venv\Scripts\activate
uvicorn server:app --reload --port 8000
```

### 4. Open in browser

http://localhost:8000

---

## Accounts

| Login  | Password | Role          | Access                        |
|--------|----------|---------------|-------------------------------|
| admin  | admin123 | Administrator | All tasks, all users          |
| alice  | alice123 | User          | Own tasks only                |
| bob    | bob123   | User          | Own tasks only                |

---

## Project Structure

```
browser-agent/
├── server.py           # FastAPI server (entry point)
├── agent_core.py       # ReAct agent + Claude
├── database.py         # SQLite DB (users, tasks)
├── requirements.txt    # Python dependencies
├── .env                # API key
├── start.bat           # One-click start (Windows)
├── data/
│   └── agent.db        # Database (auto-created)
├── static/
│   └── index.html      # Web dashboard
├── tools/
│   ├── browser_tools.py # Browser control
│   └── dom_subagent.py  # AI element finder
├── utils/
│   ├── mcp_client.py    # MCP/Puppeteer client
│   └── logger.py        # Logger + WebSocket
└── config/
    └── system_prompts.py # Agent prompts
```

---

## Troubleshooting

### `npm` fails with "execution policy" error
Use **cmd.exe** instead of PowerShell, or run in PowerShell as admin:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### `MCP connection failed`
```cmd
node --version          # must be 18+
npm install -g @modelcontextprotocol/server-puppeteer
npx puppeteer browsers install chrome
```

### Port 8000 already in use
```cmd
uvicorn server:app --port 8001
```
Then open http://localhost:8001

### `ANTHROPIC_API_KEY not found`
Make sure the `.env` file exists in the project root and contains the correct key.

---

## How It Works

1. You enter a task in the web dashboard
2. FastAPI creates a record in SQLite and starts the agent in background
3. Agent (Claude Sonnet) runs the ReAct loop:
   - **THINK** → analyzes the task and page state
   - **ACT** → calls a browser tool (via MCP/Puppeteer)
   - **OBS** → observes the result
   - Repeats until task is complete (max 20 steps)
4. Each step is streamed via WebSocket in real time
5. Result is saved to DB and visible in task history
