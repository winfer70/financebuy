"""
strategy_researcher.py — Strategy research agent for Server B (Kali).

Standalone script that periodically analyses market conditions and
backtest outcomes to suggest new strategy configurations or parameter
adjustments.  Uses the local Ollama LLM to reason about patterns.

Flow:
    1. Fetch recent backtest results from Server A.
    2. Fetch current market regime from Server A.
    3. Build a research prompt with performance data + regime context.
    4. Call Ollama to generate strategy recommendations.
    5. POST recommendations to Server A for user review.

Environment variables:
    TICKERTAP_API_URL        — Server A base URL
    TICKERTAP_INTERNAL_KEY   — Shared secret for X-Internal-Key header
    OLLAMA_MODEL             — Ollama model tag (default: llama3:8b-instruct-q4_K_M)
    OLLAMA_URL               — Ollama API base URL (default: http://localhost:11434)

Usage:
    python strategy_researcher.py

Designed to run via systemd timer (daily during off-market hours).
"""

import json
import logging
import os
import re
import sys
from typing import Dict, List

import requests

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("tickertap-strategy-researcher")

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------
API_URL = os.getenv("TICKERTAP_API_URL", "http://localhost:8000")
INTERNAL_KEY = os.getenv("TICKERTAP_INTERNAL_KEY", "")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3:8b-instruct-q4_K_M")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

_BACKTESTS_ENDPOINT = f"{API_URL}/api/v1/trading/internal/recent-backtests"
_REGIME_ENDPOINT = f"{API_URL}/api/v1/trading/internal/regime-summary"
_RECOMMENDATIONS_ENDPOINT = f"{API_URL}/api/v1/trading/internal/recommendations"

_OLLAMA_TIMEOUT = 300  # seconds


# ---------------------------------------------------------------------------
# Step 1: Fetch recent backtest summaries from Server A
# ---------------------------------------------------------------------------

def fetch_recent_backtests() -> List[Dict]:
    """Fetch summaries of recent backtests from Server A.

    Calls the internal backtests endpoint and returns a list of
    backtest summary dicts with strategy name, symbol, metrics, etc.

    Returns:
        List of backtest summary dicts.

    Raises:
        requests.RequestException: On network errors.
    """
    headers = {"X-Internal-Key": INTERNAL_KEY}
    try:
        resp = requests.get(
            _BACKTESTS_ENDPOINT,
            headers=headers,
            params={"limit": 50},
            timeout=15,
        )
        if resp.status_code != 200:
            logger.warning(
                "Failed to fetch backtests: status=%d", resp.status_code,
            )
            return []
        data = resp.json()
        logger.info("Fetched %d recent backtest summaries.", len(data))
        return data
    except requests.RequestException as exc:
        logger.warning("Could not reach Server A for backtests: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Step 2: Fetch current market regime
# ---------------------------------------------------------------------------

def fetch_regime_summary() -> Dict:
    """Fetch current market regime summary from Server A.

    Returns:
        Dict with regime, confidence, volatility, trend_strength.
    """
    headers = {"X-Internal-Key": INTERNAL_KEY}
    try:
        resp = requests.get(
            _REGIME_ENDPOINT,
            headers=headers,
            timeout=10,
        )
        if resp.status_code != 200:
            logger.warning(
                "Failed to fetch regime: status=%d", resp.status_code,
            )
            return {"regime": "unknown", "confidence": 0}
        return resp.json()
    except requests.RequestException as exc:
        logger.warning("Could not reach Server A for regime: %s", exc)
        return {"regime": "unknown", "confidence": 0}


# ---------------------------------------------------------------------------
# Step 3: Build research prompt
# ---------------------------------------------------------------------------

def build_research_prompt(
    backtests: List[Dict],
    regime: Dict,
) -> str:
    """Build the LLM prompt for strategy research.

    Provides performance data and market context so the LLM can suggest
    strategy adjustments or new approaches.

    Args:
        backtests: Recent backtest summaries.
        regime:    Current market regime data.

    Returns:
        Formatted prompt string.
    """
    # Format backtest summaries
    bt_lines = []
    for bt in backtests[:30]:
        strategy = bt.get("strategy_name", "Unknown")
        symbol = bt.get("symbol", "?")
        sharpe = bt.get("sharpe_ratio", 0)
        ret = bt.get("total_return_pct", 0)
        win = bt.get("win_rate", 0)
        trades = bt.get("total_trades", 0)
        bt_lines.append(
            f"  {strategy} on {symbol}: return={ret:+.1f}%, "
            f"sharpe={sharpe:.2f}, win_rate={win:.0f}%, trades={trades}"
        )

    bt_text = "\n".join(bt_lines) if bt_lines else "  No recent backtests available."

    regime_text = (
        f"  Regime: {regime.get('regime', 'unknown')}\n"
        f"  Confidence: {regime.get('confidence', 0):.0%}\n"
        f"  Volatility Percentile: {regime.get('volatility_percentile', 0):.0f}\n"
        f"  Trend Strength (ADX): {regime.get('trend_strength', 0):.1f}"
    )

    prompt = f"""You are an algorithmic trading strategy researcher. Analyse the following backtest performance data and current market conditions, then suggest improvements or new strategy configurations.

=== RECENT BACKTEST RESULTS ===
{bt_text}

=== CURRENT MARKET REGIME ===
{regime_text}

=== AVAILABLE STRATEGY TYPES ===
Built-in strategies: SMA Crossover, EMA Crossover, RSI Mean Reversion, MACD Crossover, Bollinger Squeeze, Stochastic, ADX Trend, VWAP Bounce, Breakout, Ichimoku

=== TASK ===
Based on the performance data and current regime:
1. Which strategies are performing well and should be continued?
2. Which strategies need parameter adjustments? Suggest specific values.
3. Are any strategies unsuitable for the current regime?
4. Suggest 1-2 new strategy configurations that would work well in the current regime.

Return ONLY valid JSON:
{{
  "recommendations": [
    {{
      "type": "adjust_params",
      "strategy": "strategy_name",
      "symbol": "TICKER",
      "reason": "Brief explanation",
      "suggested_params": {{"param_name": value}}
    }},
    {{
      "type": "new_config",
      "strategy": "strategy_name",
      "symbol": "TICKER",
      "reason": "Brief explanation",
      "suggested_params": {{"param_name": value}}
    }},
    {{
      "type": "pause",
      "strategy": "strategy_name",
      "reason": "Brief explanation"
    }}
  ],
  "regime_analysis": "Brief paragraph on how the current regime affects strategy selection",
  "overall_assessment": "Brief assessment of portfolio strategy health"
}}

Keep recommendations actionable and specific (max 8 recommendations). Return valid JSON only."""

    return prompt


# ---------------------------------------------------------------------------
# Step 4: Call Ollama for research
# ---------------------------------------------------------------------------

def research_with_ollama(prompt: str) -> Dict:
    """Call Ollama to produce strategy research recommendations.

    Uses streaming mode to handle long inference times.

    Args:
        prompt: Research prompt with performance data and market context.

    Returns:
        Parsed dict with recommendations.

    Raises:
        ValueError: If response cannot be parsed.
        requests.RequestException: On network errors.
    """
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": True,
        "options": {
            "temperature": 0.3,
            "num_predict": 1024,
        },
    }

    logger.info("Calling Ollama for strategy research (streaming)...")

    resp = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json=payload,
        timeout=(30, _OLLAMA_TIMEOUT),
        stream=True,
    )
    resp.raise_for_status()

    fragments = []
    token_count = 0
    for line in resp.iter_lines():
        if not line:
            continue
        chunk = json.loads(line)
        token = chunk.get("response", "")
        if token:
            fragments.append(token)
            token_count += 1
        if chunk.get("done"):
            break

    raw_text = "".join(fragments)
    logger.info("Research complete — received %d tokens.", token_count)
    return _parse_research_json(raw_text)


