"""
scanner_worker.py — Volume Flow Scanner background worker for TickerTap.

Implements the arq background job `run_scanner`, which performs a 5-phase
top-down volume flow analysis:

    Phase 1 — Sector ETF volume surge detection (ratio >= 2x on an up-day)
    Phase 2 — Industry ETF drill-down within each active sector
    Phase 3 — Individual stock screening: volume filter + fundamental filter
    Phase 4 — Auto-scoring (revenue momentum, volume confirm, analyst consensus)
    Phase 5 — Position sizing (1.5% risk model, 8% max position cap)

Results are persisted to the `scan_results` table (ScanResult ORM model).
Enqueue scans via `enqueue_scanner(result_id)` from API route handlers.
"""

from __future__ import annotations

import asyncio
import os
import uuid
import warnings
from datetime import datetime
from typing import Optional

import pandas as pd
import structlog
import yfinance as yf
from arq import create_pool
from arq.connections import RedisSettings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from ..logging_config import configure_structlog

# Silence yfinance deprecation warnings and download progress noise
warnings.filterwarnings("ignore")

configure_structlog()
logger = structlog.get_logger("trading.scanner_worker")

# ── Standalone DB / Redis setup (worker runs outside FastAPI) ─────────────────

_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@db:5432/tickerTap",
)
_REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# Small pool — scanner worker issues only a handful of DB calls per job
_engine = create_async_engine(
    _DATABASE_URL, echo=False, pool_size=3, max_overflow=1, pool_pre_ping=True
)
_SessionLocal = sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

_redis_pool = None


async def _get_redis():
    """Lazily create and return the arq Redis pool for the scanner worker.

    Returns:
        arq Redis connection pool.
    """
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = await create_pool(RedisSettings.from_dsn(_REDIS_URL))
    return _redis_pool


# ── Scanner constants ──────────────────────────────────────────────────────────

SECTOR_ETFS = {
    "Technology": "XLK",
    "Communication Services": "XLC",
    "Consumer Discretionary": "XLY",
    "Financials": "XLF",
    "Healthcare": "XLV",
    "Energy": "XLE",
    "Industrials": "XLI",
    "Materials": "XLB",
    "Real Estate": "XLRE",
    "Utilities": "XLU",
    "Consumer Staples": "XLP",
}

INDUSTRY_ETFS = {
    "Technology": {
        "Semiconductors": ["SOXX", "SMH"],
        "Software": ["IGV"],
        "Cloud/AI": ["CLOU", "BOTZ"],
        "Cybersecurity": ["HACK", "BUG"],
    },
    "Healthcare": {
        "Biotech": ["XBI", "IBB"],
        "Medical Devices": ["IHI"],
        "Pharma": ["IHE"],
    },
    "Financials": {"Banks": ["KBE"], "Insurance": ["KIE"], "Fintech": ["IPAY"]},
    "Energy": {"Oil E&P": ["XOP"], "Oil Services": ["OIH"]},
    "Consumer Discretionary": {"Retail": ["XRT"], "Homebuilders": ["XHB"]},
    "Industrials": {"Aerospace/Defense": ["ITA"], "Transportation": ["IYT"]},
    "Materials": {"Metals & Mining": ["XME"], "Gold Miners": ["GDX"]},
    "Communication Services": {"Internet": ["FDN"], "Media": ["PBS"]},
    "Consumer Staples": {"Food & Beverage": ["PBJ"]},
    "Real Estate": {"REITs": ["VNQ"]},
    "Utilities": {"Electric Utilities": ["XLU"]},
}

