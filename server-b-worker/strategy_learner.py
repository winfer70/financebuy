"""
strategy_learner.py — Strategy performance learner for Server B (Kali).

Analyses historical backtest outcomes to identify which strategy/parameter
combinations work best in which market regimes, and posts learned insights
to Server A.  These insights are used by the strategy researcher and
displayed to users on the TradingPage.

Flow:
    1. Fetch historical backtest results from Server A (aggregated).
    2. Group by strategy + regime → compute per-group statistics.
    3. Build an LLM prompt with the grouped statistics.
    4. Call Ollama to derive strategy-regime fitness rules.
    5. POST the learned rules to Server A.

Environment variables:
    TICKERTAP_API_URL        — Server A base URL
    TICKERTAP_INTERNAL_KEY   — Shared secret for X-Internal-Key header
    OLLAMA_MODEL             — Ollama model tag
    OLLAMA_URL               — Ollama API base URL
    MIN_BACKTESTS_FOR_LEARNING — Minimum backtests before learning (default: 20)

Usage:
    python strategy_learner.py

Designed to run via systemd timer (weekly).
"""

import json
import logging
import os
import re
import sys
from collections import defaultdict
from typing import Dict, List

import requests

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("tickertap-strategy-learner")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
API_URL = os.getenv("TICKERTAP_API_URL", "http://localhost:8000")
INTERNAL_KEY = os.getenv("TICKERTAP_INTERNAL_KEY", "")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3:8b-instruct-q4_K_M")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
MIN_BACKTESTS = int(os.getenv("MIN_BACKTESTS_FOR_LEARNING", "20"))

_BACKTESTS_ENDPOINT = f"{API_URL}/api/v1/trading/internal/backtest-history"
_STRATEGY_RULES_ENDPOINT = f"{API_URL}/api/v1/trading/internal/strategy-rules"

_OLLAMA_TIMEOUT = 600


# ---------------------------------------------------------------------------
# Step 1: Fetch historical backtest data
# ---------------------------------------------------------------------------

def fetch_backtest_history() -> List[Dict]:
    """Fetch aggregated backtest history from Server A.

    Returns:
        List of backtest result dicts with strategy, symbol, regime,
        and performance metrics.
    """
    headers = {"X-Internal-Key": INTERNAL_KEY}
    try:
        resp = requests.get(
            _BACKTESTS_ENDPOINT,
            headers=headers,
            params={"limit": 500},
            timeout=30,
        )
        if resp.status_code != 200:
            logger.warning(
                "Failed to fetch backtest history: status=%d", resp.status_code,
            )
            return []
        data = resp.json()
        logger.info("Fetched %d historical backtest records.", len(data))
        return data
    except requests.RequestException as exc:
        logger.warning("Could not reach Server A: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Step 2: Group and compute statistics
# ---------------------------------------------------------------------------

def compute_strategy_stats(backtests: List[Dict]) -> Dict:
    """Group backtests by strategy+regime and compute aggregate metrics.

    Args:
        backtests: List of backtest result dicts.

    Returns:
        Dict mapping (strategy, regime) → aggregate performance metrics.
    """
    groups = defaultdict(list)

    for bt in backtests:
        strategy = bt.get("strategy_name", "Unknown")
        regime = bt.get("regime", "unknown")
        key = f"{strategy} | {regime}"
        groups[key].append(bt)

    stats = {}
    for key, entries in groups.items():
        n = len(entries)
        avg_return = sum(e.get("total_return_pct", 0) for e in entries) / n
        avg_sharpe = sum(e.get("sharpe_ratio", 0) for e in entries) / n
        avg_winrate = sum(e.get("win_rate", 0) for e in entries) / n
        avg_trades = sum(e.get("total_trades", 0) for e in entries) / n
        avg_drawdown = sum(e.get("max_drawdown_pct", 0) for e in entries) / n

        # Win count (positive return backtests)
        wins = sum(1 for e in entries if e.get("total_return_pct", 0) > 0)

        stats[key] = {
            "count": n,
            "avg_return": round(avg_return, 2),
            "avg_sharpe": round(avg_sharpe, 2),
            "avg_win_rate": round(avg_winrate, 1),
            "avg_trades": round(avg_trades, 1),
            "avg_drawdown": round(avg_drawdown, 2),
            "backtest_win_pct": round((wins / n) * 100, 1),
        }

    return stats


# ---------------------------------------------------------------------------
# Step 3: Build learning prompt
# ---------------------------------------------------------------------------

def build_learning_prompt(stats: Dict) -> str:
    """Build the LLM prompt for strategy-regime fitness learning.

    Args:
        stats: Per strategy+regime aggregate statistics.

    Returns:
        Formatted prompt string.
    """
    stat_lines = []
    for key, s in sorted(stats.items(), key=lambda x: x[1]["avg_sharpe"], reverse=True):
        stat_lines.append(
            f"  {key}: n={s['count']}, return={s['avg_return']:+.1f}%, "
            f"sharpe={s['avg_sharpe']:.2f}, win_rate={s['avg_win_rate']:.0f}%, "
            f"drawdown={s['avg_drawdown']:.1f}%, backtest_wins={s['backtest_win_pct']:.0f}%"
        )

    stat_text = "\n".join(stat_lines)

    prompt = f"""You are analysing the performance of algorithmic trading strategies across different market regimes. Your goal is to derive rules that match strategies to optimal market conditions.

=== STRATEGY x REGIME PERFORMANCE ===
Format: Strategy | Regime: count, avg_return, sharpe, win_rate, max_drawdown, backtest_win_pct
{stat_text}

=== MARKET REGIMES ===
- trending_up: Sustained uptrend, moderate volatility
- trending_down: Sustained downtrend, moderate volatility
- mean_reverting: Range-bound, choppy, oscillating
- high_volatility: Extreme volatility, news-driven

=== TASK ===
Derive rules for which strategies work best in each regime. Focus on:
1. Which strategies have positive Sharpe ratios in which regimes?
2. Which strategies should be avoided in high-volatility regimes?
3. Are trend-following strategies (SMA/EMA/MACD) better in trending regimes?
4. Are mean-reversion strategies (RSI/Bollinger) better in ranging markets?
5. Any strategies that consistently underperform everywhere?

Return ONLY valid JSON:
{{
  "strategy_rules": [
    {{
      "strategy": "strategy_name",
      "best_regimes": ["regime1", "regime2"],
      "avoid_regimes": ["regime3"],
      "notes": "Brief explanation"
    }}
  ],
  "regime_recommendations": {{
    "trending_up": ["strategy1", "strategy2"],
    "trending_down": ["strategy1"],
    "mean_reverting": ["strategy1", "strategy2"],
    "high_volatility": ["strategy1"]
  }},
  "insights": "Brief paragraph of key findings"
}}

Keep rules evidence-based — only include rules supported by the data above. Return valid JSON only."""

    return prompt


# ---------------------------------------------------------------------------
# Step 4: Call Ollama for learning
# ---------------------------------------------------------------------------

def learn_with_ollama(prompt: str) -> Dict:
    """Call Ollama to derive strategy-regime fitness rules.

    Args:
        prompt: Learning prompt with aggregated statistics.

    Returns:
        Parsed dict with strategy rules and recommendations.
    """
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": True,
        "options": {
            "temperature": 0.2,
            "num_predict": 1024,
        },
    }

    logger.info("Calling Ollama for strategy learning (streaming)...")

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
    logger.info("Learning complete — received %d tokens.", token_count)
    return _parse_learning_json(raw_text)