def _parse_research_json(raw_text: str) -> Dict:
    """Extract and parse JSON from the LLM research response.

    Args:
        raw_text: Raw text from Ollama.

    Returns:
        Parsed dict with recommendations.

    Raises:
        ValueError: If no valid JSON can be extracted.
    """
    text = raw_text.strip()

    # Strip markdown fences if present
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()

    brace_start = text.find("{")
    if brace_start == -1:
        raise ValueError(f"No JSON found in research response: {raw_text[:200]}")

    depth = 0
    brace_end = -1
    for i in range(brace_start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                brace_end = i
                break

    if brace_end == -1:
        raise ValueError(f"Unmatched braces in research response: {raw_text[:200]}")

    json_str = text[brace_start : brace_end + 1]
    json_str = re.sub(r",\s*([}\]])", r"\1", json_str)

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in research output: {e}") from e

    return {
        "recommendations": data.get("recommendations", [])[:8],
        "regime_analysis": str(data.get("regime_analysis", "")),
        "overall_assessment": str(data.get("overall_assessment", "")),
    }


# ---------------------------------------------------------------------------
# Step 5: POST recommendations to Server A
# ---------------------------------------------------------------------------

def post_recommendations(research_result: Dict) -> bool:
    """Submit strategy recommendations to Server A for user review.

    Args:
        research_result: Parsed research output with recommendations.

    Returns:
        True on success, False on failure.
    """
    headers = {
        "Content-Type": "application/json",
        "X-Internal-Key": INTERNAL_KEY,
    }

    try:
        resp = requests.post(
            _RECOMMENDATIONS_ENDPOINT,
            json=research_result,
            headers=headers,
            timeout=15,
        )
        if resp.ok:
            logger.info(
                "Posted %d recommendations to Server A.",
                len(research_result.get("recommendations", [])),
            )
            return True
        logger.error(
            "Server A rejected recommendations: status=%d, body=%s",
            resp.status_code, resp.text[:300],
        )
        return False
    except requests.RequestException as exc:
        logger.error("Failed to POST recommendations: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Entry point: fetch data, research, and post recommendations."""
    logger.info("=" * 60)
    logger.info("TickerTap Strategy Researcher starting")
    logger.info("  Server A URL:  %s", API_URL)
    logger.info("  Ollama URL:    %s", OLLAMA_URL)
    logger.info("  Ollama model:  %s", OLLAMA_MODEL)
    logger.info("=" * 60)

    if not INTERNAL_KEY:
        logger.error("TICKERTAP_INTERNAL_KEY is not set.")
        sys.exit(1)

    # 1. Fetch data from Server A
    backtests = fetch_recent_backtests()
    regime = fetch_regime_summary()

    if not backtests:
        logger.info("No recent backtests available. Exiting.")
        sys.exit(0)

    # 2. Build prompt and call Ollama
    prompt = build_research_prompt(backtests, regime)
    try:
        result = research_with_ollama(prompt)
    except ValueError as exc:
        logger.error("LLM research parse error: %s", exc)
        sys.exit(1)
    except requests.RequestException as exc:
        logger.error("Ollama connection error: %s", exc)
        sys.exit(1)

    recommendations = result.get("recommendations", [])
    if not recommendations:
        logger.info("LLM produced no recommendations. Exiting.")
        sys.exit(0)

    logger.info("Generated %d recommendations.", len(recommendations))

    # 3. Post to Server A
    success = post_recommendations(result)
    if not success:
        sys.exit(1)

    logger.info("Strategy researcher completed successfully.")


if __name__ == "__main__":
    main()