INDUSTRY_STOCKS = {
    "Semiconductors": ["NVDA", "AMD", "AVGO", "QCOM", "MU", "AMAT", "LRCX", "MRVL", "TSM"],
    "Software": ["MSFT", "ORCL", "CRM", "NOW", "ADBE", "WDAY", "PANW"],
    "Cloud/AI": ["AMZN", "GOOGL", "MSFT", "META", "SNOW", "PLTR", "DDOG", "MDB", "NET"],
    "Cybersecurity": ["PANW", "CRWD", "ZS", "FTNT", "CYBR"],
    "Biotech": ["AMGN", "GILD", "BIIB", "VRTX", "REGN", "MRNA"],
    "Medical Devices": ["MDT", "BSX", "ISRG", "ABT", "SYK"],
    "Pharma": ["JNJ", "PFE", "MRK", "LLY", "ABBV"],
    "Banks": ["JPM", "BAC", "WFC", "GS", "MS"],
    "Insurance": ["MET", "PRU", "AIG", "AFL"],
    "Fintech": ["V", "MA", "PYPL", "SQ"],
    "Oil E&P": ["XOM", "CVX", "COP", "EOG"],
    "Oil Services": ["SLB", "HAL", "BKR"],
    "Retail": ["AMZN", "WMT", "TGT", "COST", "HD"],
    "Homebuilders": ["DHI", "LEN", "NVR", "PHM"],
    "Aerospace/Defense": ["LMT", "RTX", "NOC", "GD", "BA"],
    "Transportation": ["UPS", "FDX", "JBHT", "XPO"],
    "Metals & Mining": ["FCX", "NEM", "GOLD", "AA"],
    "Gold Miners": ["GLD", "AEM", "WPM", "KGC"],
    "Internet": ["META", "GOOGL", "NFLX", "SNAP", "PINS"],
    "Media": ["DIS", "CMCSA", "NFLX", "WBD"],
    "REITs": ["PLD", "AMT", "CCI", "EQIX", "PSA"],
    "Food & Beverage": ["COST", "PG", "KO", "PEP", "MDLZ"],
    "Electric Utilities": ["NEE", "DUK", "SO", "AEP"],
}

# Minimum volume ratio (today's volume / 50-day avg) to qualify as a surge
VOLUME_THRESHOLD = 2.0
# Fraction of total portfolio value risked per trade
RISK_PER_TRADE_PCT = 0.015
# Hard ceiling — no single position may exceed this fraction of the portfolio
MAX_POSITION_PCT = 0.08


# ── OHLCV fetch helper ────────────────────────────────────────────────────────


def _fetch_batch_ohlcv(tickers: list, period: str = "60d") -> dict:
    """Fetch daily OHLCV data for one or more tickers via yfinance.

    Args:
        tickers: List of ticker symbols to download.
        period:  Lookback period string accepted by yfinance (default "60d").

    Returns:
        Dict mapping ticker → pd.DataFrame (Open/High/Low/Close/Volume).
        Tickers with no data or fewer than 5 bars are omitted.
    """
    if not tickers:
        return {}

    result: dict = {}
    try:
        if len(tickers) == 1:
            # Single-ticker path: yfinance returns a plain DataFrame
            df = yf.download(
                tickers[0], period=period, interval="1d",
                auto_adjust=True, progress=False,
            )
            if not df.empty and len(df) >= 5:
                result[tickers[0]] = df
        else:
            # Multi-ticker path: yfinance returns (Metric, Ticker) MultiIndex columns
            # group_by="ticker" makes indexing cleaner: raw[ticker]["Close"]
            raw = yf.download(
                tickers, period=period, interval="1d",
                auto_adjust=True, progress=False, group_by="ticker",
            )
            for ticker in tickers:
                try:
                    df = raw[ticker].dropna(how="all")
                    if not df.empty and len(df) >= 5:
                        result[ticker] = df
                except (KeyError, TypeError):
                    pass
    except Exception as exc:
        logger.warning("_fetch_batch_ohlcv error", error=str(exc))

    return result


# ── Phase 1: Sector ETF surge detection ───────────────────────────────────────


def _phase1_sync(ohlcv_data: dict) -> list:
    """Identify sector ETFs with a volume surge on an up-price day.

    Compares the latest bar's volume against the rolling 50-day average of
    all preceding bars.  A sector is flagged when ratio >= 2.0 AND close > prior close.

    Args:
        ohlcv_data: Dict keyed as "SectorName|ETFTicker" → pd.DataFrame.

    Returns:
        List of dicts: [{"sector", "etf", "ratio", "price"}, ...].
    """
    active = []
    for label, df in ohlcv_data.items():
        sector, etf = label.split("|", 1)
        try:
            # 50-bar average excludes the current (incomplete or just-closed) bar
            avg_vol = df["Volume"].iloc[:-1].tail(50).mean()
            if avg_vol == 0 or pd.isna(avg_vol):
                continue
            ratio = df["Volume"].iloc[-1] / avg_vol
            price_up = float(df["Close"].iloc[-1]) > float(df["Close"].iloc[-2])
            if ratio >= VOLUME_THRESHOLD and price_up:
                active.append({
                    "sector": sector,
                    "etf": etf,
                    "ratio": round(float(ratio), 2),
                    "price": round(float(df["Close"].iloc[-1]), 2),
                })
        except Exception:
            pass

    return active


