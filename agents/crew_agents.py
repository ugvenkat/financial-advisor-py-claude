"""
All 5 CrewAI agents, their Tasks, and the crew assembly.
Maps 1-to-1 with the .NET agents but uses CrewAI's native
Agent/Task/Crew orchestration instead of a custom ReAct engine.
"""

from __future__ import annotations
import os
from crewai import Agent, Task, Crew, Process
from crewai import LLM

from tools.financial_toolkit import (
    DATA_TOOLS, FUNDAMENTAL_TOOLS, SENTIMENT_TOOLS,
    RISK_TOOLS, CIO_TOOLS,
)

# ── Anthropic Claude LLM config ───────────────────────────────────────────────
def _llm() -> LLM:
    return LLM(
        model      = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
        api_key    = os.getenv("ANTHROPIC_API_KEY"),
        temperature= 0.1,
        max_tokens = 2048,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  AGENT DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════════

def data_collection_agent() -> Agent:
    return Agent(
        role="Data Collection Specialist",
        goal=(
            "Autonomously gather comprehensive financial data for a given stock ticker "
            "including price, ratios, news, analyst ratings, and earnings data."
        ),
        backstory=(
            "You are an expert financial data collector. You systematically fetch data "
            "from multiple sources to build a complete picture of any stock. You never stop "
            "until you have data from ALL required sources: price, financial ratios, "
            "news headlines, analyst ratings, and earnings history."
        ),
        tools=DATA_TOOLS,
        llm=_llm(),
        verbose=True,
        max_iter=3,
        allow_delegation=False,
    )


def fundamental_analysis_agent() -> Agent:
    return Agent(
        role="Fundamental Analysis Expert",
        goal=(
            "Deeply analyze a company's financial health, score it 0-100, "
            "and identify its key strengths and weaknesses."
        ),
        backstory=(
            "You are a CFA-level fundamental analyst who evaluates companies on "
            "P/E ratio, EPS growth, revenue growth, debt levels, and free cash flow. "
            "You always fetch missing data before scoring, consider sector context, "
            "and provide a letter grade with supporting evidence."
        ),
        tools=FUNDAMENTAL_TOOLS,
        llm=_llm(),
        verbose=True,
        max_iter=3,
        allow_delegation=False,
    )


def sentiment_analysis_agent() -> Agent:
    return Agent(
        role="Market Sentiment Analyst",
        goal=(
            "Analyze news sentiment for a stock, classify headlines as Bullish/Neutral/Bearish, "
            "and produce a quantitative sentiment score from -1.0 to +1.0."
        ),
        backstory=(
            "You are a specialist in market sentiment and news analysis. You fetch headlines "
            "from multiple sources, classify each one, and identify the dominant market mood. "
            "You look for themes driving sentiment: earnings beats, product launches, "
            "regulatory news, or macroeconomic concerns."
        ),
        tools=SENTIMENT_TOOLS,
        llm=_llm(),
        verbose=True,
        max_iter=3,
        allow_delegation=False,
    )


def risk_analysis_agent() -> Agent:
    return Agent(
        role="Risk Assessment Specialist",
        goal=(
            "Evaluate investment risk for a stock across multiple dimensions: "
            "market risk, valuation risk, financial risk, and sector risk. "
            "Produce a risk score 0-100 and risk level."
        ),
        backstory=(
            "You are an experienced risk analyst who evaluates beta, P/E valuation, "
            "debt levels, 52-week price position, and sector volatility. You always "
            "fetch the latest data before scoring and identify the most critical "
            "specific risk factors for the company."
        ),
        tools=RISK_TOOLS,
        llm=_llm(),
        verbose=True,
        max_iter=3,
        allow_delegation=False,
    )


def cio_agent() -> Agent:
    return Agent(
        role="Chief Investment Officer",
        goal=(
            "Synthesize all analyst reports into a final investment decision: "
            "StrongBuy / Buy / Hold / Sell / StrongSell with confidence % and price target."
        ),
        backstory=(
            "You are the Chief Investment Officer with 30 years of experience. "
            "You receive reports from your fundamental, sentiment, and risk analysts "
            "and weigh all signals - including conflicting ones - to make a final "
            "investment recommendation. You always compute a price target before deciding. "
            "Your memos are clear, concise, and backed by data."
        ),
        tools=CIO_TOOLS,
        llm=_llm(),
        verbose=True,
        max_iter=2,
        allow_delegation=False,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  TASK DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════════

def make_data_task(ticker: str, agent: Agent) -> Task:
    return Task(
        description=f"""
Collect comprehensive financial data for {ticker}.

You MUST gather ALL of the following using the available tools:
1. Current stock price, P/E ratio, market cap, beta, 52-week range (use get_stock_price)
2. Financial ratios: P/B, debt-to-equity, free cash flow, revenue growth, EPS growth (use get_financial_ratios)
3. Latest 8-10 news headlines (use get_latest_news)
4. Analyst ratings and recent upgrades/downgrades (use get_analyst_ratings)
5. Earnings data: EPS actuals vs estimates (use get_earnings_data)
6. Additional news from MarketWatch (use get_marketwatch_news)

Do NOT stop until you have data from ALL six sources.
""",
        expected_output=f"""
A complete JSON summary of all collected data for {ticker} including:
- current_price, pe_ratio, market_cap, beta, 52w_high, 52w_low, sector
- pb_ratio, debt_to_equity, free_cash_flow, eps_growth, revenue_growth
- news: list of at least 8 headline objects with title and source
- analyst_ratings: strong_buy, buy, hold, sell, strong_sell counts
- earnings: quarterly EPS actuals and estimates
""",
        agent=agent,
    )


def make_fundamental_task(ticker: str, raw_data_summary: str, agent: Agent) -> Task:
    return Task(
        description=f"""
Perform a deep fundamental analysis of {ticker}.

Pre-loaded context from data collection:
{raw_data_summary}

Your tasks:
1. If any key metrics are missing, use get_financial_ratios or get_stock_price to fetch them
2. Run calculate_fundamental_score with ALL available metrics
3. Interpret the score - what does it mean for this specific company?
4. Consider the sector context - is this P/E reasonable for this industry?
5. Identify the top 3 strengths and top 3 weaknesses with supporting data points
""",
        expected_output=f"""
A fundamental analysis report for {ticker} containing:
- score: number 0-100
- grade: letter A/B/C/D/F
- strengths: list of 3 specific strengths with data
- weaknesses: list of 3 specific weaknesses with data
- detailed_analysis: 2-3 sentence analytical conclusion
""",
        agent=agent,
    )


def make_sentiment_task(ticker: str, headlines_context: str, agent: Agent) -> Task:
    return Task(
        description=f"""
Perform a comprehensive sentiment analysis for {ticker}.

Pre-loaded headlines:
{headlines_context}

Your tasks:
1. Fetch fresh news using get_latest_news for {ticker}
2. Fetch additional news from get_marketwatch_news for {ticker}
3. Combine ALL headlines into one list
4. Run classify_sentiment on the combined headlines
5. Identify themes driving sentiment (earnings, macro, product, regulatory)
""",
        expected_output=f"""
A sentiment analysis report for {ticker} containing:
- overall: Bullish / Neutral / Bearish
- score: -1.0 to +1.0
- bullish_pct, neutral_pct, bearish_pct: percentage breakdowns
- top bullish and bearish headlines
- sentiment_summary: 2-sentence summary of the market mood
""",
        agent=agent,
    )


def make_risk_task(ticker: str, metrics_context: str, agent: Agent) -> Task:
    return Task(
        description=f"""
Perform a comprehensive risk analysis for {ticker}.

Pre-loaded metrics:
{metrics_context}

Your tasks:
1. If beta, P/E, or debt/equity are missing, use get_stock_price or get_financial_ratios to fetch them
2. Run calculate_risk_score with all available metrics
3. Consider ALL risk dimensions: market, valuation, financial, sector, technical
4. Identify the most significant risk factors specific to this company
""",
        expected_output=f"""
A risk analysis report for {ticker} containing:
- risk_score: number 0-100 (higher = riskier)
- risk_level: Low / Medium / High / VeryHigh
- risk_factors: list of 3-5 specific risk factors with data
- risk_summary: 2-sentence risk summary
""",
        agent=agent,
    )


def make_cio_task(
    ticker: str,
    company_name: str,
    fundamental_report: str,
    sentiment_report: str,
    risk_report: str,
    metrics_context: str,
    agent: Agent,
) -> Task:
    return Task(
        description=f"""
You are the Chief Investment Officer. Make a final investment decision for {ticker} ({company_name}).

=== AGENT REPORTS ===

FUNDAMENTAL ANALYSIS REPORT:
{fundamental_report}

SENTIMENT ANALYSIS REPORT:
{sentiment_report}

RISK ANALYSIS REPORT:
{risk_report}

MARKET DATA:
{metrics_context}

=== YOUR DECISION PROCESS ===
Step 1: Weigh the signals - do they agree or conflict?
Step 2: Consider the risk-adjusted opportunity
Step 3: Determine your action: StrongBuy / Buy / Hold / Sell / StrongSell
Step 4: Call compute_price_target to calculate a price target
Step 5: State your confidence (0-100%) and time horizon
Step 6: Identify the top catalysts and risks
""",
        expected_output=f"""
A complete investment recommendation for {ticker} as a JSON object:
{{
  "action": "Buy",
  "confidence": 75,
  "price_target": 210.00,
  "time_horizon": "12 months",
  "catalysts": ["catalyst 1", "catalyst 2", "catalyst 3"],
  "risks": ["risk 1", "risk 2", "risk 3"],
  "rationale": "3-4 sentence professional investment memo"
}}
""",
        agent=agent,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  CREW BUILDER
# ═══════════════════════════════════════════════════════════════════════════════

def build_analysis_crew(
    ticker: str,
    company_name: str,
    metrics_context: str,
    headlines_context: str,
    raw_data_summary: str,
    fundamental_report: str,
    sentiment_report: str,
    risk_report: str,
) -> tuple[Crew, dict[str, Task]]:
    """
    Build a Crew for the CIO final decision.
    Data collection + analysis phases are run in parallel separately.
    This crew handles the CIO synthesis step.
    """
    _cio = cio_agent()
    cio_task = make_cio_task(
        ticker, company_name,
        fundamental_report, sentiment_report, risk_report,
        metrics_context, _cio
    )
    crew = Crew(
        agents=[_cio],
        tasks=[cio_task],
        process=Process.sequential,
        verbose=True,
    )
    return crew, {"cio": cio_task}
