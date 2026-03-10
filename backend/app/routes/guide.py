"""
routes/guide.py — User Guide AI Q&A endpoint.

Proxies user questions to the Ollama LLM on Server B (Kali) for
context-aware answers about TickerTap features and usage.

Route:
  POST /api/v1/guide/ask — Submit a question, receive an LLM-generated answer.

Environment variables:
  OLLAMA_URL   — Ollama API base URL (default: http://localhost:11434)
  OLLAMA_MODEL — Ollama model to use (default: llama3:8b-instruct-q4_K_M)

Requires a valid JWT token (authenticated users only).
"""

import logging
import os

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .auth_routes import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/guide", tags=["guide"])

# ── Configuration ────────────────────────────────────────────────────────────
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3:8b-instruct-q4_K_M")
_OLLAMA_TIMEOUT = 60  # seconds

# ── System prompt providing TickerTap context to the LLM ─────────────────────
_SYSTEM_PROMPT = (
    "You are an expert assistant for TickerTap, a professional Bloomberg-terminal-style "
    "investment terminal application. Answer questions helpfully and concisely. If a "
    "question is not about TickerTap, politely redirect to TickerTap-related topics.\n\n"
    "Key features:\n"
    "- Dashboard: Portfolio selector dropdown, performance chart (1W/1M/3M/YTD/1Y/ALL) "
    "using actual purchase dates for accurate growth tracking (shows empty state when no data), "
    "market heatmap (clickable tiles → VIEW CHART), summary stats (portfolio value, "
    "unrealised P&L with all-time %, gain/loss today with today %, position count), "
    "Top Gainers panel with BEP/Price/CHG/Gain-Loss columns, "
    "Biggest Losers panel with same detailed columns and VIEW ALL button, category filter tabs "
    "(ALL/STOCKS/CRYPTO/ETFs/PHYSICAL) on both gainers and losers, "
    "portfolio performance chart displayed full-width above the grid, "
    "same-symbol positions consolidated into single rows in top positions, "
    "allocation donut chart (respects display currency symbol)\n"
    "- Portfolio Manager: Multiple portfolios, 4 asset types (stocks, crypto, ETFs, "
    "physical assets incl. gold/silver/platinum/palladium/copper with futures tickers), "
    "add/modify/sell/delete positions, stop-loss tracking, profit-taking targets (highlights "
    "green when price reaches target), exclude/include toggle, allocation % column showing "
    "position weight in portfolio, price change period selector (1D/5D/1M/3M/6M/1Y) with "
    "period G/L in summary strip, bulk SMA with alerts, analyst price targets (mean/high/low "
    "shown in modify modal), CSV import/export (includes Profit Taking column), sortable columns, "
    "cross-page nav (VIEW CHART/VIEW NEWS), group tags, "
    "CHG column shows dollar amount with percentage (e.g. $123.45 (+1.23%)), "
    "all monetary values respect display currency preference with real-time conversion\n"
    "- Charts: Symbol search + watchlist chips with live prices, candlestick/line charts, "
    "intervals (1m-1mo), periods (1M-ALL or 100-ALL bars), SMA overlays (50/150/custom), "
    "breakout detection, volume bars toggle, crosshair + hover tooltip, zoom/pan, "
    "9 drawing tools (trend line, horizontal line, ray, rectangle, Fibonacci, pitchfork, "
    "arrow, text, ruler) with colour/width/style options, ruler measurement tool shows "
    "price difference and % change between two points, chart template save/load, "
    "event indicators overlay (earnings 'E', dividends 'D', splits 'S' as colour-coded "
    "markers with tooltip badges showing event details), "
    "purchase point indicators (nearest-bar matching for accurate placement across all intervals)\n"
    "- News: LLM-scored articles (-5 to +5), sentiment badges (VERY BULLISH to VERY BEARISH), "
    "reasoning text, per-ticker impact badges with context popup (VIEW CHART/FILTER NEWS), "
    "sentiment filter (ALL/BULLISH/BEARISH), portfolio toggle, watchlist toggle (mutually "
    "exclusive with portfolio — filters articles by watchlist tickers), source badges "
    "(YAHOO/GOOGLE/FINVIZ/MKTWATCH), ticker search, staleness indicator, "
    "server-side filtering and pagination — portfolio, sentiment, and search filters applied "
    "before pagination for consistent page sizes (25, 50, 75, or 100 articles per page) "
    "and PREV/NEXT page navigation controls\n"
    "- Transactions: History table (TXN ID, Type, Symbol, Amount, Currency, Account, Status, Date), "
    "type filter (ALL/DEPOSIT/WITHDRAWAL/BUY/SELL), search, summary stats, export CSV\n"
    "- Orders: Blotter table, status filter (ALL/OPEN/FILLED/CANCELLED), summary stats incl. "
    "open notional, cancel individual or all open orders, place order modal\n"
    "- Import: Broker statement import (8 brokers: Robinhood, IBKR, E*TRADE, TD Ameritrade, "
    "Coinbase, Binance, Schwab, Fidelity), drag-and-drop upload, manual import grid, "
    "portfolio review tab, commit staged positions\n"
    "Portfolio CSV export (Ticker/Name/Qty/Date/Price/AssetType/GroupTag/StopLoss/ProfitTaking), "
    "transaction CSV export (TXN ID/Type/Symbol/Amount/Currency/Account/Status/Date), "
    "CSV import requires Ticker+Qty+Price columns\n"
    "- Ticker Strip: Live scrolling market quotes, portfolio tickers or defaults, "
    "smart polling (3s open / 5m closed)\n"
    "- Settings: Profile display (email, name, phone, KYC, account status), "
    "display currency (USD/EUR/GBP/PLN/CHF/JPY/CAD/AUD) with real-time ECB rates, "
    "language selection (English/Polish/German/Chinese/Spanish/Portuguese/French/Japanese/Italian), "
    "preferences persist across sessions\n"
    "- Account & Security: Email/password sign-in, registration, "
    "email verification required on registration before first login, "
    "strong password validation (uppercase, lowercase, digit, special character, min 8 chars), "
    "account lockout after 10 failed attempts (15-minute cooldown), "
    "edit name and change email from Settings > Account (name changes reflect instantly in navbar avatar, email change requires verification), "
    "deactivate account (disables login, preserves data, reactivate via email link), "
    "delete account with 30-day soft delete (cancellable via email) or permanent deletion, "
    "forgot/reset password, "
    "5-minute inactivity auto-logout, silent token refresh, TLS 1.3 encryption, "
    "HSTS and Content Security Policy headers, Redis-backed rate limiting\n"
    "- Watchlists: Create unlimited named watchlists, add stocks/crypto/ETFs/physical assets, "
    "live price quotes with market-aware polling, detailed table (Symbol, Name, Price, "
    "Change $ + %, Day Range, Since Added %, Notes), summary strip (total value, day change, "
    "item count), category filter tabs, per-item notes, buy directly from watchlist into a "
    "portfolio, rename and delete watchlists, performance since added tracking\n"
    "- Feedback & Reporting: Submit bug reports with subject/category/description, "
    "suggest improvements through dedicated feedback form, report activation issues "
    "without authentication, accessible from sidebar navigation\n"
    "- Interface: Collapsible sidebar (icons-only mode) with preference saved automatically, "
    "breadcrumb in topbar shows translated page names, sidebar state persisted across sessions, "
    "full browser back/forward navigation support with pushState/popstate, "
    "sidebar hover tooltips on all navigation buttons"
)


