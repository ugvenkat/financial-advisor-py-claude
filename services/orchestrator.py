"""
Orchestrator — mirrors MultiAgentOrchestrator.cs.
Agent 1 runs first, Agents 2/3/4 run in parallel (asyncio.gather),
Agent 5 synthesises everything.
"""

from __future__ import annotations
import asyncio
import json
import re
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from crewai import Agent, Task, Crew, Process

from models import (
    AnalysisJob, AnalysisRequest, JobStatus, StockReport, StockRawData,
    PortfolioReport, FinancialMetrics, NewsArticle, AnalystRating,
    FundamentalScore, SentimentScore, SentimentClass, RiskScore, RiskLevel,
    InvestmentRecommendation, InvestmentAction, AgentTrace, AgentStep,
)
from agents.crew_agents import (
    data_collection_agent, fundamental_analysis_agent, sentiment_analysis_agent,
    risk_analysis_agent, cio_agent,
    make_data_task, make_fundamental_task, make_sentiment_task,
    make_risk_task, make_cio_task,
)
from data.memory_store import MemoryStore
from services.report_writer import ReportWriter
from services.status_tracker import AgentStatusTracker

log = logging.getLogger("orchestrator")

def _safe_float(val, default=0.0) -> float:
    """Safely convert value to float, returning default if not possible."""
    try:
        return float(val) if val is not None else default
    except (ValueError, TypeError):
        return default

# Thread pool for running CrewAI (blocking) tasks inside async context
_POOL = ThreadPoolExecutor(max_workers=8)

COMPANY_NAMES = {
    "AAPL": "Apple Inc.",        "MSFT": "Microsoft Corporation",
    "GOOGL": "Alphabet Inc.",    "AMZN": "Amazon.com Inc.",
    "NVDA": "NVIDIA Corporation","META": "Meta Platforms Inc.",
    "TSLA": "Tesla Inc.",        "JPM":  "JPMorgan Chase & Co.",
    "V":    "Visa Inc.",         "JNJ":  "Johnson & Johnson",
    "WMT":  "Walmart Inc.",      "XOM":  "ExxonMobil Corporation",
    "NFLX": "Netflix Inc.",      "INTC": "Intel Corporation",
    "DIS":  "Walt Disney Company",
}


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS — parse agent output text → domain models
# ─────────────────────────────────────────────────────────────────────────────

def _extract_json(text: str) -> dict:
    """Extract first JSON object from arbitrary LLM output text."""
    text = text.strip()
    # Strip markdown fences
    text = re.sub(r"```(?:json)?", "", text).strip()
    # Find outermost { }
    start = text.find("{")
    end   = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            pass
    return {}


def _grade_from_score(score: float) -> str:
    if score >= 85: return "A"
    if score >= 70: return "B"
    if score >= 55: return "C"
    if score >= 40: return "D"
    return "F"


def _risk_level_from_score(score: float) -> RiskLevel:
    if score >= 70: return RiskLevel.VeryHigh
    if score >= 55: return RiskLevel.High
    if score >= 35: return RiskLevel.Medium
    return RiskLevel.Low


def _parse_raw_data(ticker: str, output: str) -> StockRawData:
    data = StockRawData(
        ticker=ticker.upper(),
        company_name=COMPANY_NAMES.get(ticker.upper(), f"{ticker.upper()} Corp."),
    )
    obj = _extract_json(output)
    if not obj:
        return data
    m = data.metrics
    m.current_price       = obj.get("current_price")
    m.pe_ratio            = obj.get("pe_ratio")
    m.market_cap          = obj.get("market_cap")
    m.beta                = obj.get("beta")
    m.eps                 = obj.get("eps")
    m.pb_ratio            = obj.get("pb_ratio")
    m.debt_to_equity      = obj.get("debt_to_equity")
    m.free_cash_flow      = obj.get("free_cash_flow")
    m.fifty_two_week_high = obj.get("52w_high")
    m.fifty_two_week_low  = obj.get("52w_low")
    m.revenue_growth_yoy  = obj.get("revenue_growth")
    m.eps_growth_yoy      = obj.get("eps_growth")
    m.sector              = obj.get("sector", "")

    for n in (obj.get("news") or []):
        if isinstance(n, dict):
            data.news.append(NewsArticle(title=n.get("title",""), source=n.get("source","Yahoo Finance")))
        elif isinstance(n, str):
            data.news.append(NewsArticle(title=n, source="Yahoo Finance"))

    # If no structured news, pull headlines from text
    if not data.news:
        for line in output.split("\n"):
            line = line.strip().lstrip("-•* ")
            if len(line) > 20:
                data.news.append(NewsArticle(title=line, source="Extracted"))
            if len(data.news) >= 10:
                break

    ratings_raw = obj.get("analyst_ratings") or {}
    if isinstance(ratings_raw, dict):
        for rating_type in ("strong_buy", "buy", "hold", "sell", "strong_sell"):
            count = ratings_raw.get(rating_type, 0) or 0
            for _ in range(int(count)):
                data.analyst_ratings.append(AnalystRating(rating=rating_type.replace("_", " ").title()))

    return data


