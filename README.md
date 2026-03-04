# 📊 Financial Advisor — Python / CrewAI

A 5-agent AI financial analysis system built with **CrewAI** and **Ollama** (local LLM).
This is the Python port of the original .NET application — same agents, same logic, same REST API.

---

## 🏗️ Architecture

```
POST /api/analysis  ─►  Agent 1: Data Collection  (fetches all market data)
                              │
                    ┌─────────┴──────────┐
                    ▼         ▼          ▼
               Agent 2    Agent 3    Agent 4      ← run in PARALLEL
             Fundamental  Sentiment   Risk
             Analysis     Analysis    Analysis
                    └─────────┬──────────┘
                              ▼
                    Agent 5: CIO Decision
                    (synthesises everything → Buy/Hold/Sell)
```

---

## 🚀 How to Run (Step by Step)

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

### Step 2 — Install Ollama and pull the model

Ollama runs the AI model on your own computer.

1. Download Ollama from https://ollama.com/download
2. Install and open it (it runs as a background service)
3. Open a Terminal / Command Prompt and run:

```bash
ollama pull llama3.1:8b
```

This downloads the AI model (~4.7 GB). Wait for it to finish.

Test it works:
```bash
ollama run llama3.1:8b "Say hello"
```

---

### Step 3 — Set up the project

Open a Terminal / Command Prompt in the `financial_advisor_py` folder.

**Create a virtual environment** (keeps this project's packages separate):
```bash
python -m venv venv
```

**Activate it:**
- Windows:   `venv\Scripts\activate`
- Mac/Linux: `source venv/bin/activate`

You should see `(venv)` at the start of your prompt.

**Install all dependencies:**
```bash
pip install -r requirements.txt
```

This takes 2–3 minutes. You only need to do this once.

---

### Step 4 — Run the API

Make sure Ollama is running (it should be running in the background after install).

Start the API:
```bash
uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

You should see:
```
INFO  ✅ Financial Advisor API ready — Ollama model: llama3.1:8b
INFO  Uvicorn running on http://0.0.0.0:8080
```

The API is now running! Keep this terminal open.

---

### Step 5 — Run an analysis

Open a **new** Terminal window and run:

**Analyze a single stock (e.g. Apple):**
```bash
curl -X POST http://localhost:8080/api/analysis \
  -H "Content-Type: application/json" \
  -d '{"tickers": ["AAPL"]}'
```

You'll get back a job ID like:
```json
{
  "job_id": "A1B2C3D4",
  "status": "Queued",
  "message": "5-agent agentic analysis started for: AAPL"
}
```

**Check progress:**
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
  -d '{"tickers": ["AAPL", "MSFT", "NVDA"]}'
```

---

### Step 6 — View reports

All reports are saved automatically to the `reports/` folder.

Each job creates:
- `reports/{JOB_ID}/report.json`       — full data in JSON
- `reports/{JOB_ID}/report.md`         — portfolio summary in Markdown
- `reports/{JOB_ID}/AAPL.md`           — individual stock report
- `reports/{JOB_ID}/AAPL_agent_traces.md` — how each agent reasoned

Open the `.md` files in VS Code, Obsidian, or any Markdown viewer.

---

## ⚙️ Configuration

Edit the `.env` file to change settings:

```
OLLAMA_BASE_URL=http://localhost:11434   # where Ollama is running
OLLAMA_MODEL=llama3.1:8b                # which model to use
DB_PATH=data/financial_advisor.db       # where the database is stored
REPORTS_DIR=./reports                   # where reports are saved
```

**To use a different (more powerful) model:**
```bash
ollama pull llama3.3:70b
```
Then change `OLLAMA_MODEL=llama3.3:70b` in `.env`.

---

## 🌐 API Reference

| Method | URL | What it does |
|--------|-----|--------------|
| `POST` | `/api/analysis` | Start a new analysis job |
| `GET`  | `/api/analysis/{jobId}` | Get job status + results |
| `GET`  | `/api/analysis/{jobId}/live` | Watch agents in real time |
| `GET`  | `/api/analysis/{jobId}/traces` | See agent reasoning traces |
| `GET`  | `/api/analysis/{jobId}/report` | Download Markdown report |
| `GET`  | `/api/analysis` | List recent jobs |
| `GET`  | `/api/health` | Health check |

Interactive API docs: http://localhost:8080/docs (Swagger UI)

---

## ❓ Troubleshooting

**`ollama: command not found`**
→ Ollama is not installed or not in your PATH. Reinstall from https://ollama.com/download

**`Connection refused` when calling the API**
→ The `uvicorn` server is not running. Start it with the command in Step 4.

**Analysis is very slow**
→ The AI model runs on your CPU by default. A single stock analysis takes 5–15 minutes on CPU.
  If you have an NVIDIA GPU, Ollama uses it automatically (much faster).

**`ModuleNotFoundError`**
→ Make sure your virtual environment is activated (`source venv/bin/activate` or `venv\Scripts\activate`)
  and that you ran `pip install -r requirements.txt`.

**Analysis stuck / no output**
→ Check the terminal where `uvicorn` is running — you'll see detailed logs of what each agent is doing.

---

## 📦 Dependencies

| Package | Purpose |
|---------|---------|
| `crewai` | Multi-agent AI framework |
| `fastapi` | REST API framework |
| `uvicorn` | ASGI web server |
| `requests` | HTTP calls to Yahoo Finance |
| `beautifulsoup4` | HTML parsing for MarketWatch news |
| `aiosqlite` | Async SQLite database |
| `pydantic` | Data models and validation |
| `python-dotenv` | Load `.env` config file |

---

> ⚠️ **Not financial advice.** This tool is for educational and research purposes only.