# ── Request / Response schemas ───────────────────────────────────────────────
class GuideAskRequest(BaseModel):
    """Schema for a user question submitted to the guide endpoint.

    Attributes:
        question: The user's question text (1-500 chars).
    """
    question: str = Field(..., min_length=1, max_length=500)


class GuideAskResponse(BaseModel):
    """Schema for the guide endpoint response.

    Attributes:
        answer: The LLM-generated answer text.
        model:  The Ollama model tag used for generation.
    """
    answer: str
    model: str


# ── Endpoint ─────────────────────────────────────────────────────────────────
@router.post("/ask", response_model=GuideAskResponse)
async def ask_guide(body: GuideAskRequest, current_user=Depends(get_current_user)):
    """Submit a question to the TickerTap AI guide.

    Proxies the question to the Ollama LLM with TickerTap context.

    Args:
        body: GuideAskRequest containing the user's question.
        current_user: Authenticated user (injected by JWT dependency).

    Returns:
        GuideAskResponse with the LLM answer and model info.

    Raises:
        HTTPException 503: If Ollama is unreachable or times out.
        HTTPException 502: If Ollama returns an unexpected response.
    """
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": f"{_SYSTEM_PROMPT}\n\nUser question: {body.question}",
        "stream": False,
        "options": {
            "temperature": 0.4,
            "num_predict": 512,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=_OLLAMA_TIMEOUT) as client:
            resp = await client.post(f"{OLLAMA_URL}/api/generate", json=payload)
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException:
        logger.warning("Ollama timeout for guide question: %s", body.question[:80])
        raise HTTPException(
            status_code=503,
            detail="AI service timed out. Please try again shortly.",
        )
    except httpx.HTTPError as exc:
        logger.error("Ollama connection error: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="AI service is currently unavailable.",
        )

    answer = data.get("response", "").strip()
    if not answer:
        raise HTTPException(
            status_code=502,
            detail="AI service returned an empty response.",
        )

    return GuideAskResponse(answer=answer, model=OLLAMA_MODEL)