# ── Phase 2: Industry ETF drill-down ──────────────────────────────────────────


def _phase2_sync(active_sectors: list, industry_ohlcv: dict) -> list:
    """Drill into active sectors to identify surging industry ETFs.

    For each active sector, iterates its industry buckets and selects the
    industry ETF with the highest volume ratio.  An industry is flagged when
    best_ratio >= 2.0 AND that ETF closed higher on the day.

    Args:
        active_sectors:  List of active sector dicts (output of _phase1_sync).
        industry_ohlcv:  Dict mapping ETF ticker → pd.DataFrame for all
                         relevant industry ETFs.

    Returns:
        List of dicts: [{"sector", "industry", "etf", "ratio"}, ...].
    """
    active = []
    active_sector_names = {s["sector"] for s in active_sectors}

    for sector_name in active_sector_names:
        industries = INDUSTRY_ETFS.get(sector_name, {})
        for industry_name, etfs in industries.items():
            best_ratio = 0.0
            best_etf = None
            best_up = False

            for etf in etfs:
                df = industry_ohlcv.get(etf)
                if df is None or len(df) < 5:
                    continue
                try:
                    avg_vol = df["Volume"].iloc[:-1].tail(50).mean()
                    if avg_vol == 0 or pd.isna(avg_vol):
                        continue
                    ratio = float(df["Volume"].iloc[-1] / avg_vol)
                    price_up = float(df["Close"].iloc[-1]) > float(df["Close"].iloc[-2])
                    if ratio > best_ratio:
                        best_ratio = ratio
                        best_etf = etf
                        best_up = price_up
                except Exception:
                    pass

            if best_etf and best_ratio >= VOLUME_THRESHOLD and best_up:
                active.append({
                    "sector": sector_name,
                    "industry": industry_name,
                    "etf": best_etf,
                    "ratio": round(best_ratio, 2),
                })

    return active


# ── Phase 3 helpers ───────────────────────────────────────────────────────────


def _volume_ratio_simple(df: pd.DataFrame) -> tuple:
    """Compute volume ratio and directional flag for a single OHLCV DataFrame.

    Args:
        df: Daily OHLCV DataFrame with at least 3 rows.

    Returns:
        Tuple (ratio: float, price_up: bool).
    """
    avg_vol = df["Volume"].iloc[:-1].tail(50).mean()
    if avg_vol == 0 or pd.isna(avg_vol):
        return 0.0, False
    ratio = float(df["Volume"].iloc[-1] / avg_vol)
    price_up = float(df["Close"].iloc[-1]) > float(df["Close"].iloc[-2])
    return ratio, price_up