def _parse_fundamental(ticker: str, output: str) -> FundamentalScore:
    score = FundamentalScore(ticker=ticker, detailed_analysis=output)
    obj   = _extract_json(output)
    if obj:
        score.score     = _safe_float(obj.get("score", 50))
        score.grade     = obj.get("grade") or _grade_from_score(score.score)
        score.strengths = obj.get("strengths", [])
        score.weaknesses= obj.get("weaknesses", [])
        if obj.get("detailed_analysis"):
            score.detailed_analysis = obj["detailed_analysis"]
    else:
        # Text fallback
        m = re.search(r"score[:\s]+(\d+(?:\.\d+)?)", output, re.I)
        score.score = float(m.group(1)) if m else 50.0
        m2 = re.search(r"grade[:\s]+([A-F][+-]?)", output, re.I)
        score.grade = m2.group(1).upper() if m2 else _grade_from_score(score.score)
    return score


def _parse_sentiment(ticker: str, output: str) -> SentimentScore:
    score = SentimentScore(ticker=ticker, sentiment_summary=output)
    obj   = _extract_json(output)
    if obj:
        raw = _safe_float(obj.get("score", obj.get("sentiment_score", 0)))
        score.score           = raw
        score.bullish_percent = _safe_float(obj.get("bullish_pct", obj.get("bullish_percent", 0)))
        score.bearish_percent = _safe_float(obj.get("bearish_pct", obj.get("bearish_percent", 0)))
        score.neutral_percent = _safe_float(obj.get("neutral_pct", obj.get("neutral_percent", 0)))
        overall_str = (obj.get("overall") or obj.get("overall_sentiment") or "").lower()
        if "bullish" in overall_str or raw > 0.2:
            score.overall = SentimentClass.Bullish
        elif "bearish" in overall_str or raw < -0.2:
            score.overall = SentimentClass.Bearish
        else:
            score.overall = SentimentClass.Neutral
    else:
        lower = output.lower()
        score.score   = 0.35 if "bullish" in lower else (-0.35 if "bearish" in lower else 0)
        score.overall = (SentimentClass.Bullish if score.score > 0.2
                         else SentimentClass.Bearish if score.score < -0.2
                         else SentimentClass.Neutral)
    return score


def _parse_risk(ticker: str, output: str) -> RiskScore:
    risk = RiskScore(ticker=ticker, risk_summary=output)
    obj  = _extract_json(output)
    if obj:
        risk.score   = _safe_float(obj.get("risk_score", obj.get("score", 50)))
        level_str    = (obj.get("risk_level") or "").lower()
        if "veryhigh" in level_str or "very" in level_str:
            risk.level = RiskLevel.VeryHigh
        elif "high" in level_str:
            risk.level = RiskLevel.High
        elif "medium" in level_str or "moderate" in level_str:
            risk.level = RiskLevel.Medium
        elif "low" in level_str:
            risk.level = RiskLevel.Low
        else:
            risk.level = _risk_level_from_score(risk.score)
        risk.risk_factors = obj.get("risk_factors", [])
    else:
        m = re.search(r"risk score[:\s]+(\d+(?:\.\d+)?)", output, re.I)
        risk.score = float(m.group(1)) if m else 50.0
        risk.level = _risk_level_from_score(risk.score)
    return risk


