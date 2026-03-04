# Financial Advisor — Python / CrewAI

A 5-agent AI financial analysis system built with **CrewAI** and **Anthropic Claude API**.
This is the Python port of the original .NET application — same agents, same logic, same REST API.

---

## Architecture

```
POST /api/analysis  ->  Agent 1: Data Collection  (fetches all market data)
                              |
                    +---------+---------+
                    v         v         v
               Agent 2    Agent 3    Agent 4      <- run in PARALLEL
             Fundamental  Sentiment   Risk
             Analysis     Analysis    Analysis
                    +---------+---------+
                              v
                    Agent 5: CIO Decision
                    (synthesises everything -> Buy/Hold/Sell)
```

---

## How to Run (Step by Step)

### Step 1 — Install Python

You need Python 3.11 or newer.

- **Windows:** Download from https://www.python.org/downloads/ — check "Add Python to PATH" during install
- **Mac:** In Terminal: `brew install python@3.11`
- **Linux:** `sudo apt install python3.11 python3.11-venv`

Check it works:
```
python --version
```
You should see `Python 3.11.x` or higher.

---

### Step 2 — Get an Anthropic API Key

This project uses **Claude** (claude-haiku-4-5) via the Anthropic API — no local GPU required.

1. Sign up at https://console.anthropic.com
2. Go to **API Keys** and create a new key
3. Copy the key — you will need it in Step 4

---

### Step 3 — Set up the project

Open a Terminal / Git Bash in the project folder.

**Create a virtual environment:**
```bash
python -m venv venv
```

**Activate it:**
- Windows Git Bash: `source venv/Scripts/activate`
- Mac/Linux:        `source venv/bin/activate`

You should see `(venv)` at the start of your prompt.

**Install all dependencies:**
```bash
pip install -r requirements.txt
```

This takes 2-3 minutes. You only need to do this once.

---

### Step 4 — Configure your API key

Copy the example env file:
```bash
cp .env.example .env
```

Open `.env` and add your Anthropic API key:
```
ANTHROPIC_API_KEY=sk-ant-your-key-here
ANTHROPIC_MODEL=claude-haiku-4-5-20251001
DB_PATH=data/financial_advisor.db
REPORTS_DIR=./reports
```

---

### Step 5 — Run the API

**Important: Do NOT use --reload flag on Windows.**

```bash
PYTHONUTF8=1 python -m uvicorn main:app --host 0.0.0.0 --port 8080
```

You should see:
```
INFO  Financial Advisor API ready - Anthropic model: claude-haiku-4-5-20251001
INFO  Uvicorn running on http://0.0.0.0:8080
```

The API is now running! Keep this terminal open.

---

### Step 6 — Run an analysis

Open a **new** Terminal window and run:

**Analyze a single stock (e.g. Apple):**
```bash
curl -X POST http://localhost:8080/api/analysis \
  -H "Content-Type: application/json" \
  -d "{\"tickers\": [\"AAPL\"]}"
```

You will get back a job ID like:
```json
{
  "job_id": "A1B2C3D4",
  "status": "Queued",
  "message": "5-agent agentic analysis started for: AAPL"
}
```

**Check progress (poll every 10-15 seconds):**
```bash
curl http://localhost:8080/api/analysis/A1B2C3D4
```

**Watch agents working live:**
```bash
curl http://localhost:8080/api/analysis/A1B2C3D4/live
```

**Get the final report (once status = "Completed"):**
```bash
curl http://localhost:8080/api/analysis/A1B2C3D4/report
```

**Analyze multiple stocks:**
```bash
curl -X POST http://localhost:8080/api/analysis \
  -H "Content-Type: application/json" \
  -d "{\"tickers\": [\"AAPL\", \"MSFT\", \"NVDA\"]}"
```

A single stock analysis typically completes in **45-90 seconds** with Claude API.

---

### Step 7 — View reports

All reports are saved automatically to the `reports/` folder.

Each job creates:
- `reports/{JOB_ID}/report.json`            — full data in JSON
- `reports/{JOB_ID}/report.md`              — portfolio summary in Markdown
- `reports/{JOB_ID}/AAPL.md`               — individual stock report
- `reports/{JOB_ID}/AAPL_agent_traces.md`  — how each agent reasoned

Open the `.md` files in VS Code, Obsidian, or any Markdown viewer.

---

## Configuration

Edit the `.env` file to change settings:

```
ANTHROPIC_API_KEY=sk-ant-your-key-here    # your Anthropic API key
ANTHROPIC_MODEL=claude-haiku-4-5-20251001 # Claude model to use
DB_PATH=data/financial_advisor.db         # where the database is stored
REPORTS_DIR=./reports                     # where reports are saved
```

**To use a more powerful model**, change `ANTHROPIC_MODEL` in `.env`:
```
ANTHROPIC_MODEL=claude-sonnet-4-20250514
```
Note: More powerful models cost more API credits and may be slower.

---

## API Reference

| Method | URL | What it does |
|--------|-----|--------------|
| POST | /api/analysis | Start a new analysis job |
| GET  | /api/analysis/{jobId} | Get job status + results |
| GET  | /api/analysis/{jobId}/live | Watch agents in real time |
| GET  | /api/analysis/{jobId}/traces | See agent reasoning traces |
| GET  | /api/analysis/{jobId}/report | Download Markdown report |
| GET  | /api/analysis | List recent jobs |
| GET  | /api/health | Health check |

Interactive API docs: http://localhost:8080/docs (Swagger UI)

---

## Troubleshooting

**500 Internal Server Error on POST**
- Make sure you started uvicorn WITHOUT --reload flag
- Check that your .env file exists and has a valid ANTHROPIC_API_KEY

**Connection refused when calling the API**
- The uvicorn server is not running. Start it with the command in Step 5.

**Port already in use**
- Another process is using port 8080. Kill it first:
  Windows: `netstat -ano | grep 8080` then `taskkill /F /PID <number>`

**Analysis is slow or times out**
- Claude API has rate limits on new accounts (50,000 tokens/minute).
  If you hit limits, wait 60 seconds and retry.

**ModuleNotFoundError**
- Make sure your virtual environment is activated (`source venv/Scripts/activate`)
  and that you ran `pip install -r requirements.txt`.

**Job stays in Queued status**
- Stop the server (Ctrl+C) and restart WITHOUT --reload flag.

---

## Dependencies

| Package | Purpose |
|---------|---------|
| crewai | Multi-agent AI framework |
| anthropic | Anthropic Claude API client |
| fastapi | REST API framework |
| uvicorn | ASGI web server |
| requests | HTTP calls to Yahoo Finance |
| beautifulsoup4 | HTML parsing for MarketWatch news |
| aiosqlite | Async SQLite database |
| pydantic | Data models and validation |
| python-dotenv | Load .env config file |

---

> **Not financial advice.** This tool is for educational and research purposes only.