def _get_fundamentals_sync(ticker: str) -> dict:
    """Fetch fundamental data for a ticker via yfinance.

    Attempts quarterly revenue YoY first; falls back to TTM revenueGrowth
    from the info dict.  Also pulls the next earnings date from the calendar
    endpoint for the binary-event disqualification check.

    Args:
        ticker: Uppercase ticker symbol.

    Returns:
        Dict with keys: name, market_cap, current_price, target_mean,
        target_high, rec_key, n_analysts, rev_yoy_pct, next_earnings.
        Any value is None when the data is unavailable.
    """
    t = yf.Ticker(ticker)
    info = t.info

    name = info.get("shortName") or info.get("longName")
    market_cap = info.get("marketCap")
    current_price = info.get("currentPrice") or info.get("regularMarketPrice")
    target_mean = info.get("targetMeanPrice")
    target_high = info.get("targetHighPrice")
    rec_key = info.get("recommendationKey")
    n_analysts = info.get("numberOfAnalystOpinions")
    # revenueGrowth: trailing-12-month YoY as a decimal (0.22 = 22%)
    rev_growth_ttm = info.get("revenueGrowth")

    # Quarterly revenue YoY: compare most-recent quarter vs same quarter last year
    rev_yoy_pct: Optional[float] = None
    try:
        qf = t.quarterly_financials
        if "Total Revenue" in qf.index and len(qf.columns) >= 5:
            rev = qf.loc["Total Revenue"].values  # columns are sorted newest → oldest
            if rev[4] != 0 and not pd.isna(rev[4]) and not pd.isna(rev[0]):
                rev_yoy_pct = float((rev[0] - rev[4]) / abs(rev[4]) * 100)
    except Exception:
        pass

    # Fall back to TTM figure from info when quarterly data is unavailable
    if rev_yoy_pct is None and rev_growth_ttm is not None:
        try:
            rev_yoy_pct = float(rev_growth_ttm) * 100
        except (TypeError, ValueError):
            pass

    # Next earnings date — used only for the binary-event disqualifier check
    next_earnings: Optional[pd.Timestamp] = None
    try:
        cal = t.calendar
        if cal is not None and not cal.empty and "Earnings Date" in cal.index:
            next_earnings = pd.Timestamp(cal.loc["Earnings Date"].iloc[0])
    except Exception:
        pass

    return {
        "name": name,
        "market_cap": market_cap,
        "current_price": current_price,
        "target_mean": target_mean,
        "target_high": target_high,
        "rec_key": rec_key,
        "n_analysts": n_analysts,
        "rev_yoy_pct": rev_yoy_pct,
        "next_earnings": next_earnings,
    }


def _check_disqualifiers(price: float, info: dict) -> list:
    """Check whether a stock fails any fundamental disqualification criterion.

    Args:
        price: Latest closing price in USD.
        info:  Fundamentals dict returned by `_get_fundamentals_sync`.

    Returns:
        List of human-readable disqualifier strings.
        An empty list means the stock passed all checks.
    """
    reasons: list = []

    # 1. Already trading above analyst price target — upside is thin
    target_mean = info.get("target_mean")
    if target_mean and price > target_mean * 1.05:
        reasons.append(f"price ${price:.2f} exceeds mean target ${target_mean:.2f} +5%")

    # 2. Revenue growth too weak to justify a momentum thesis
    rev_yoy = info.get("rev_yoy_pct")
    if rev_yoy is not None and rev_yoy < 15.0:
        reasons.append(f"rev_yoy {rev_yoy:.1f}% below 15% threshold")

    # 3. Market cap too small — liquidity / spread risk
    market_cap = info.get("market_cap")
    if market_cap and market_cap < 500_000_000:
        reasons.append(f"market_cap ${market_cap / 1e6:.0f}M below $500M minimum")

    # 4. Earnings announcement within 5 days — binary event risk
    next_earnings = info.get("next_earnings")
    if next_earnings is not None:
        try:
            # Normalise both timestamps to tz-naive UTC for safe arithmetic
            now_naive = pd.Timestamp(datetime.utcnow())
            if getattr(next_earnings, "tzinfo", None) is not None:
                ne_naive = next_earnings.tz_convert("UTC").tz_localize(None)
            else:
                ne_naive = next_earnings
            days_to = (ne_naive - now_naive).days
            if 0 <= days_to <= 5:
                reasons.append(f"earnings in {days_to}d")
        except Exception:
            pass

    return reasons


# ── Phase 4: Auto-scoring ─────────────────────────────────────────────────────