def _parse_recommendation(
    raw: StockRawData,
    fundamental: FundamentalScore,
    sentiment: SentimentScore,
    risk: RiskScore,
    output: str,
) -> InvestmentRecommendation:
    rec = InvestmentRecommendation(
        ticker       = raw.ticker,
        company_name = raw.company_name,
        current_price= raw.metrics.current_price,
        fundamental  = fundamental,
        sentiment    = sentiment,
        risk         = risk,
        risk_level   = risk.level,
        cio_summary  = output,
    )
    obj = _extract_json(output)
    if obj:
        action_str = obj.get("action", "Hold")
        try:
            rec.action = InvestmentAction(action_str)
        except ValueError:
            rec.action = InvestmentAction.Hold

        rec.confidence   = _safe_float(obj.get("confidence", 60))
        rec.price_target = obj.get("price_target") or obj.get("target")
        rec.time_horizon = obj.get("time_horizon", "6-12 months")
        rec.key_catalysts= obj.get("catalysts", obj.get("key_catalysts", []))
        rec.key_risks    = obj.get("risks", obj.get("key_risks", []))
        rec.rationale    = obj.get("rationale", obj.get("memo", ""))
    else:
        # Text fallbacks
        for action in ("StrongBuy","StrongSell","Buy","Sell","Hold"):
            if action.lower() in output.lower():
                try:
                    rec.action = InvestmentAction(action); break
                except ValueError:
                    pass
        m = re.search(r"confidence[:\s]+(\d+)", output, re.I)
        rec.confidence = float(m.group(1)) if m else 60.0
        m2 = re.search(r"(?:price target|target)[:\s]+\$?(\d+(?:\.\d+)?)", output, re.I)
        if m2:
            rec.price_target = float(m2.group(1))

    # Compute upside
    if rec.current_price and rec.price_target and rec.current_price > 0:
        rec.upside_percent = (rec.price_target - rec.current_price) / rec.current_price * 100

    return rec


def _run_single_agent_crew(agent: Agent, task: Task) -> str:
    """Run a single-agent crew synchronously and return the output string."""
    crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=True)
    result = crew.kickoff()
    return str(result)


# ─────────────────────────────────────────────────────────────────────────────
#  ORCHESTRATOR
# ─────────────────────────────────────────────────────────────────────────────

