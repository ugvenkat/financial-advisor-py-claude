"""
All domain models — mirrors the .NET Models.cs exactly.
"""

from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
import uuid


# ─────────────────────────────────────────────────────────────────
#  ENUMS
# ─────────────────────────────────────────────────────────────────

class JobStatus(str, Enum):
    Queued    = "Queued"
    Running   = "Running"
    Completed = "Completed"
    Failed    = "Failed"

class SentimentClass(str, Enum):
    Bullish = "Bullish"
    Neutral = "Neutral"
    Bearish = "Bearish"

class RiskLevel(str, Enum):
    Low      = "Low"
    Medium   = "Medium"
    High     = "High"
    VeryHigh = "VeryHigh"

class InvestmentAction(str, Enum):
    StrongBuy  = "StrongBuy"
    Buy        = "Buy"
    Hold       = "Hold"
    Sell       = "Sell"
    StrongSell = "StrongSell"


# ─────────────────────────────────────────────────────────────────
#  AGENTIC PRIMITIVES
# ─────────────────────────────────────────────────────────────────

class AgentStep(BaseModel):
    step_number:  int      = 0
    thought:      str      = ""
    action:       str      = ""
    action_input: str      = ""
    observation:  str      = ""
    is_final:     bool     = False
    final_answer: str      = ""
    timestamp:    datetime = Field(default_factory=datetime.utcnow)

class AgentTrace(BaseModel):
    agent_name:   str             = ""
    ticker:       str             = ""
    goal:         str             = ""
    steps:        list[AgentStep] = Field(default_factory=list)
    final_answer: str             = ""
    succeeded:    bool            = False

    @property
    def total_steps(self) -> int:
        return len(self.steps)


# ─────────────────────────────────────────────────────────────────
#  REQUEST / JOB MODELS
# ─────────────────────────────────────────────────────────────────

class AnalysisRequest(BaseModel):
    tickers:       list[str]       = Field(..., min_length=1)
    force_refresh: bool            = False
    analyst_notes: Optional[str]   = None

class AnalysisJob(BaseModel):
    job_id:        str                   = Field(default_factory=lambda: uuid.uuid4().hex[:8].upper())
    tickers:       list[str]             = Field(default_factory=list)
    status:        JobStatus             = JobStatus.Queued
    created_at:    datetime              = Field(default_factory=datetime.utcnow)
    completed_at:  Optional[datetime]    = None
    reports:       list["StockReport"]   = Field(default_factory=list)
    error_message: Optional[str]         = None
    output_dir:    Optional[str]         = None
    failed_tickers: dict[str, str]       = Field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────
#  RAW DATA MODELS
# ─────────────────────────────────────────────────────────────────

class NewsArticle(BaseModel):
    title:        str               = ""
    summary:      str               = ""
    source:       str               = ""
    url:          str               = ""
    published_at: Optional[datetime] = None

class FinancialMetrics(BaseModel):
    current_price:       Optional[float] = None
    market_cap:          Optional[float] = None
    pe_ratio:            Optional[float] = None
    pb_ratio:            Optional[float] = None
    eps:                 Optional[float] = None
    eps_growth_yoy:      Optional[float] = None
    revenue_growth_yoy:  Optional[float] = None
    debt_to_equity:      Optional[float] = None
    free_cash_flow:      Optional[float] = None
    beta:                Optional[float] = None
    dividend_yield:      Optional[float] = None
    fifty_two_week_high: Optional[float] = None
    fifty_two_week_low:  Optional[float] = None
    sector:              str             = ""
    industry:            str             = ""

class AnalystRating(BaseModel):
    firm:         str            = ""
    rating:       str            = ""
    price_target: Optional[float] = None
    date:         Optional[datetime] = None

class QuarterlyResult(BaseModel):
    quarter: str            = ""
    eps:     Optional[float] = None
    revenue: Optional[float] = None

class EarningsData(BaseModel):
    last_eps:             Optional[float]        = None
    estimated_eps:        Optional[float]        = None
    eps_surprise_percent: Optional[float]        = None
    last_revenue:         Optional[float]        = None
    next_earnings_date:   Optional[str]          = None
    quarterly_history:    list[QuarterlyResult]  = Field(default_factory=list)