def _score_candidate(candidate: dict) -> dict:
    """Compute objective score components for a scan candidate.

    Scores three quantitative dimensions (0-5 each):
      - revenue_momentum  — trailing revenue YoY growth rate
      - volume_confirm    — today's volume surge multiplier
      - analyst_consensus — Wall Street recommendation consensus

    Four subjective dimensions (thesis_clarity, risk_reward, sector_tailwind,
    entry_zone_quality) are left null for the human trader to fill in.

    Args:
        candidate: Dict with keys vol_ratio, rev_yoy_pct, rec_key.

    Returns:
        Dict with keys: scores (nested dict), auto_score (int),
        auto_score_max (int — 15 when analyst data present, else 10).
    """
    rev_yoy = candidate.get("rev_yoy_pct", 0) or 0
    vol_r = candidate.get("vol_ratio", 0)
    rec = (candidate.get("rec_key") or "").lower().replace(" ", "")

    # Revenue momentum: tiered on YoY growth percentage
    if rev_yoy >= 40:
        rev_score = 5
    elif rev_yoy >= 25:
        rev_score = 4
    elif rev_yoy >= 15:
        rev_score = 3
    elif rev_yoy >= 10:
        rev_score = 2
    elif rev_yoy > 0:
        rev_score = 1
    else:
        rev_score = 0

    # Volume confirmation: tiered on surge multiplier
    if vol_r >= 4:
        vol_score = 5
    elif vol_r >= 3:
        vol_score = 4
    elif vol_r >= 2.5:
        vol_score = 3
    elif vol_r >= 2:
        vol_score = 2
    else:
        vol_score = 1

    # Analyst consensus
    rec_map = {"strongbuy": 5, "buy": 4, "hold": 3, "underperform": 2, "sell": 1}
    rec_score = rec_map.get(rec, None)

    auto_score = rev_score + vol_score + (rec_score or 0)
    auto_max = 15 if rec_score is not None else 10

    return {
        "scores": {
            "revenue_momentum": rev_score,
            "volume_confirm": vol_score,
            "analyst_consensus": rec_score,
            # Subjective dimensions — filled in by the human trader at review time
            "thesis_clarity": None,
            "risk_reward": None,
            "sector_tailwind": None,
            "entry_zone_quality": None,
        },
        "auto_score": auto_score,
        "auto_score_max": auto_max,
    }


# ── Phase 5: Position sizing ──────────────────────────────────────────────────


def _size_position(price: float, portfolio_value_usd: float) -> dict:
    """Compute position size using a fixed-fractional 1.5% risk model.

    Uses a default 8% stop-loss distance from entry.  Hard-caps the resulting
    position at 8% of total portfolio value.

    Args:
        price:                Latest closing price per share (USD).
        portfolio_value_usd:  Total portfolio value in USD.

    Returns:
        Dict with keys: risk_usd, stop_dist, shares, position_usd,
        position_pct, at_cap (True when the 8% ceiling was applied).
    """
    risk_usd = portfolio_value_usd * RISK_PER_TRADE_PCT
    stop_dist = price * 0.08  # default 8% stop from entry price
    shares = max(1, int(risk_usd / stop_dist))
    position_usd = shares * price
    position_pct = position_usd / portfolio_value_usd * 100

    # Cap position at 8% of portfolio value
    if position_pct > MAX_POSITION_PCT * 100:
        shares = max(1, int((portfolio_value_usd * MAX_POSITION_PCT) / price))
        position_usd = shares * price
        position_pct = position_usd / portfolio_value_usd * 100

    return {
        "risk_usd": round(risk_usd, 2),
        "stop_dist": round(stop_dist, 2),
        "shares": shares,
        "position_usd": round(position_usd, 2),
        "position_pct": round(position_pct, 2),
        # True when the position hit the 8% ceiling (within 5% of cap)
        "at_cap": position_pct >= MAX_POSITION_PCT * 100 * 0.95,
    }


# ── Main arq job ──────────────────────────────────────────────────────────────