class MultiAgentOrchestrator:
    def __init__(self, memory: MemoryStore, writer: ReportWriter, tracker: AgentStatusTracker):
        self.memory  = memory
        self.writer  = writer
        self.tracker = tracker

    async def start_job(self, request: AnalysisRequest) -> AnalysisJob:
        job = AnalysisJob(
            tickers=[t.strip().upper() for t in dict.fromkeys(request.tickers)]
        )
        await self.memory.save_job(job)
        log.info("Job %s queued: %s", job.job_id, job.tickers)
        # Schedule as background task on current event loop
        print(f"[START_JOB] Scheduling job {job.job_id} for {job.tickers}", flush=True)
        asyncio.ensure_future(self._run_job(job, request))
        print(f"[START_JOB] Task created for {job.job_id}", flush=True)
        return job

    async def get_job(self, job_id: str) -> AnalysisJob | None:
        return await self.memory.get_job(job_id)

    async def get_recent_jobs(self, limit: int = 10) -> list[AnalysisJob]:
        return await self.memory.get_recent_jobs(limit)

    async def _run_job(self, job: AnalysisJob, request: AnalysisRequest):
        print(f"[JOB] Started {job.job_id} for {job.tickers}", flush=True)
        job.status = JobStatus.Running
        await self.memory.save_job(job)
        try:
            portfolio = PortfolioReport(job_id=job.job_id)
            for ticker in job.tickers:
                try:
                    report = await self._process_ticker(job.job_id, ticker)
                    job.reports.append(report)
                    portfolio.stock_reports.append(report)
                    await self.memory.save_report(job.job_id, report)
                except Exception as e:
                    log.error("Failed ticker %s: %s", ticker, e)
                    job.failed_tickers[ticker] = str(e)
                    await self.memory.save_job(job)

            portfolio.executive_summary = _build_summary(portfolio, job.failed_tickers)
            job.output_dir   = await self.writer.write_report(job.job_id, portfolio)
            job.status       = JobStatus.Completed
            job.completed_at = datetime.utcnow()
            log.info("Job %s COMPLETE: %s", job.job_id, job.output_dir)
        except Exception as e:
            job.status        = JobStatus.Failed
            job.error_message = str(e)
            log.error("Job %s FAILED: %s", job.job_id, e)

        await self.memory.save_job(job)
        self.tracker.clear(job.job_id)

    async def _process_ticker(self, job_id: str, ticker: str) -> StockReport:
        print(f"[PIPELINE] Starting {ticker} - Agent 1 DataCollection", flush=True)
        log.info("[PIPELINE] Start: %s", ticker)
        loop = asyncio.get_event_loop()

        # ── Agent 1: Data Collection ──────────────────────────────────────────
        self.tracker.update(job_id, ticker, "DataCollectionAgent", 0, "Collecting data...")
        data_agent = data_collection_agent()
        data_task  = make_data_task(ticker, data_agent)

        data_output = await loop.run_in_executor(
            _POOL, _run_single_agent_crew, data_agent, data_task
        )
        raw_data = _parse_raw_data(ticker, data_output)
        data_trace = AgentTrace(agent_name="DataCollectionAgent", ticker=ticker,
                                goal=data_task.description, final_answer=data_output, succeeded=True)
        await self.memory.save_trace(job_id, ticker, "DataCollectionAgent", data_trace)
        self.tracker.complete(job_id, ticker, "DataCollectionAgent", "Data collected")
        print(f"[PIPELINE] {ticker} - Agent 1 DONE", flush=True)
        log.info("  [DONE] Agent1 DataCollection")

        # Build context strings for analysis agents
        m = raw_data.metrics
        metrics_ctx = (
            f"Ticker: {ticker}\n"
            f"Price: ${m.current_price or 'N/A'}  P/E: {m.pe_ratio or 'N/A'}  "
            f"Beta: {m.beta or 'N/A'}  Market Cap: {m.market_cap or 'N/A'}\n"
            f"P/B: {m.pb_ratio or 'N/A'}  D/E: {m.debt_to_equity or 'N/A'}  "
            f"FCF: {m.free_cash_flow or 'N/A'}  Sector: {m.sector or 'N/A'}\n"
            f"52W High: {m.fifty_two_week_high or 'N/A'}  "
            f"52W Low: {m.fifty_two_week_low or 'N/A'}\n"
            f"EPS Growth: {m.eps_growth_yoy or 'N/A'}  Revenue Growth: {m.revenue_growth_yoy or 'N/A'}"
        )
        headlines_ctx = "\n".join(f"- {n.title}" for n in raw_data.news[:8]) or "No headlines available"

        # ── Agents 2/3/4: Run in parallel ────────────────────────────────────
        self.tracker.update(job_id, ticker, "FundamentalAnalysisAgent", 0, "Analyzing fundamentals...")
        self.tracker.update(job_id, ticker, "SentimentAnalysisAgent",   0, "Analyzing sentiment...")
        self.tracker.update(job_id, ticker, "RiskAnalysisAgent",        0, "Analyzing risk...")

        fund_agent = fundamental_analysis_agent()
        sent_agent = sentiment_analysis_agent()
        risk_agent = risk_analysis_agent()

        fund_task = make_fundamental_task(ticker, metrics_ctx, fund_agent)
        sent_task = make_sentiment_task(ticker, headlines_ctx, sent_agent)
        risk_task = make_risk_task(ticker, metrics_ctx, risk_agent)

        fund_out, sent_out, risk_out = await asyncio.gather(
            loop.run_in_executor(_POOL, _run_single_agent_crew, fund_agent, fund_task),
            loop.run_in_executor(_POOL, _run_single_agent_crew, sent_agent, sent_task),
            loop.run_in_executor(_POOL, _run_single_agent_crew, risk_agent, risk_task),
        )

        fundamental = _parse_fundamental(ticker, fund_out)
        sentiment   = _parse_sentiment(ticker, sent_out)
        risk        = _parse_risk(ticker, risk_out)

        fund_trace = AgentTrace(agent_name="FundamentalAnalysisAgent", ticker=ticker,
                                goal=fund_task.description, final_answer=fund_out, succeeded=True)
        sent_trace = AgentTrace(agent_name="SentimentAnalysisAgent",   ticker=ticker,
                                goal=sent_task.description, final_answer=sent_out, succeeded=True)
        risk_trace = AgentTrace(agent_name="RiskAnalysisAgent",        ticker=ticker,
                                goal=risk_task.description, final_answer=risk_out, succeeded=True)

        await asyncio.gather(
            self.memory.save_trace(job_id, ticker, "FundamentalAnalysisAgent", fund_trace),
            self.memory.save_trace(job_id, ticker, "SentimentAnalysisAgent",   sent_trace),
            self.memory.save_trace(job_id, ticker, "RiskAnalysisAgent",        risk_trace),
        )
        self.tracker.complete(job_id, ticker, "FundamentalAnalysisAgent", f"Score {fundamental.score:.0f} Grade {fundamental.grade}")
        self.tracker.complete(job_id, ticker, "SentimentAnalysisAgent",   f"Sentiment: {sentiment.overall}")
        self.tracker.complete(job_id, ticker, "RiskAnalysisAgent",        f"Risk: {risk.level} ({risk.score:.0f})")
        print(f"[PIPELINE] {ticker} - Agents 2/3/4 DONE", flush=True)
        log.info("  [DONE] Agents 2/3/4 complete - Fund: %s, Sent: %s, Risk: %s",
                 fundamental.grade, sentiment.overall, risk.level)

        # ── Agent 5: CIO ──────────────────────────────────────────────────────
        self.tracker.update(job_id, ticker, "CIOAgent", 0, "Making investment decision...")
        cio = cio_agent()
        cio_task = make_cio_task(
            ticker,
            COMPANY_NAMES.get(ticker, f"{ticker} Corp."),
            fund_out[:500], sent_out[:500], risk_out[:500],
            metrics_ctx, cio,
        )
        cio_out = await loop.run_in_executor(_POOL, _run_single_agent_crew, cio, cio_task)

        recommendation = _parse_recommendation(raw_data, fundamental, sentiment, risk, cio_out)
        cio_trace      = AgentTrace(agent_name="CIOAgent", ticker=ticker,
                                    goal=cio_task.description, final_answer=cio_out, succeeded=True)
        recommendation.cio_trace = cio_trace

        await self.memory.save_trace(job_id, ticker, "CIOAgent", cio_trace)
        self.tracker.complete(job_id, ticker, "CIOAgent",
                              f"{recommendation.action} ({recommendation.confidence:.0f}%)")
        print(f"[PIPELINE] {ticker} - Agent 5 CIO DONE", flush=True)
        log.info("  [DONE] Agent5 CIO: %s %.0f%% | Target $%s",
                 recommendation.action, recommendation.confidence, recommendation.price_target)

        return StockReport(
            ticker         = ticker,
            recommendation = recommendation,
            raw_data       = raw_data,
            all_traces     = [data_trace, fund_trace, sent_trace, risk_trace, cio_trace],
            generated_at   = datetime.utcnow(),
        )


def _build_summary(report: PortfolioReport, failed: dict) -> str:
    buys  = sum(1 for r in report.stock_reports if r.recommendation.action in (InvestmentAction.Buy, InvestmentAction.StrongBuy))
    holds = sum(1 for r in report.stock_reports if r.recommendation.action == InvestmentAction.Hold)
    sells = sum(1 for r in report.stock_reports if r.recommendation.action in (InvestmentAction.Sell, InvestmentAction.StrongSell))
    best  = max(
        (r for r in report.stock_reports if r.recommendation.action in (InvestmentAction.Buy, InvestmentAction.StrongBuy)),
        key=lambda r: r.recommendation.confidence,
        default=None,
    )
    summary = f"Analyzed {len(report.stock_reports)} stock(s): {buys} Buy, {holds} Hold, {sells} Sell."
    if best:
        summary += f" Top pick: {best.ticker} ({best.recommendation.action}, {best.recommendation.confidence:.0f}% confidence)."
    if failed:
        summary += f" Failed: {', '.join(failed.keys())}."
    return summary

