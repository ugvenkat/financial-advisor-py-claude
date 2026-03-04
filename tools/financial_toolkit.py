"""
Financial Toolkit — all 10 tools as CrewAI @tool decorated functions.
Mirrors FinancialToolkit.cs exactly: same APIs, same scoring logic.
"""

import json
import re
import math
import requests
from xml.etree import ElementTree
from bs4 import BeautifulSoup
from crewai.tools import tool

# ── Shared HTTP session with Yahoo Finance headers ────────────────────────────

_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept":          "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin":          "https://finance.yahoo.com",
    "Referer":         "https://finance.yahoo.com/",
})

def _get_json(url: str) -> dict | None:
    try:
        r = _SESSION.get(url, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

def _get_raw(url: str) -> str | None:
    try:
        r = _SESSION.get(url, timeout=20)
        r.raise_for_status()
        return r.text
    except Exception:
        return None

def _extract_ticker(raw: str) -> str:
    """Parse ticker from either {\"ticker\": \"AAPL\"} or plain AAPL string."""
    raw = raw.strip()
    # Try JSON first line
    first_line = raw.split("\n")[0].strip()
    for attempt in (first_line, raw):
        try:
            obj = json.loads(attempt)
            for key in ("ticker", "TICKER", "symbol", "SYMBOL"):
                if key in obj and obj[key]:
                    return re.sub(r"[^A-Z0-9.\-]", "", obj[key].upper())
        except Exception:
            pass
    # Plain string fallback
    clean = re.sub(r"[^A-Z0-9.\-]", "", first_line.upper())
    return clean[:10] if clean else ""


# ═══════════════════════════════════════════════════════════════════════════════
#  DATA TOOLS
# ═══════════════════════════════════════════════════════════════════════════════

@tool("get_stock_price")
def get_stock_price(ticker: str) -> str:
    """
    Fetches current stock price, 52-week range, market cap, P/E ratio,
    beta, EPS, and dividend yield using Yahoo Finance JSON API.
    Input: {"ticker": "AAPL"}
    """
    sym = _extract_ticker(ticker)
    if not sym:
        return "Error: could not parse ticker"

    # Try v7 quote API first (most data-rich)
    data = _get_json(f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={sym}")
    result: dict = {}

    quotes = None
    try:
        quotes = data["quoteResponse"]["result"][0]
    except Exception:
        pass

    if quotes:
        def _f(key): return quotes.get(key)
        result = {
            "ticker":         sym,
            "current_price":  _f("regularMarketPrice"),
            "previous_close": _f("regularMarketPreviousClose"),
            "market_cap":     _f("marketCap"),
            "pe_ratio":       _f("trailingPE"),
            "forward_pe":     _f("forwardPE"),
            "eps":            _f("epsTrailingTwelveMonths"),
            "beta":           _f("beta"),
            "52w_high":       _f("fiftyTwoWeekHigh"),
            "52w_low":        _f("fiftyTwoWeekLow"),
            "dividend_yield": _f("dividendYield"),
            "price_to_book":  _f("priceToBook"),
            "sector":         _f("sector"),
            "industry":       _f("industry"),
            "full_name":      _f("longName"),
            "50day_avg":      _f("fiftyDayAverage"),
            "200day_avg":     _f("twoHundredDayAverage"),
            "avg_volume":     _f("averageDailyVolume3Month"),
        }
    else:
        # Fallback to v8 chart API
        data2 = _get_json(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=1d"
        )
        try:
            meta = data2["chart"]["result"][0]["meta"]
            result = {
                "ticker":        sym,
                "current_price": meta.get("regularMarketPrice"),
                "market_cap":    meta.get("marketCap"),
                "52w_high":      meta.get("fiftyTwoWeekHigh"),
                "52w_low":       meta.get("fiftyTwoWeekLow"),
                "currency":      meta.get("currency"),
                "exchange":      meta.get("exchangeName"),
            }
        except Exception:
            return f"Could not fetch price data for {sym} — Yahoo Finance API unavailable"

    cleaned = {k: v for k, v in result.items() if v is not None}
    return json.dumps(cleaned, indent=2) if cleaned else f"No data returned for {sym}"


@tool("get_financial_ratios")
def get_financial_ratios(ticker: str) -> str:
    """
    Fetches detailed financial ratios: P/B ratio, debt-to-equity,
    free cash flow, revenue growth, EPS growth from Yahoo Finance.
    Input: {"ticker": "AAPL"}
    """
    sym = _extract_ticker(ticker)
    url = (
        f"https://query1.finance.yahoo.com/v11/finance/quoteSummary/{sym}"
        f"?modules=financialData,defaultKeyStatistics,incomeStatementHistory"
    )
    data = _get_json(url)
    if not data:
        return f"Could not fetch financial ratios for {sym}"

    try:
        summary = data["quoteSummary"]["result"][0]
    except Exception:
        return f"No data in quoteSummary for {sym}"

    result: dict = {}
    fin  = summary.get("financialData", {})
    stat = summary.get("defaultKeyStatistics", {})

    def _r(obj, key): return (obj.get(key) or {}).get("raw")

    result.update({
        "current_ratio":          _r(fin,  "currentRatio"),
        "debt_to_equity":         _r(fin,  "debtToEquity"),
        "free_cash_flow":         _r(fin,  "freeCashflow"),
        "revenue_growth":         _r(fin,  "revenueGrowth"),
        "earnings_growth":        _r(fin,  "earningsGrowth"),
        "gross_margins":          _r(fin,  "grossMargins"),
        "profit_margins":         _r(fin,  "profitMargins"),
        "return_on_equity":       _r(fin,  "returnOnEquity"),
        "return_on_assets":       _r(fin,  "returnOnAssets"),
        "total_revenue":          _r(fin,  "totalRevenue"),
        "total_cash":             _r(fin,  "totalCash"),
        "total_debt":             _r(fin,  "totalDebt"),
        "operating_cashflow":     _r(fin,  "operatingCashflow"),
        "target_mean_price":      _r(fin,  "targetMeanPrice"),
        "analyst_recommendation": fin.get("recommendationKey"),
        "enterprise_value":       _r(stat, "enterpriseValue"),
        "forward_pe":             _r(stat, "forwardPE"),
        "pb_ratio":               _r(stat, "priceToBook"),
        "peg_ratio":              _r(stat, "pegRatio"),
        "short_ratio":            _r(stat, "shortRatio"),
        "beta":                   _r(stat, "beta"),
        "shares_outstanding":     _r(stat, "sharesOutstanding"),
        "book_value":             _r(stat, "bookValue"),
        "eps_trailing":           _r(stat, "trailingEps"),
        "eps_forward":            _r(stat, "forwardEps"),
    })

    cleaned = {k: v for k, v in result.items() if v is not None}
    return json.dumps(cleaned, indent=2) if cleaned else f"No ratio data for {sym}"


@tool("get_latest_news")
def get_latest_news(ticker: str) -> str:
    """
    Fetches the latest news headlines for a stock from Yahoo Finance RSS feed.
    Input: {"ticker": "AAPL"}
    """
    sym = _extract_ticker(ticker)
    url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={sym}&region=US&lang=en-US"
    rss = _get_raw(url)
    if not rss:
        return f"No news found for {sym}"

    try:
        root = ElementTree.fromstring(rss)
        ns   = {"content": "http://purl.org/rss/1.0/modules/content/"}
        articles = []
        for item in root.iter("item"):
            title   = (item.findtext("title") or "").strip()
            desc    = (item.findtext("description") or "").strip()
            pub     = (item.findtext("pubDate") or "").strip()
            if not title:
                continue
            articles.append({
                "title":   title,
                "summary": desc[:200] if len(desc) > 200 else desc,
                "source":  "Yahoo Finance",
                "date":    pub,
            })
            if len(articles) >= 10:
                break
        return json.dumps(articles, indent=2) if articles else f"No news articles found for {sym}"
    except Exception as e:
        return f"Error parsing news for {sym}: {e}"


@tool("get_analyst_ratings")
def get_analyst_ratings(ticker: str) -> str:
    """
    Fetches analyst consensus: number of Strong Buy, Buy, Hold, Sell, Strong Sell ratings.
    Input: {"ticker": "AAPL"}
    """
    sym = _extract_ticker(ticker)
    url = (
        f"https://query1.finance.yahoo.com/v11/finance/quoteSummary/{sym}"
        f"?modules=recommendationTrend,upgradeDowngradeHistory"
    )
    data = _get_json(url)
    if not data:
        return f"No analyst data for {sym}"

    try:
        summary = data["quoteSummary"]["result"][0]
    except Exception:
        return f"No analyst summary for {sym}"

    result: dict = {}
    trend = (summary.get("recommendationTrend") or {}).get("trend", [])
    if trend:
        t = trend[0]
        result.update({
            "strong_buy":  t.get("strongBuy"),
            "buy":         t.get("buy"),
            "hold":        t.get("hold"),
            "sell":        t.get("sell"),
            "strong_sell": t.get("strongSell"),
            "period":      t.get("period"),
        })

    history = (summary.get("upgradeDowngradeHistory") or {}).get("history", [])
    if history:
        import datetime as _dt
        recent = []
        for h in history[:5]:
            epoch = h.get("epochGradeDate")
            date_str = (
                _dt.datetime.utcfromtimestamp(epoch).strftime("%Y-%m-%d")
                if epoch else ""
            )
            recent.append({
                "firm":   h.get("firm"),
                "action": h.get("action"),
                "from":   h.get("fromGrade"),
                "to":     h.get("toGrade"),
                "date":   date_str,
            })
        result["recent_changes"] = recent

    return json.dumps(result, indent=2)


@tool("get_earnings_data")
def get_earnings_data(ticker: str) -> str:
    """
    Fetches earnings data: EPS estimate vs actual, revenue, surprise percentage.
    Input: {"ticker": "AAPL"}
    """
    sym = _extract_ticker(ticker)
    url = (
        f"https://query1.finance.yahoo.com/v11/finance/quoteSummary/{sym}"
        f"?modules=earnings,earningsTrend,earningsHistory"
    )
    data = _get_json(url)
    if not data:
        return f"No earnings data for {sym}"

    try:
        summary = data["quoteSummary"]["result"][0]
    except Exception:
        return f"No earnings summary for {sym}"

    result: dict = {}
    def _r(obj, key): return (obj.get(key) or {}).get("raw")

    history = (summary.get("earningsHistory") or {}).get("history", [])
    if history:
        quarters = []
        for q in history[:4]:
            quarters.append({
                "quarter":          (q.get("quarter") or {}).get("fmt"),
                "eps_actual":       _r(q, "epsActual"),
                "eps_estimate":     _r(q, "epsEstimate"),
                "surprise_percent": _r(q, "surprisePercent"),
            })
        result["quarterly_earnings"] = quarters

    trend = (summary.get("earningsTrend") or {}).get("trend", [])
    current = next((t for t in trend if t.get("period") == "0q"), None)
    if current:
        result["current_quarter_estimate"] = _r(current.get("earningsEstimate") or {}, "avg") \
            if isinstance(current.get("earningsEstimate"), dict) \
            else (current.get("earningsEstimate") or {}).get("avg", {}).get("raw")
        result["revenue_estimate"] = (
            (current.get("revenueEstimate") or {}).get("avg", {}).get("raw")
        )
        result["growth_estimate"] = _r(current, "growth")

    return json.dumps(result, indent=2)


@tool("get_marketwatch_news")
def get_marketwatch_news(ticker: str) -> str:
    """
    Fetches additional news headlines from MarketWatch.
    Input: {"ticker": "AAPL"}
    """
    sym = _extract_ticker(ticker).lower()
    url = f"https://www.marketwatch.com/investing/stock/{sym}/newsviewer"
    html = _get_raw(url)
    if not html:
        return f"No MarketWatch news for {sym.upper()}"

    soup      = BeautifulSoup(html, "lxml")
    headlines = []
    for tag in soup.select("h3.article__headline")[:8]:
        text = tag.get_text(strip=True)
        if text:
            headlines.append(text)

    if not headlines:
        return f"No MarketWatch headlines found for {sym.upper()}"

    return json.dumps({"source": "MarketWatch", "headlines": headlines}, indent=2)


# ═══════════════════════════════════════════════════════════════════════════════
#  ANALYSIS TOOLS
# ═══════════════════════════════════════════════════════════════════════════════

@tool("classify_sentiment")
def classify_sentiment(headlines: str) -> str:
    """
    Classifies a list of news headlines as Bullish, Neutral, or Bearish
    using keyword analysis. Input: {"headlines": ["headline1", "headline2", ...]}
    """
    try:
        parsed = json.loads(headlines)
        if isinstance(parsed, dict):
            items = parsed.get("headlines", [])
        elif isinstance(parsed, list):
            items = parsed
        else:
            items = []
    except Exception:
        items = [headlines] if headlines else []

    if not items:
        return "Error: no headlines provided"

    BULLISH_WORDS = {
        "beat", "record", "surge", "rally", "upgrade", "buy", "outperform",
        "growth", "profit", "exceeds", "strong", "positive", "soar", "gains",
        "bullish", "dividend", "buyback", "partnership", "breakthrough",
        "wins", "raises", "lifts", "jumps",
    }
    BEARISH_WORDS = {
        "miss", "loss", "decline", "downgrade", "sell", "underperform", "cut",
        "layoff", "warning", "investigation", "lawsuit", "debt", "default",
        "bearish", "recession", "fraud", "risk", "fail", "drop", "crash",
        "concern", "lowers", "slashes", "falls",
    }

    results = []
    for h in items:
        text  = h.lower()
        bull  = sum(1 for w in BULLISH_WORDS if w in text)
        bear  = sum(1 for w in BEARISH_WORDS if w in text)
        diff  = abs(bull - bear)
        conf  = 0.90 if diff >= 3 else 0.75 if diff >= 2 else 0.60 if diff >= 1 else 0.45
        sent  = "Bullish" if bull > bear else ("Bearish" if bear > bull else "Neutral")
        results.append({"headline": h, "sentiment": sent, "confidence": conf})

    total      = len(results)
    bull_count = sum(1 for r in results if r["sentiment"] == "Bullish")
    bear_count = sum(1 for r in results if r["sentiment"] == "Bearish")
    neut_count = total - bull_count - bear_count

    return json.dumps({
        "classifications": results,
        "summary": {
            "total":         total,
            "bullish_count": bull_count,
            "neutral_count": neut_count,
            "bearish_count": bear_count,
            "bullish_pct":   round(bull_count * 100 / total, 1) if total else 0,
            "bearish_pct":   round(bear_count * 100 / total, 1) if total else 0,
            "overall_score": round((bull_count - bear_count) / total, 2) if total else 0,
        }
    }, indent=2)


@tool("calculate_fundamental_score")
def calculate_fundamental_score(
    pe_ratio: float | None = None,
    eps_growth: float | None = None,
    revenue_growth: float | None = None,
    debt_to_equity: float | None = None,
    free_cash_flow_billions: float | None = None,
) -> str:
    """
    Calculates a fundamental score (0-100) and grade (A-F) from financial metrics.
    Pass as JSON: {"pe_ratio": 25, "eps_growth": 0.15, "revenue_growth": 0.10,
                   "debt_to_equity": 0.5, "free_cash_flow_billions": 5.0}
    """
    # Accept either keyword args OR a JSON string as first positional arg
    if isinstance(pe_ratio, str):
        try:
            p = json.loads(pe_ratio)
            pe_ratio               = p.get("pe_ratio")
            eps_growth             = p.get("eps_growth")
            revenue_growth         = p.get("revenue_growth")
            debt_to_equity         = p.get("debt_to_equity")
            free_cash_flow_billions = p.get("free_cash_flow_billions")
        except Exception:
            pass

    def score_metric(val, scorer, weight):
        if val is None:
            return 0.5 * weight, weight, "N/A (neutral 50pts)"
        pts = scorer(val)
        label = f"{val:.2f} → {pts * 100:.0f}/100"
        return pts * weight, weight, label

    breakdown  = {}
    strengths  = []
    weaknesses = []
    total = weight = 0.0

    def add(name, val, scorer, w):
        nonlocal total, weight
        pts_w, w_, label = score_metric(val, scorer, w)
        total  += pts_w
        weight += w_
        breakdown[name] = label
        if val is not None:
            pts = scorer(val)
            if pts > 0.75: strengths.append(f"{name}: {val:.2f}")
            if pts < 0.35: weaknesses.append(f"{name}: {val:.2f}")

    add("pe_ratio",       pe_ratio,               lambda v: 1.0 if v < 15 else 0.8 if v < 25 else 0.5 if v < 40 else 0.25 if v < 60 else 0.1, 1.0)
    add("eps_growth",     eps_growth,              lambda v: 1.0 if v > 0.25 else 0.75 if v > 0.10 else 0.5 if v > 0 else 0.1, 1.0)
    add("revenue_growth", revenue_growth,          lambda v: 1.0 if v > 0.20 else 0.75 if v > 0.10 else 0.5 if v > 0.05 else 0.25 if v > 0 else 0.1, 1.0)
    add("debt_to_equity", debt_to_equity,          lambda v: 1.0 if v < 0.5 else 0.8 if v < 1.0 else 0.5 if v < 2.0 else 0.25 if v < 3.0 else 0.1, 1.0)
    add("free_cash_flow", free_cash_flow_billions, lambda v: 1.0 if v > 10 else 0.75 if v > 1 else 0.5 if v > 0 else 0.1, 1.0)

    final_score = (total / weight * 100) if weight else 50.0
    grade       = "A" if final_score >= 85 else "B" if final_score >= 70 else "C" if final_score >= 55 else "D" if final_score >= 40 else "F"

    return json.dumps({
        "score":     round(final_score, 1),
        "grade":     grade,
        "breakdown": breakdown,
        "strengths":  strengths,
        "weaknesses": weaknesses,
    }, indent=2)


@tool("calculate_risk_score")
def calculate_risk_score(
    beta: float | None = None,
    pe_ratio: float | None = None,
    debt_to_equity: float | None = None,
    sector: str = "",
    current_price: float | None = None,
    week52_high: float | None = None,
    week52_low: float | None = None,
) -> str:
    """
    Calculates a risk score (0-100, higher = riskier) and risk level.
    Pass as JSON: {"beta": 1.2, "pe_ratio": 28, "debt_to_equity": 0.4,
                   "sector": "Technology", "current_price": 189, ...}
    """
    if isinstance(beta, str):
        try:
            p = json.loads(beta)
            beta           = p.get("beta")
            pe_ratio       = p.get("pe_ratio")
            debt_to_equity = p.get("debt_to_equity")
            sector         = p.get("sector", "")
            current_price  = p.get("current_price")
            week52_high    = p.get("week52_high")
            week52_low     = p.get("week52_low")
        except Exception:
            pass

    factors   = []
    risk_sum  = 0.0
    cnt       = 0

    if beta is not None:
        br = 90 if beta > 2.0 else 75 if beta > 1.5 else 60 if beta > 1.2 else 40 if beta > 0.8 else 20
        risk_sum += br; cnt += 1
        if beta > 1.5:
            factors.append(f"High beta ({beta:.2f}) — elevated volatility")
    else:
        risk_sum += 50; cnt += 1

    if pe_ratio is not None:
        vr = 90 if pe_ratio > 80 else 75 if pe_ratio > 50 else 60 if pe_ratio > 35 else 35 if pe_ratio > 20 else 15
        risk_sum += vr; cnt += 1
        if pe_ratio > 60:
            factors.append(f"Very high P/E ({pe_ratio:.1f}) — priced for perfection")
    else:
        risk_sum += 50; cnt += 1

    if debt_to_equity is not None:
        dr = 85 if debt_to_equity > 4 else 70 if debt_to_equity > 2.5 else 50 if debt_to_equity > 1.5 else 30 if debt_to_equity > 0.5 else 15
        risk_sum += dr; cnt += 1
        if debt_to_equity > 3:
            factors.append(f"High leverage (D/E {debt_to_equity:.2f})")
    else:
        risk_sum += 40; cnt += 1

    if current_price and week52_high and week52_low:
        rng = week52_high - week52_low
        pos = (current_price - week52_low) / rng if rng > 0 else 0.5
        risk_sum += 70 if pos > 0.9 else 45 if pos > 0.7 else 30 if pos > 0.4 else 50
        cnt += 1
        if pos > 0.9:
            factors.append("Near 52-week high — limited upside margin")

    sector_mult = {
        "technology": 1.3, "energy": 1.4, "consumer discretionary": 1.2,
        "consumer staples": 0.7, "utilities": 0.6, "healthcare": 0.9,
    }.get((sector or "").lower(), 1.0)
    risk_sum += 50 * sector_mult; cnt += 1

    score = risk_sum / cnt if cnt else 50.0
    level = "VeryHigh" if score >= 70 else "High" if score >= 55 else "Medium" if score >= 35 else "Low"

    return json.dumps({
        "risk_score":       round(score, 1),
        "risk_level":       level,
        "risk_factors":     factors,
        "sector_multiplier": sector_mult,
    }, indent=2)


@tool("compute_price_target")
def compute_price_target(
    current_price: float = 0,
    eps: float | None = None,
    eps_growth: float | None = None,
    pe_ratio: float | None = None,
    action: str = "Hold",
) -> str:
    """
    Computes a price target using earnings-based and multiple-based methods.
    Pass as JSON: {"current_price": 189.30, "eps": 6.43, "eps_growth": 0.12,
                   "pe_ratio": 28, "action": "Buy"}
    """
    if isinstance(current_price, str):
        try:
            p = json.loads(current_price)
            current_price = p.get("current_price", 0)
            eps           = p.get("eps")
            eps_growth    = p.get("eps_growth")
            pe_ratio      = p.get("pe_ratio")
            action        = p.get("action", "Hold")
        except Exception:
            pass

    mult_map = {
        "StrongBuy": 1.25, "Buy": 1.13, "Hold": 1.02,
        "Sell": 0.90, "StrongSell": 0.78,
    }
    mult = mult_map.get(action, 1.0)

    earnings_target = None
    if eps and eps_growth and pe_ratio:
        fwd_eps         = eps * (1 + eps_growth)
        earnings_target = fwd_eps * (pe_ratio * 0.95)

    multiple_target = current_price * mult
    final_target    = ((earnings_target + multiple_target) / 2) if earnings_target else multiple_target
    upside          = ((final_target - current_price) / current_price * 100) if current_price else 0

    return json.dumps({
        "current_price":          round(current_price, 2),
        "multiple_based_target":  round(multiple_target, 2),
        "earnings_based_target":  round(earnings_target, 2) if earnings_target else None,
        "final_price_target":     round(final_target, 2),
        "upside_percent":         round(upside, 1),
    }, indent=2)


# ── Tool lists exposed to agents ─────────────────────────────────────────────

DATA_TOOLS      = [get_stock_price, get_financial_ratios, get_latest_news,
                   get_analyst_ratings, get_earnings_data, get_marketwatch_news]
ANALYSIS_TOOLS  = [classify_sentiment, calculate_fundamental_score, calculate_risk_score]
CIO_TOOLS       = [compute_price_target]
ALL_TOOLS       = DATA_TOOLS + ANALYSIS_TOOLS + CIO_TOOLS
FUNDAMENTAL_TOOLS = [get_financial_ratios, get_stock_price, calculate_fundamental_score]
SENTIMENT_TOOLS   = [get_latest_news, get_marketwatch_news, classify_sentiment]
RISK_TOOLS        = [get_stock_price, get_financial_ratios, calculate_risk_score]