def _parse_learning_json(raw_text: str) -> Dict:
    """Extract and parse JSON from the LLM learning response.

    Args:
        raw_text: Raw text from Ollama.

    Returns:
        Parsed dict with strategy rules.

    Raises:
        ValueError: If no valid JSON can be extracted.
    """
    text = raw_text.strip()

    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()

    brace_start = text.find("{")
    if brace_start == -1:
        raise ValueError(f"No JSON found in learning response: {raw_text[:200]}")

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
        raise ValueError(f"Unmatched braces in learning response: {raw_text[:200]}")

    json_str = text[brace_start : brace_end + 1]
    json_str = re.sub(r",\s*([}\]])", r"\1", json_str)

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in learning output: {e}") from e

    return {
        "strategy_rules": data.get("strategy_rules", []),
        "regime_recommendations": data.get("regime_recommendations", {}),
        "insights": str(data.get("insights", "")),
    }


# ---------------------------------------------------------------------------
# Step 5: POST learned rules to Server A
# ---------------------------------------------------------------------------

def post_strategy_rules(learning_result: Dict, sample_size: int) -> bool:
    """Submit strategy-regime fitness rules to Server A.

    Args:
        learning_result: Parsed learning output.
        sample_size:     Number of backtests analysed.

    Returns:
        True on success, False on failure.
    """
    headers = {
        "Content-Type": "application/json",
        "X-Internal-Key": INTERNAL_KEY,
    }

    payload = {
        "strategy_rules": learning_result.get("strategy_rules", []),
        "regime_recommendations": learning_result.get("regime_recommendations", {}),
        "insights": learning_result.get("insights", ""),
        "sample_size": sample_size,
    }

    try:
        resp = requests.post(
            _STRATEGY_RULES_ENDPOINT,
            json=payload,
            headers=headers,
            timeout=15,
        )
        if resp.ok:
            logger.info("Posted strategy rules to Server A.")
            return True
        logger.error(
            "Server A rejected strategy rules: status=%d, body=%s",
            resp.status_code, resp.text[:300],
        )
        return False
    except requests.RequestException as exc:
        logger.error("Failed to POST strategy rules: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Entry point: fetch history, learn patterns, post rules."""
    logger.info("=" * 60)
    logger.info("TickerTap Strategy Learner starting")
    logger.info("  Server A URL:  %s", API_URL)
    logger.info("  Ollama URL:    %s", OLLAMA_URL)
    logger.info("  Ollama model:  %s", OLLAMA_MODEL)
    logger.info("  Min backtests: %d", MIN_BACKTESTS)
    logger.info("=" * 60)

    if not INTERNAL_KEY:
        logger.error("TICKERTAP_INTERNAL_KEY is not set.")
        sys.exit(1)

    # 1. Fetch historical backtest data
    backtests = fetch_backtest_history()

    if len(backtests) < MIN_BACKTESTS:
        logger.info(
            "Only %d backtests available (need %d). Exiting.",
            len(backtests), MIN_BACKTESTS,
        )
        sys.exit(0)

    # 2. Compute statistics
    stats = compute_strategy_stats(backtests)
    logger.info("Computed stats for %d strategy-regime groups.", len(stats))

    # 3. Build prompt and call Ollama
    prompt = build_learning_prompt(stats)
    try:
        result = learn_with_ollama(prompt)
    except ValueError as exc:
        logger.error("LLM learning parse error: %s", exc)
        sys.exit(1)
    except requests.RequestException as exc:
        logger.error("Ollama connection error: %s", exc)
        sys.exit(1)

    rules = result.get("strategy_rules", [])
    if not rules:
        logger.info("LLM produced no strategy rules. Exiting.")
        sys.exit(0)

    logger.info("Generated rules for %d strategies.", len(rules))

    # 4. Post to Server A
    success = post_strategy_rules(result, len(backtests))
    if not success:
        sys.exit(1)

    logger.info("Strategy learner completed successfully.")


if __name__ == "__main__":
    main()
