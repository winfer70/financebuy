"""
bot.py — Telegram bot for tickerTap AI trading assistant.

Commands:
  /analyze <TICKER>          — AI analysis with rules pre-check via /api/v1/analysis/stock
  /buy <TICKER> <QTY> <PRICE> — Add position to AI Paper portfolio
  /sell <TICKER> <QTY> <PRICE> — Close/reduce position in AI Paper portfolio
  /positions                  — List open AI Paper positions with current P&L
  /pnl                        — P&L summary (open + closed)
  /alerts                     — List active price alerts

All API calls go to localhost:8000 with X-Bot-Api-Key header.
Bot token loaded from TELEGRAM_BOT_TOKEN env var.
"""

import asyncio
import logging
import os
from decimal import Decimal, InvalidOperation
from typing import Optional

import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logger = logging.getLogger("tickerTap.telegram_bot")

_BASE_URL = "http://localhost:8000/api/v1"
_BOT_API_KEY = os.getenv("BOT_API_KEY", "")
_PAPER_PORTFOLIO_ID = os.getenv("AI_PAPER_PORTFOLIO_ID", "")
_BOT_USER_ID = os.getenv("BOT_USER_ID", "")
_HEADERS = {"X-Bot-Api-Key": _BOT_API_KEY}
_TIMEOUT = httpx.Timeout(300.0, connect=10.0)


# ── API helpers ───────────────────────────────────────────────────────────────

async def _api_get(path: str, params: dict = None) -> dict:
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
        r = await client.get(f"{_BASE_URL}{path}", params=params)
        r.raise_for_status()
        return r.json()


async def _api_post(path: str, body: dict) -> dict:
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
        r = await client.post(f"{_BASE_URL}{path}", json=body)
        r.raise_for_status()
        return r.json()


async def _api_patch(path: str, body: dict) -> dict:
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
        r = await client.patch(f"{_BASE_URL}{path}", json=body)
        r.raise_for_status()
        return r.json()


def _fmt_price(v) -> str:
    if v is None:
        return "N/A"
    try:
        return f"${float(v):,.2f}"
    except (TypeError, ValueError):
        return str(v)


def _fmt_pct(v) -> str:
    if v is None:
        return "N/A"
    try:
        return f"{float(v):+.2f}%"
    except (TypeError, ValueError):
        return str(v)


# ── /analyze ─────────────────────────────────────────────────────────────────