async def run_scanner(ctx: dict, result_id: str) -> None:
    """Execute a Volume Flow Scanner job.

    Top-down scan pipeline:
      Phase 1 — Sector ETF surge detection
      Phase 2 — Industry ETF drill-down within active sectors
      Phase 3 — Stock screening (volume + price filter + fundamentals)
      Phase 4 — Auto-scoring (pure computation, no yfinance)
      Phase 5 — Position sizing (pure computation, no yfinance)

    Results are persisted to the ScanResult row identified by result_id.

    Args:
        ctx:       arq job context dict.
        result_id: UUID string of the ScanResult row to process.
    """
    # Bind per-job context so all log lines carry the scan ID
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(worker="trading-worker", scan_id=result_id)

    # Late import to avoid circular references at module load time
    from ..models import ScanResult

    start_ts = datetime.utcnow()

    # ── Step 1: Load row, read parameters, mark running ──────────────────────
    portfolio_value_usd = 10000.0
    session = _SessionLocal()
    try:
        stmt = select(ScanResult).where(ScanResult.result_id == uuid.UUID(result_id))
        res = await session.execute(stmt)
        scan = res.scalar_one_or_none()
        if not scan:
            logger.warning("ScanResult not found", result_id=result_id)
            return
        # Capture the full parameters dict before the session closes
        parameters_json: dict = dict(scan.parameters_json or {})
        portfolio_value_usd = float(
            parameters_json.get("portfolio_value_usd", 10000)
        )
        scan.status = "running"
        scan.started_at = start_ts
        await session.commit()
    finally:
        await session.close()

    # Build session context for volume projection
    from .scanner_session import get_session_context, project_daily_volume
    session_ctx = get_session_context()
    # Allow caller to override mode via parameters_json
    requested_mode = parameters_json.get("mode", "auto")
    if requested_mode in ("live", "prev-day"):
        session_ctx["mode"] = requested_mode
    # Store session state in parameters_json for result persistence
    parameters_json["session_state"] = session_ctx["session_state"]
    parameters_json["elapsed_weight"] = session_ctx["elapsed_weight"]
    parameters_json["mode"] = session_ctx["mode"]

    logger.info("Scanner started", result_id=result_id, portfolio=portfolio_value_usd)

    try:
        # All yfinance calls are sync — wrap in executor to avoid blocking the event loop
        loop = asyncio.get_event_loop()

        # ── Phase 1: Sector ETF volume surge ─────────────────────────────────
        sector_tickers = list(SECTOR_ETFS.values())
        sector_ohlcv_raw = await loop.run_in_executor(
            None, lambda: _fetch_batch_ohlcv(sector_tickers)
        )
        # Re-key as "SectorName|ETFTicker" so _phase1_sync can label results
        sector_ohlcv = {
            f"{sector}|{etf}": sector_ohlcv_raw[etf]
            for sector, etf in SECTOR_ETFS.items()
            if etf in sector_ohlcv_raw
        }
        active_sectors = _phase1_sync(sector_ohlcv)
        logger.info("Phase 1 done", active_sector_count=len(active_sectors))

        # ── Phase 2: Industry ETF drill-down ──────────────────────────────────
        active_sector_names = {s["sector"] for s in active_sectors}
        # Collect unique industry ETF tickers needed for all active sectors
        industry_etf_list: list = []
        for sector_name in active_sector_names:
            for etfs in INDUSTRY_ETFS.get(sector_name, {}).values():
                industry_etf_list.extend(etfs)
        industry_etf_list = list(set(industry_etf_list))

        industry_ohlcv: dict = {}
        if industry_etf_list:
            industry_ohlcv = await loop.run_in_executor(
                None, lambda: _fetch_batch_ohlcv(industry_etf_list)
            )
        active_industries = _phase2_sync(active_sectors, industry_ohlcv)
        logger.info("Phase 2 done", active_industry_count=len(active_industries))

        # ── Phase 3: Stock screening + fundamentals + scoring + sizing ────────
        candidates: list = []
        seen_tickers: set = set()

        for ind_entry in active_industries:
            industry_name = ind_entry["industry"]
            sector_name = ind_entry["sector"]
            stock_tickers = INDUSTRY_STOCKS.get(industry_name, [])
            if not stock_tickers:
                continue

            # Fetch OHLCV for all stocks in the industry (single batch call)
            # Capture loop variable explicitly to avoid late-binding in lambda
            stock_ohlcv = await loop.run_in_executor(
                None, lambda t=stock_tickers: _fetch_batch_ohlcv(t)
            )

            # First pass: cheap volume + price filter (no network calls)
            vol_passing: list = []  # list of (ticker, vol_ratio, price)
            for ticker, df in stock_ohlcv.items():
                try:
                    vol_ratio, price_up = _volume_ratio_simple(df)
                    price = float(df["Close"].iloc[-1])
                    # Require 2x volume surge, up-day, and price >= $10 (no penny stocks)
                    if vol_ratio >= VOLUME_THRESHOLD and price_up and price >= 10.0:
                        vol_passing.append((ticker, vol_ratio, price))
                except Exception:
                    pass

            # Second pass: fundamentals + disqualifiers (one network call per ticker)
            for ticker, vol_ratio, price in vol_passing:
                if ticker in seen_tickers:
                    # De-duplicate tickers that appear in multiple industries
                    continue
                seen_tickers.add(ticker)

                try:
                    # _get_fundamentals_sync is blocking — run in executor
                    info = await loop.run_in_executor(
                        None, lambda t=ticker: _get_fundamentals_sync(t)
                    )
                except Exception as exc:
                    logger.warning("Fundamentals fetch failed", ticker=ticker, error=str(exc))
                    continue

                disqualifiers = _check_disqualifiers(price, info)
                if disqualifiers:
                    logger.debug("Ticker disqualified", ticker=ticker, reasons=disqualifiers)
                    continue

                # Compute upside percentage to analyst mean price target
                target_mean = info.get("target_mean")
                upside_pct = (
                    round((target_mean - price) / price * 100, 1)
                    if target_mean and price
                    else None
                )

                candidate: dict = {
                    "ticker": ticker,
                    "industry": industry_name,
                    "sector": sector_name,
                    "price": round(price, 2),
                    "vol_ratio": round(vol_ratio, 2),
                    "rev_yoy_pct": info.get("rev_yoy_pct"),
                    "target_mean": info.get("target_mean"),
                    "target_high": info.get("target_high"),
                    "upside_pct": upside_pct,
                    "rec_key": info.get("rec_key"),
                    "n_analysts": info.get("n_analysts"),
                }

                # Phase 4: objective scoring (pure computation)
                candidate.update(_score_candidate(candidate))

                # Phase 5: position sizing (pure computation)
                candidate["position"] = _size_position(price, portfolio_value_usd)

                candidates.append(candidate)

        scan_duration_s = round((datetime.utcnow() - start_ts).total_seconds(), 1)
        logger.info(
            "Scan complete",
            result_id=result_id,
            phase1=len(active_sectors),
            phase2=len(active_industries),
            phase3=len(candidates),
            duration_s=scan_duration_s,
        )

        # ── Persist results ───────────────────────────────────────────────────
        results_json = {
            "active_sectors": active_sectors,
            "active_industries": active_industries,
            "candidates": candidates,
            "phase1_count": len(active_sectors),
            "phase2_count": len(active_industries),
            "phase3_count": len(candidates),
            "scan_duration_s": scan_duration_s,
        }

        session = _SessionLocal()
        try:
            stmt = select(ScanResult).where(ScanResult.result_id == uuid.UUID(result_id))
            res = await session.execute(stmt)
            scan = res.scalar_one_or_none()
            if scan:
                scan.results_json = results_json
                scan.parameters_json = parameters_json  # persists session_state/elapsed_weight/mode
                scan.mode = session_ctx["mode"]
                scan.status = "complete"
                scan.completed_at = datetime.utcnow()
                scan.phase_reached = 3
            await session.commit()
        finally:
            await session.close()

    except Exception as exc:
        logger.exception("Scanner failed", result_id=result_id, error=str(exc))
        try:
            session = _SessionLocal()
            try:
                stmt = select(ScanResult).where(ScanResult.result_id == uuid.UUID(result_id))
                res = await session.execute(stmt)
                scan = res.scalar_one_or_none()
                if scan:
                    scan.status = "error"
                    scan.error_message = str(exc)[:500]
                await session.commit()
            finally:
                await session.close()
        except Exception:
            pass


# ── Enqueue helper ────────────────────────────────────────────────────────────


async def enqueue_scanner(result_id: str) -> str:
    """Enqueue a Volume Flow Scanner job to the arq worker.

    Called from the API route after creating a ScanResult row with
    status="pending".  Uses a lazily-initialised module-level Redis pool.

    Args:
        result_id: UUID string of the ScanResult to process.

    Returns:
        The arq job_id string, or an empty string if enqueuing failed.
    """
    try:
        redis = await _get_redis()
        # enqueue_job returns a Job object (with .job_id) or None on dedup
        job = await redis.enqueue_job("run_scanner", result_id, _queue_name="arq:trading")
        return job.job_id if job else ""
    except Exception as exc:
        logger.error("enqueue_scanner failed", result_id=result_id, error=str(exc))
        return ""