class StockRawData(BaseModel):
    ticker:          str                  = ""
    company_name:    str                  = ""
    metrics:         FinancialMetrics     = Field(default_factory=FinancialMetrics)
    news:            list[NewsArticle]    = Field(default_factory=list)
    analyst_ratings: list[AnalystRating]  = Field(default_factory=list)
    earnings:        EarningsData         = Field(default_factory=EarningsData)
    collected_at:    datetime             = Field(default_factory=datetime.utcnow)


# ─────────────────────────────────────────────────────────────────
#  AGENT OUTPUT MODELS
# ─────────────────────────────────────────────────────────────────

class SentimentItem(BaseModel):
    source:     str            = ""
    headline:   str            = ""
    sentiment:  SentimentClass = SentimentClass.Neutral
    confidence: float          = 0.0

class FundamentalScore(BaseModel):
    ticker:           str             = ""
    score:            float           = 50.0
    grade:            str             = "C"
    strengths:        list[str]       = Field(default_factory=list)
    weaknesses:       list[str]       = Field(default_factory=list)
    detailed_analysis: str            = ""
    trace:            AgentTrace      = Field(default_factory=AgentTrace)

class SentimentScore(BaseModel):
    ticker:           str                = ""
    overall:          SentimentClass     = SentimentClass.Neutral
    score:            float              = 0.0
    bullish_percent:  float              = 0.0
    neutral_percent:  float              = 100.0
    bearish_percent:  float              = 0.0
    sentiment_summary: str              = ""
    items:            list[SentimentItem] = Field(default_factory=list)
    trace:            AgentTrace         = Field(default_factory=AgentTrace)

class RiskScore(BaseModel):
    ticker:       str         = ""
    level:        RiskLevel   = RiskLevel.Medium
    score:        float       = 50.0
    risk_factors: list[str]   = Field(default_factory=list)
    risk_summary: str         = ""
    trace:        AgentTrace  = Field(default_factory=AgentTrace)

class InvestmentRecommendation(BaseModel):
    ticker:        str                  = ""
    company_name:  str                  = ""
    action:        InvestmentAction     = InvestmentAction.Hold
    confidence:    float                = 60.0
    risk_level:    RiskLevel            = RiskLevel.Medium
    price_target:  Optional[float]      = None
    current_price: Optional[float]      = None
    upside_percent: Optional[float]     = None
    time_horizon:  str                  = "6-12 months"
    rationale:     str                  = ""
    key_catalysts: list[str]            = Field(default_factory=list)
    key_risks:     list[str]            = Field(default_factory=list)
    fundamental:   FundamentalScore     = Field(default_factory=FundamentalScore)
    sentiment:     SentimentScore       = Field(default_factory=SentimentScore)
    risk:          RiskScore            = Field(default_factory=RiskScore)
    cio_summary:   str                  = ""
    cio_trace:     AgentTrace           = Field(default_factory=AgentTrace)


# ─────────────────────────────────────────────────────────────────
#  REPORT MODELS
# ─────────────────────────────────────────────────────────────────

class StockReport(BaseModel):
    ticker:         str                     = ""
    recommendation: InvestmentRecommendation = Field(default_factory=InvestmentRecommendation)
    raw_data:       StockRawData            = Field(default_factory=StockRawData)
    all_traces:     list[AgentTrace]        = Field(default_factory=list)
    generated_at:   datetime               = Field(default_factory=datetime.utcnow)

class PortfolioReport(BaseModel):
    job_id:           str               = ""
    generated_at:     datetime          = Field(default_factory=datetime.utcnow)
    stock_reports:    list[StockReport] = Field(default_factory=list)
    executive_summary: str             = ""


# ─────────────────────────────────────────────────────────────────
#  LIVE STATUS MODELS
# ─────────────────────────────────────────────────────────────────

class AgentActivity(BaseModel):
    ticker:     str      = ""
    agent:      str      = ""
    step:       int      = 0
    activity:   str      = ""
    completed:  bool     = False
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def seconds_since_update(self) -> float:
        return (datetime.utcnow() - self.updated_at).total_seconds()

class LiveJobStatus(BaseModel):
    job_id:        str                           = ""
    last_update:   datetime                      = Field(default_factory=datetime.utcnow)
    active_agents: dict[str, AgentActivity]      = Field(default_factory=dict)


# Rebuild forward references
AnalysisJob.model_rebuild()