async def cmd_analyze(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /analyze <TICKER>")
        return

    ticker = context.args[0].upper().strip()
    msg = await update.message.reply_text(f"Analysing {ticker}... (may take 1-2 min)")

    try:
        data = await _api_get("/analysis/stock", params={"ticker": ticker})
    except httpx.HTTPStatusError as e:
        await msg.edit_text(f"Error {e.response.status_code}: {e.response.text[:200]}")
        return
    except Exception as e:
        await msg.edit_text(f"Failed: {e}")
        return

    rec = data.get("recommendation") or "N/A"
    entry = _fmt_price(data.get("suggested_entry"))
    stop = _fmt_price(data.get("suggested_stop"))
    target = _fmt_price(data.get("suggested_target"))
    rr = data.get("risk_reward_ratio")
    rr_str = f"{float(rr):.1f}:1" if rr else "N/A"
    price = _fmt_price(data.get("market_data", {}).get("price"))
    rsi = data.get("market_data", {}).get("rsi14")
    analysis_text = data.get("analysis_text", "")
    flags = data.get("rules_flags", [])

    flag_lines = ""
    if flags:
        icons = {"critical": "🔴", "warning": "⚠️", "info": "ℹ️"}
        flag_lines = "\n".join(
            f"{icons.get(f['severity'], '•')} {f['detail']}"
            for f in flags
        )
        flag_lines = f"\n\n*Rules Flags:*\n{flag_lines}"

    text = (
        f"*{ticker} Analysis*\n"
        f"Price: {price}  |  RSI14: {rsi or 'N/A'}\n\n"
        f"*Recommendation: {rec}*\n"
        f"Entry: {entry}  |  Stop: {stop}  |  Target: {target}\n"
        f"R:R  {rr_str}"
        f"{flag_lines}\n\n"
        f"_{analysis_text}_\n\n"
        f"ID: `{data.get('analysis_id', '')[:8]}`"
    )
    await msg.edit_text(text, parse_mode="Markdown")


# ── /buy ─────────────────────────────────────────────────────────────────────

async def cmd_buy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 3:
        await update.message.reply_text("Usage: /buy <TICKER> <QTY> <PRICE>")
        return

    ticker = context.args[0].upper().strip()
    try:
        qty = float(context.args[1])
        price = float(context.args[2])
    except ValueError:
        await update.message.reply_text("QTY and PRICE must be numbers")
        return

    if not _PAPER_PORTFOLIO_ID:
        await update.message.reply_text("AI_PAPER_PORTFOLIO_ID not configured")
        return

    try:
        pos = await _api_post(
            f"/portfolio-manager/{_PAPER_PORTFOLIO_ID}/positions",
            {
                "ticker": ticker,
                "quantity": qty,
                "purchase_price": price,
                "group_tag": "AI_PAPER",
            },
        )
    except httpx.HTTPStatusError as e:
        await update.message.reply_text(f"Failed: {e.response.status_code} {e.response.text[:200]}")
        return
    except Exception as e:
        await update.message.reply_text(f"Failed: {e}")
        return

    total = qty * price
    await update.message.reply_text(
        f"✅ *Bought {ticker}*\n"
        f"{qty} × ${price:,.2f} = ${total:,.2f}\n"
        f"Portfolio: AI Paper\n"
        f"Position ID: `{str(pos.get('position_id', ''))[:8]}`",
        parse_mode="Markdown",
    )


# ── /sell ─────────────────────────────────────────────────────────────────────

async def cmd_sell(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 3:
        await update.message.reply_text("Usage: /sell <TICKER> <QTY> <PRICE>")
        return

    ticker = context.args[0].upper().strip()
    try:
        qty = float(context.args[1])
        sell_price = float(context.args[2])
    except ValueError:
        await update.message.reply_text("QTY and PRICE must be numbers")
        return

    if not _PAPER_PORTFOLIO_ID:
        await update.message.reply_text("AI_PAPER_PORTFOLIO_ID not configured")
        return

    # Find open position for this ticker in AI Paper portfolio
    try:
        positions_data = await _api_get(
            f"/portfolio-manager/{_PAPER_PORTFOLIO_ID}/positions",
            params={"open_only": True},
        )
    except Exception as e:
        await update.message.reply_text(f"Failed to fetch positions: {e}")
        return

    positions = positions_data if isinstance(positions_data, list) else positions_data.get("positions", [])
    match = next(
        (p for p in positions if p.get("ticker", "").upper() == ticker and p.get("group_tag") == "AI_PAPER"),
        None,
    )
    if not match:
        await update.message.reply_text(f"No open AI Paper position found for {ticker}")
        return

    position_id = match["position_id"]
    cost_basis = float(match.get("purchase_price", 0))
    pnl_pct = ((sell_price - cost_basis) / cost_basis * 100) if cost_basis else 0

    try:
        await _api_post(
            f"/portfolio-manager/{_PAPER_PORTFOLIO_ID}/positions/{position_id}/sell",
            {"quantity": qty, "sell_price": sell_price},
        )
    except httpx.HTTPStatusError as e:
        await update.message.reply_text(f"Failed: {e.response.status_code} {e.response.text[:200]}")
        return
    except Exception as e:
        await update.message.reply_text(f"Failed: {e}")
        return

    icon = "🟢" if pnl_pct >= 0 else "🔴"
    await update.message.reply_text(
        f"{icon} *Sold {ticker}*\n"
        f"{qty} × ${sell_price:,.2f}\n"
        f"Cost basis: ${cost_basis:,.2f}  |  P&L: {pnl_pct:+.2f}%",
        parse_mode="Markdown",
    )


# ── /positions ────────────────────────────────────────────────────────────────

async def cmd_positions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _PAPER_PORTFOLIO_ID:
        await update.message.reply_text("AI_PAPER_PORTFOLIO_ID not configured")
        return

    try:
        data = await _api_get(f"/portfolio-manager/{_PAPER_PORTFOLIO_ID}/positions")
    except Exception as e:
        await update.message.reply_text(f"Failed: {e}")
        return

    positions = data if isinstance(data, list) else data.get("positions", [])
    open_pos = [p for p in positions if not p.get("closed_at") and p.get("group_tag") == "AI_PAPER"]

    if not open_pos:
        await update.message.reply_text("No open AI Paper positions.")
        return

    lines = ["*Open AI Paper Positions*\n"]
    for p in open_pos:
        ticker = p.get("ticker", "?")
        qty = p.get("quantity", 0)
        cost = float(p.get("purchase_price", 0))
        current = float(p.get("current_price") or cost)
        pnl_pct = ((current - cost) / cost * 100) if cost else 0
        icon = "🟢" if pnl_pct >= 0 else "🔴"
        lines.append(f"{icon} *{ticker}* {qty} @ ${cost:,.2f} → ${current:,.2f} ({pnl_pct:+.2f}%)")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── /pnl ──────────────────────────────────────────────────────────────────────

async def cmd_pnl(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _PAPER_PORTFOLIO_ID:
        await update.message.reply_text("AI_PAPER_PORTFOLIO_ID not configured")
        return

    try:
        data = await _api_get(f"/portfolio-manager/{_PAPER_PORTFOLIO_ID}/positions")
    except Exception as e:
        await update.message.reply_text(f"Failed: {e}")
        return

    positions = data if isinstance(data, list) else data.get("positions", [])
    paper = [p for p in positions if p.get("group_tag") == "AI_PAPER"]

    open_pos = [p for p in paper if not p.get("closed_at")]
    closed_pos = [p for p in paper if p.get("closed_at")]

    open_value = sum(float(p.get("quantity", 0)) * float(p.get("current_price") or p.get("purchase_price", 0)) for p in open_pos)
    open_cost = sum(float(p.get("quantity", 0)) * float(p.get("purchase_price", 0)) for p in open_pos)
    open_pnl = open_value - open_cost

    closed_pnl = 0.0
    for p in closed_pos:
        qty = float(p.get("quantity", 0))
        cost = float(p.get("purchase_price", 0))
        sold = float(p.get("sold_price") or p.get("purchase_price", 0))
        closed_pnl += (sold - cost) * qty

    icon_o = "🟢" if open_pnl >= 0 else "🔴"
    icon_c = "🟢" if closed_pnl >= 0 else "🔴"
    total = open_pnl + closed_pnl
    icon_t = "🟢" if total >= 0 else "🔴"

    await update.message.reply_text(
        f"*AI Paper P&L*\n\n"
        f"{icon_o} Open unrealised: ${open_pnl:+,.2f} ({len(open_pos)} positions)\n"
        f"{icon_c} Closed realised: ${closed_pnl:+,.2f} ({len(closed_pos)} trades)\n"
        f"─────────────────\n"
        f"{icon_t} Total: ${total:+,.2f}",
        parse_mode="Markdown",
    )


# ── /alerts ───────────────────────────────────────────────────────────────────

async def cmd_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        data = await _api_get("/alerts", params={"active_only": True})
    except Exception as e:
        await update.message.reply_text(f"Failed: {e}")
        return

    alerts = data if isinstance(data, list) else data.get("alerts", [])
    if not alerts:
        await update.message.reply_text("No active price alerts.")
        return

    lines = ["*Active Price Alerts*\n"]
    for a in alerts[:20]:
        ticker = a.get("symbol", "?")
        cond = a.get("condition", "?")
        target = _fmt_price(a.get("target_price"))
        note = a.get("note", "")
        note_str = f" — {note}" if note else ""
        lines.append(f"• *{ticker}* {cond} {target}{note_str}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── /refinements ──────────────────────────────────────────────────────────────

async def cmd_refinements(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List pending rule refinement suggestions from weekly meta-analysis."""
    try:
        data = await _api_get("/analysis/refinements")
    except Exception as e:
        await update.message.reply_text(f"Failed: {e}")
        return

    refinements = data if isinstance(data, list) else data.get("refinements", [])
    pending = [r for r in refinements if r.get("status") == "pending"]

    if not pending:
        await update.message.reply_text("No pending rule refinements.")
        return

    lines = ["*Pending Rule Refinements*\n"]
    for r in pending[:5]:
        rid = str(r.get("refinement_id", ""))[:8]
        trades = r.get("trade_count", "?")
        wr = r.get("win_rate_pct", "?")
        summary = r.get("pattern_summary", "")[:200]
        rules = r.get("suggested_rules", {}).get("rules", [])
        rule_lines = "\n".join(f"  • {rule}" for rule in rules[:3])
        lines.append(
            f"ID: `{rid}` | {trades} trades | Win rate: {wr}%\n"
            f"_{summary}_\n"
            f"Suggestions:\n{rule_lines}\n"
            f"Approve: /approve_refinement {rid}\n"
        )

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── /approve_refinement ───────────────────────────────────────────────────────

async def cmd_approve_refinement(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Approve a rule refinement and apply suggested rules to investment_rules.json."""
    if not context.args:
        await update.message.reply_text("Usage: /approve_refinement <ID_PREFIX>")
        return

    rid_prefix = context.args[0].strip()
    try:
        data = await _api_post(f"/analysis/refinements/approve", {"refinement_id_prefix": rid_prefix})
    except httpx.HTTPStatusError as e:
        await update.message.reply_text(f"Failed: {e.response.status_code} {e.response.text[:200]}")
        return
    except Exception as e:
        await update.message.reply_text(f"Failed: {e}")
        return

    applied = data.get("applied_rules", [])
    rule_text = "\n".join(f"• {r}" for r in applied) if applied else "No rules applied"
    await update.message.reply_text(
        f"✅ *Refinement Approved*\n\n"
        f"Applied to investment_rules.json:\n{rule_text}",
        parse_mode="Markdown",
    )


# ── Bot lifecycle ─────────────────────────────────────────────────────────────

_application: Optional[Application] = None


async def start_bot() -> None:
    global _application
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN not set — Telegram bot disabled")
        return

    _application = (
        Application.builder()
        .token(token)
        .connect_timeout(10)
        .read_timeout(300)
        .build()
    )

    _application.add_handler(CommandHandler("analyze", cmd_analyze))
    _application.add_handler(CommandHandler("buy", cmd_buy))
    _application.add_handler(CommandHandler("sell", cmd_sell))
    _application.add_handler(CommandHandler("positions", cmd_positions))
    _application.add_handler(CommandHandler("pnl", cmd_pnl))
    _application.add_handler(CommandHandler("alerts", cmd_alerts))
    _application.add_handler(CommandHandler("refinements", cmd_refinements))
    _application.add_handler(CommandHandler("approve_refinement", cmd_approve_refinement))

    await _application.initialize()
    await _application.start()
    await _application.updater.start_polling(drop_pending_updates=True)
    logger.info("telegram_bot_started")


async def stop_bot() -> None:
    global _application
    if _application is None:
        return
    await _application.updater.stop()
    await _application.stop()
    await _application.shutdown()
    _application = None
    logger.info("telegram_bot_stopped")
