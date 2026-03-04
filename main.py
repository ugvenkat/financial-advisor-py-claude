"""
Financial Advisor API — Python/CrewAI port of the .NET application.
Same 8 REST endpoints, same request/response shapes.

Run with: uvicorn main:app --host 0.0.0.0 --port 8080 --reload
"""

from __future__ import annotations
import os
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from models import AnalysisRequest, JobStatus
from data.memory_store import MemoryStore
from services.report_writer import ReportWriter
from services.status_tracker import AgentStatusTracker
from services.orchestrator import MultiAgentOrchestrator

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("main")

# ── App state ─────────────────────────────────────────────────────────────────
memory:       MemoryStore
writer:       ReportWriter
tracker:      AgentStatusTracker
orchestrator: MultiAgentOrchestrator


@asynccontextmanager
async def lifespan(app: FastAPI):
    global memory, writer, tracker, orchestrator
    db_path    = os.getenv("DB_PATH",         "data/financial_advisor.db")
    report_dir = os.getenv("REPORTS_DIR",     "./reports")

    memory       = MemoryStore(db_path)
    writer       = ReportWriter(report_dir)
    tracker      = AgentStatusTracker()
    orchestrator = MultiAgentOrchestrator(memory, writer, tracker)

    await memory.initialize()
    log.info("Financial Advisor API ready - Anthropic model: %s",
             os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"))
    yield
    log.info("Shutting down.")


app = FastAPI(
    title       = "Financial Advisor - Multi-Agent AI",
    description = "5-agent CrewAI financial analysis pipeline powered by local Ollama",
    version     = "2.0.0",
    lifespan    = lifespan,
)

from fastapi import Request
from fastapi.responses import JSONResponse
import traceback

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    tb = traceback.format_exc()
    print(f"[ERROR] 500 on {request.url}:\n{tb}", flush=True)
    log.error("Unhandled exception: %s\n%s", exc, tb)
    return JSONResponse(status_code=500, content={"error": str(exc), "traceback": tb})


# ─────────────────────────────────────────────────────────────────────────────
#  ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/analysis", status_code=202)
async def start_analysis(req: AnalysisRequest):
    """Start a new 5-agent agentic analysis job."""
    if not req.tickers:
        raise HTTPException(400, detail={"code": "INVALID_REQUEST", "message": "At least one ticker required"})
    if len(req.tickers) > 10:
        raise HTTPException(400, detail={"code": "INVALID_REQUEST", "message": "Max 10 tickers per job"})

    job = await orchestrator.start_job(req)
    return {
        "job_id":          job.job_id,
        "status":          job.status,
        "tickers":         job.tickers,
        "created_at":      job.created_at,
        "status_url":      f"/api/analysis/{job.job_id}",
        "live_status_url": f"/api/analysis/{job.job_id}/live",
        "message":         f"5-agent agentic analysis started for: {', '.join(job.tickers)}",
    }


@app.get("/api/analysis/{job_id}")
async def get_job(job_id: str):
    """Poll job status and get full results."""
    job = await orchestrator.get_job(job_id)
    if not job:
        raise HTTPException(404, detail={"code": "JOB_NOT_FOUND", "message": f"Job '{job_id}' not found"})

    elapsed = (
        (job.completed_at - job.created_at).total_seconds()
        if job.completed_at else
        (datetime.utcnow() - job.created_at).total_seconds()
    )

    return {
        "job_id":        job.job_id,
        "status":        job.status,
        "tickers":       job.tickers,
        "created_at":    job.created_at,
        "completed_at":  job.completed_at,
        "duration_secs": round(elapsed, 1),
        "error_message": job.error_message,
        "failed_tickers": job.failed_tickers,
        "output_dir":    job.output_dir,
        "reports": [
            {
                "ticker":            r.ticker,
                "generated_at":      r.generated_at,
                "total_agent_steps": sum(t.total_steps for t in r.all_traces),
                "recommendation": {
                    "action":        r.recommendation.action,
                    "confidence":    r.recommendation.confidence,
                    "risk_level":    r.recommendation.risk_level,
                    "current_price": r.recommendation.current_price,
                    "price_target":  r.recommendation.price_target,
                    "upside_percent":r.recommendation.upside_percent,
                    "time_horizon":  r.recommendation.time_horizon,
                    "key_catalysts": r.recommendation.key_catalysts,
                    "key_risks":     r.recommendation.key_risks,
                    "cio_summary":   (r.recommendation.cio_summary or "")[:500],
                    "fundamental": {
                        "score":     r.recommendation.fundamental.score,
                        "grade":     r.recommendation.fundamental.grade,
                        "strengths": r.recommendation.fundamental.strengths,
                        "weaknesses":r.recommendation.fundamental.weaknesses,
                    },
                    "sentiment": {
                        "overall":          r.recommendation.sentiment.overall,
                        "score":            r.recommendation.sentiment.score,
                        "bullish_percent":  r.recommendation.sentiment.bullish_percent,
                        "bearish_percent":  r.recommendation.sentiment.bearish_percent,
                    },
                    "risk": {
                        "level":        r.recommendation.risk.level,
                        "score":        r.recommendation.risk.score,
                        "risk_factors": r.recommendation.risk.risk_factors,
                    },
                },
            }
            for r in job.reports
        ],
    }


@app.get("/api/analysis/{job_id}/live")
async def live_status(job_id: str):
    """Live debug - see exactly what each agent is doing right now."""
    job = await memory.get_job(job_id)
    if not job:
        raise HTTPException(404, detail={"code": "JOB_NOT_FOUND", "message": f"Job '{job_id}' not found"})

    status  = tracker.get(job_id)
    elapsed = round((datetime.utcnow() - job.created_at).total_seconds(), 1)

    active = None
    if status:
        active = sorted(
            [
                {
                    "ticker":         a.ticker,
                    "agent":          a.agent,
                    "step":           a.step,
                    "activity":       a.activity,
                    "completed":      a.completed,
                    "stuck_for_secs": round((datetime.utcnow() - a.updated_at).total_seconds(), 0),
                }
                for a in status.active_agents.values()
            ],
            key=lambda x: x["agent"],
        )

    return {
        "job_id":       job_id,
        "job_status":   job.status,
        "elapsed_secs": elapsed,
        "last_update":  status.last_update if status else None,
        "active_agents": active,
        "hint": (
            "No live data yet - job may not have started"
            if not status else
            f"Last activity {round((datetime.utcnow() - status.last_update).total_seconds(), 0):.0f}s ago"
        ),
    }


@app.get("/api/analysis/{job_id}/traces")
async def get_traces(job_id: str):
    """Get full agent reasoning traces."""
    job = await memory.get_job(job_id)
    if not job:
        raise HTTPException(404, detail={"code": "JOB_NOT_FOUND", "message": f"Job '{job_id}' not found"})

    traces = await memory.get_traces(job_id)

    from itertools import groupby
    grouped = {}
    for t in traces:
        grouped.setdefault(t["ticker"], []).append(t)

    return {
        "job_id":       job_id,
        "total_agents": len({t["agent_name"] for t in traces}),
        "total_steps":  sum(t["trace"].total_steps for t in traces),
        "traces": [
            {
                "ticker": ticker,
                "agents": [
                    {
                        "agent_name":  t["agent_name"],
                        "total_steps": t["trace"].total_steps,
                        "succeeded":   t["trace"].succeeded,
                        "final_answer": (t["trace"].final_answer or "")[:400],
                    }
                    for t in agent_list
                ],
            }
            for ticker, agent_list in grouped.items()
        ],
    }


@app.get("/api/analysis/{job_id}/report", response_class=PlainTextResponse)
async def get_report(job_id: str):
    """Download Markdown report."""
    job = await memory.get_job(job_id)
    if not job:
        raise HTTPException(404, detail={"code": "JOB_NOT_FOUND", "message": f"Job '{job_id}' not found"})
    if job.status != JobStatus.Completed:
        raise HTTPException(400, detail={"code": "JOB_NOT_COMPLETE", "message": f"Job is {job.status} - not ready yet"})

    path = os.path.join(job.output_dir or "", "report.md")
    if not os.path.exists(path):
        raise HTTPException(404, detail={"code": "REPORT_MISSING", "message": "Report file not found on disk"})

    with open(path, encoding="utf-8") as f:
        return f.read()


@app.get("/api/analysis")
async def list_jobs(limit: int = Query(default=10, le=50)):
    """List recent analysis jobs."""
    jobs = await orchestrator.get_recent_jobs(min(limit, 50))
    return [
        {
            "job_id":       j.job_id,
            "status":       j.status,
            "tickers":      j.tickers,
            "created_at":   j.created_at,
            "completed_at": j.completed_at,
            "reports":      len(j.reports),
            "output_dir":   j.output_dir,
        }
        for j in jobs
    ]


@app.get("/api/health")
async def health():
    """Health check."""
    return {
        "status":    "healthy",
        "timestamp": datetime.utcnow(),
        "framework": "CrewAI",
        "llm":       f"Anthropic / {os.getenv('ANTHROPIC_MODEL', 'claude-haiku-4-5-20251001')}",
        "pattern":   "ReAct (Reason - Act - Observe)",
        "agents": [
            "1 DataCollectionAgent",
            "2 FundamentalAnalysisAgent",
            "3 SentimentAnalysisAgent",
            "4 RiskAnalysisAgent",
            "5 CIOAgent",
        ],
    }
