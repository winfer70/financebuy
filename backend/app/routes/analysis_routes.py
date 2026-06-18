"""
analysis_routes.py — AI stock analysis endpoint for TickerTap.

GET /api/v1/analysis/stock?ticker=XX
  - Fetches live market data via yfinance (price, RSI14, SMA50/200, P/E, sector)
  - Loads investment_rules.json hot (no restart needed)
  - Pre-checks rules: avoid list, analyst target premium, volatility class
  - Posts to Ollama (REDACTED:11434) for LLM analysis
  - Parses recommendation (BUY/HOLD/AVOID/WATCH), entry, stop, target, R:R
  - Saves TradeAnalysis row
  - Returns JSON

Auth: X-Bot-Api-Key header (bot) OR JWT bearer token (normal user).
"""

import json
import os
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional

import httpx
import structlog
import yfinance as yf
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import TradeAnalysis
from ..services.chromadb_client import query_similar, store_analysis
from .auth_routes import get_current_user_or_bot

logger = structlog.get_logger("tickerTap.analysis")

router = APIRouter(prefix="/analysis", tags=["analysis"])

_RULES_PATH = Path(__file__).parent.parent / "config" / "investment_rules.json"
_OLLAMA_URL = os.getenv("OLLAMA_URL", "http://REDACTED:11434")
_OLLAMA_MODEL = os.getenv("OLLAMA_ANALYSIS_MODEL", "qwen3:14b")


# ── Schemas ───────────────────────────────────────────────────────────────────

class AnalysisResponse(BaseModel):
    analysis_id: str
    ticker: str
    recommendation: Optional[str]
    suggested_entry: Optional[float]
    suggested_stop: Optional[float]
    suggested_target: Optional[float]
    risk_reward_ratio: Optional[float]
    market_data: dict
    rules_flags: list
    analysis_text: str
    requested_at: str

    class Config:
        orm_mode = True


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_rules() -> dict:
    try:
        return json.loads(_RULES_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("investment_rules_load_failed", error=str(exc))
        return {}


def _compute_rsi(closes: list, period: int = 14) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0))
        losses.append(max(-delta, 0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def _compute_atr(highs: list, lows: list, closes: list, period: int = 14) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    trs = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return round(atr, 4)


def _fetch_market_data(ticker: str) -> dict:
    t = yf.Ticker(ticker)
    info = t.info or {}
    hist = t.history(period="3mo")

    if hist.empty:
        raise HTTPException(status_code=404, detail=f"No market data found for {ticker}")

    closes = hist["Close"].tolist()
    highs = hist["High"].tolist()
    lows = hist["Low"].tolist()

    price = round(closes[-1], 4) if closes else None
    sma50 = round(sum(closes[-50:]) / min(50, len(closes)), 4) if closes else None
    sma200 = round(sum(closes[-200:]) / min(200, len(closes)), 4) if closes else None
    rsi = _compute_rsi(closes)
    atr = _compute_atr(highs, lows, closes)

    week52_high = info.get("fiftyTwoWeekHigh")
    week52_low = info.get("fiftyTwoWeekLow")
    pe_ratio = info.get("trailingPE") or info.get("forwardPE")
    sector = info.get("sector", "Unknown")
    analyst_target = info.get("targetMeanPrice")
    market_cap = info.get("marketCap")

    return {
        "price": price,
        "sma50": sma50,
        "sma200": sma200,
        "rsi14": rsi,
        "atr14": atr,
        "week52_high": week52_high,
        "week52_low": week52_low,
        "pe_ratio": round(pe_ratio, 2) if pe_ratio else None,
        "sector": sector,
        "analyst_target": analyst_target,
        "market_cap": market_cap,
    }


def _check_rules(ticker: str, market_data: dict, rules: dict) -> list:
    flags = []
    ticker_upper = ticker.upper()

    avoid = [t.upper() for t in rules.get("avoid_tickers", [])]
    if ticker_upper in avoid:
        flags.append({"rule": "AVOID_LIST", "severity": "critical", "detail": f"{ticker} is on the permanent avoid list"})

    volatile = [t.upper() for t in rules.get("volatile_tickers", [])]
    stable = [t.upper() for t in rules.get("stable_tickers", [])]
    if ticker_upper in volatile:
        flags.append({"rule": "VOLATILE_TICKER", "severity": "warning", "detail": f"{ticker} classified as VOLATILE — apply 2-day re-entry cooloff and +5% BEP trigger"})
    elif ticker_upper in stable:
        flags.append({"rule": "STABLE_TICKER", "severity": "info", "detail": f"{ticker} classified as STABLE — +2% BEP trigger applies"})

    price = market_data.get("price")
    analyst_target = market_data.get("analyst_target")
    warn_pct = rules.get("analyst_target_premium_warn_pct", 40.0)
    if price and analyst_target and price > 0:
        premium_pct = ((analyst_target - price) / price) * 100
        if premium_pct < warn_pct:
            flags.append({
                "rule": "ANALYST_TARGET_BAKED_IN",
                "severity": "warning",
                "detail": f"Analyst target ${analyst_target:.2f} is only {premium_pct:.1f}% above current price — target may already be priced in (threshold: {warn_pct}%)"
            })

    rsi = market_data.get("rsi14")
    if rsi and rsi > 70:
        flags.append({"rule": "RSI_OVERBOUGHT", "severity": "warning", "detail": f"RSI14={rsi:.1f} — overbought territory, momentum may reverse"})
    elif rsi and rsi < 30:
        flags.append({"rule": "RSI_OVERSOLD", "severity": "info", "detail": f"RSI14={rsi:.1f} — oversold, potential entry opportunity but confirm trend"})

    sma50 = market_data.get("sma50")
    sma200 = market_data.get("sma200")
    if price and sma50 and sma200:
        if price < sma200:
            flags.append({"rule": "BELOW_SMA200", "severity": "warning", "detail": f"Price ${price} below SMA200 ${sma200:.2f} — in long-term downtrend"})
        elif price > sma50 > sma200:
            flags.append({"rule": "ABOVE_BOTH_SMAS", "severity": "info", "detail": f"Price above SMA50 and SMA200 — uptrend structure intact"})

    tier_s = [t.upper() for t in rules.get("watchlist_tier_s", [])]
    tier_a = [t.upper() for t in rules.get("watchlist_tier_a", [])]
    tier_b = [t.upper() for t in rules.get("watchlist_tier_b", [])]
    if ticker_upper in tier_s:
        flags.append({"rule": "WATCHLIST_TIER_S", "severity": "info", "detail": f"{ticker} is a Tier S (highest conviction) watchlist name"})
    elif ticker_upper in tier_a:
        flags.append({"rule": "WATCHLIST_TIER_A", "severity": "info", "detail": f"{ticker} is a Tier A watchlist name"})
    elif ticker_upper in tier_b:
        flags.append({"rule": "WATCHLIST_TIER_B", "severity": "info", "detail": f"{ticker} is a Tier B watchlist name"})

    return flags


def _build_prompt(ticker: str, market_data: dict, rules: dict, flags: list, rag_context: list = None) -> str:
    rules_text = "\n".join(f"- {r}" for r in rules.get("rules_text", []))
    flag_text = "\n".join(f"- [{f['severity'].upper()}] {f['rule']}: {f['detail']}" for f in flags) if flags else "- No rule violations detected"

    price = market_data.get("price", "N/A")
    rsi = market_data.get("rsi14", "N/A")
    sma50 = market_data.get("sma50", "N/A")
    sma200 = market_data.get("sma200", "N/A")
    atr = market_data.get("atr14", "N/A")
    pe = market_data.get("pe_ratio", "N/A")
    sector = market_data.get("sector", "N/A")
    w52h = market_data.get("week52_high", "N/A")
    w52l = market_data.get("week52_low", "N/A")
    analyst_t = market_data.get("analyst_target", "N/A")

    atr_val = market_data.get("atr14")
    stop_hint = f"{price - 1.5 * atr_val:.2f}" if price and atr_val else "N/A"
    atr_mult = rules.get("hard_stop_atr_multiplier", 1.5)

    rag_section = ""
    if rag_context:
        rag_lines = "\n".join(f"- {r['doc']}" for r in rag_context[:3])
        rag_section = f"\n## Similar Past Trades (for context only)\n{rag_lines}\n"

    return f"""You are a disciplined swing trader analyst. Analyse {ticker} using ONLY the data and rules provided. Be concise and specific.

## Personal Trading Rules (NON-NEGOTIABLE)
{rules_text}

## Pre-Check Rule Flags
{flag_text}

## Market Data for {ticker}
- Current price: ${price}
- RSI(14): {rsi}
- SMA50: {sma50} | SMA200: {sma200}
- ATR(14): {atr}
- 52-week High: {w52h} | Low: {w52l}
- P/E ratio: {pe}
- Sector: {sector}
- Analyst mean target: {analyst_t}
- Suggested hard stop (price - {atr_mult}×ATR): ${stop_hint}
{rag_section}
## Instructions
Provide a structured analysis with EXACTLY these fields (one per line):
RECOMMENDATION: [BUY|HOLD|AVOID|WATCH]
ENTRY: [price or N/A]
STOP: [price — must be below entry]
TARGET: [price — T1 at +7% from entry]
RISK_REWARD: [ratio e.g. 2.5:1 or N/A]
ANALYSIS: [2-4 sentences: setup quality, key risks, alignment with personal rules above]

Do not add extra fields. Do not repeat the rules back."""


def _parse_ollama_response(text: str) -> dict:
    result = {
        "recommendation": None,
        "suggested_entry": None,
        "suggested_stop": None,
        "suggested_target": None,
        "risk_reward_ratio": None,
        "analysis_text": text,
    }

    patterns = {
        "recommendation": r"RECOMMENDATION:\s*([A-Z]+)",
        "suggested_entry": r"ENTRY:\s*\$?([\d.]+)",
        "suggested_stop": r"STOP:\s*\$?([\d.]+)",
        "suggested_target": r"TARGET:\s*\$?([\d.]+)",
        "risk_reward_ratio": r"RISK_REWARD:\s*([\d.]+)",
        "analysis_text": r"ANALYSIS:\s*(.+?)(?:\n[A-Z_]+:|$)",
    }

    for field, pattern in patterns.items():
        m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if not m:
            continue
        val = m.group(1).strip()
        if field == "recommendation":
            result[field] = val.upper()[:16]
        elif field == "analysis_text":
            result[field] = val.strip()
        else:
            try:
                result[field] = float(val)
            except ValueError:
                pass

    return result


async def _call_ollama(prompt: str) -> str:
    timeout = httpx.Timeout(300.0, connect=10.0)
    payload = {
        "model": _OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": 1024},
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{_OLLAMA_URL}/api/generate", json=payload)
            resp.raise_for_status()
            return resp.json().get("response", "")
    except httpx.HTTPStatusError as exc:
        logger.error("ollama_http_error", status=exc.response.status_code)
        raise HTTPException(status_code=502, detail="Ollama returned an error")
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        logger.error("ollama_unreachable", error=str(exc))
        raise HTTPException(status_code=503, detail="Ollama unreachable")


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.get("/stock", response_model=AnalysisResponse)
async def analyse_stock(
    ticker: str = Query(..., min_length=1, max_length=10),
    db: AsyncSession = Depends(get_db),
    _auth=Depends(get_current_user_or_bot),
):
    """Fetch market data, run rules pre-check, call Ollama, save and return analysis."""
    ticker = ticker.upper().strip()
    rules = _load_rules()

    market_data = _fetch_market_data(ticker)
    flags = _check_rules(ticker, market_data, rules)

    # RAG: find similar past analyses with known outcomes
    rag_context = await query_similar(
        ticker=ticker,
        sector=market_data.get("sector", ""),
        recommendation=None,
        n_results=3,
    )

    prompt = _build_prompt(ticker, market_data, rules, flags, rag_context)
    raw_response = await _call_ollama(prompt)
    parsed = _parse_ollama_response(raw_response)

    rr = parsed.get("risk_reward_ratio")
    entry = parsed.get("suggested_entry")
    stop = parsed.get("suggested_stop")
    target = parsed.get("suggested_target")
    rec = parsed.get("recommendation")

    def _to_decimal(v):
        return Decimal(str(v)) if v is not None else None

    analysis = TradeAnalysis(
        analysis_id=uuid.uuid4(),
        ticker=ticker,
        rules_snapshot=rules,
        market_data_snapshot=market_data,
        analysis_json={"raw": raw_response, "flags": flags},
        recommendation=rec,
        suggested_entry=_to_decimal(entry),
        suggested_stop=_to_decimal(stop),
        suggested_target=_to_decimal(target),
        risk_reward_ratio=_to_decimal(rr),
        outcome="OPEN",
    )
    db.add(analysis)
    await db.commit()
    await db.refresh(analysis)

    # Store embedding in ChromaDB for future RAG (no-op if ChromaDB unreachable)
    chromadb_id = await store_analysis(
        analysis_id=str(analysis.analysis_id),
        ticker=ticker,
        recommendation=rec,
        market_data=market_data,
        analysis_text=parsed.get("analysis_text", ""),
        outcome="OPEN",
    )
    if chromadb_id:
        analysis.chromadb_id = chromadb_id
        await db.commit()

    logger.info(
        "trade_analysis_created",
        ticker=ticker,
        recommendation=rec,
        analysis_id=str(analysis.analysis_id),
        rag_results=len(rag_context),
        chromadb_stored=chromadb_id is not None,
    )

    return AnalysisResponse(
        analysis_id=str(analysis.analysis_id),
        ticker=ticker,
        recommendation=rec,
        suggested_entry=entry,
        suggested_stop=stop,
        suggested_target=target,
        risk_reward_ratio=rr,
        market_data=market_data,
        rules_flags=flags,
        analysis_text=parsed.get("analysis_text", raw_response),
        requested_at=analysis.requested_at.isoformat() if analysis.requested_at else datetime.now(timezone.utc).isoformat(),
    )


# ── Refinement endpoints ──────────────────────────────────────────────────────

class ApproveRefinementRequest(BaseModel):
    refinement_id_prefix: str


@router.get("/refinements")
async def list_refinements(
    db: AsyncSession = Depends(get_db),
    _auth=Depends(get_current_user_or_bot),
):
    """List all rule refinements ordered by most recent."""
    from sqlalchemy import select as _select
    from ..models import RuleRefinement

    result = await db.execute(
        _select(RuleRefinement).order_by(RuleRefinement.generated_at.desc()).limit(20)
    )
    rows = result.scalars().all()
    return [
        {
            "refinement_id": str(r.refinement_id),
            "status": r.status,
            "trade_count": r.trade_count,
            "win_rate_pct": float(r.win_rate_pct) if r.win_rate_pct else None,
            "avg_pnl_pct": float(r.avg_pnl_pct) if r.avg_pnl_pct else None,
            "pattern_summary": r.pattern_summary,
            "suggested_rules": r.suggested_rules,
            "generated_at": r.generated_at.isoformat() if r.generated_at else None,
        }
        for r in rows
    ]


@router.post("/refinements/approve")
async def approve_refinement(
    body: ApproveRefinementRequest,
    db: AsyncSession = Depends(get_db),
    _auth=Depends(get_current_user_or_bot),
):
    """Approve a rule refinement: apply suggested rules to investment_rules.json."""
    from sqlalchemy import select as _select
    from ..models import RuleRefinement

    result = await db.execute(_select(RuleRefinement))
    all_refs = result.scalars().all()
    match = next(
        (r for r in all_refs if str(r.refinement_id).startswith(body.refinement_id_prefix)),
        None,
    )
    if not match:
        raise HTTPException(status_code=404, detail="Refinement not found")
    if match.status != "pending":
        raise HTTPException(status_code=400, detail=f"Refinement already {match.status}")

    suggested = (match.suggested_rules or {}).get("rules", [])

    # Append suggested rules to rules_text in investment_rules.json
    try:
        rules = json.loads(_RULES_PATH.read_text(encoding="utf-8"))
        existing = rules.get("rules_text", [])
        new_rules = [r for r in suggested if r not in existing]
        rules["rules_text"] = existing + new_rules
        _RULES_PATH.write_text(json.dumps(rules, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to update rules: {exc}")

    match.status = "approved"
    from datetime import datetime as _dt, timezone as _tz
    match.approved_at = _dt.now(_tz.utc)
    await db.commit()

    return {"status": "approved", "applied_rules": suggested}
