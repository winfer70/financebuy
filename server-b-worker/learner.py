"""
learner.py — TickerTap scoring accuracy analyser for Server B (REDACTED_HOST).

Standalone script that runs periodically (via systemd timer, typically weekly).
Analyses prediction outcomes to identify scoring biases and generates
calibration rules that are injected into the worker's LLM prompt.

Flow:
    1. Fetch outcome data from Server A (GET /feedback/internal/outcome-data).
    2. Compute aggregate accuracy statistics.
    3. Build an LLM analysis prompt with the statistics and sample outcomes.
    4. Call Ollama to identify patterns and generate rules.
    5. POST the new rules to Server A (POST /feedback/internal/rules).

Environment variables:
    TICKERTAP_API_URL        — Server A base URL (e.g. http://<APP_IP>:8000)
    TICKERTAP_INTERNAL_KEY   — Shared secret for X-Internal-Key header
    OLLAMA_MODEL             — Ollama model tag (default: llama3:8b-instruct-q4_K_M)
    OLLAMA_URL               — Ollama API base URL (default: http://localhost:11434)
    MIN_OUTCOMES_FOR_LEARNING — Minimum outcomes before generating rules (default: 50)
    MAX_OUTCOMES_FOR_PROMPT   — Max outcomes to include in analysis prompt (default: 50)

Usage:
    python learner.py
"""

import json
import logging
import os
import re
import sys
from collections import Counter
from typing import Dict, List, Optional

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
logger = logging.getLogger("tickertap-learner")

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------
API_URL = os.getenv("TICKERTAP_API_URL", "http://localhost:8000")
INTERNAL_KEY = os.getenv("TICKERTAP_INTERNAL_KEY", "")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3:8b-instruct-q4_K_M")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
MIN_OUTCOMES = int(os.getenv("MIN_OUTCOMES_FOR_LEARNING", "50"))
MAX_OUTCOMES_FOR_PROMPT = int(os.getenv("MAX_OUTCOMES_FOR_PROMPT", "50"))

# Server A endpoints.
_OUTCOME_ENDPOINT = f"{API_URL}/api/v1/feedback/internal/outcome-data"
_RULES_ENDPOINT = f"{API_URL}/api/v1/feedback/internal/rules"

# Ollama generation timeout.
_OLLAMA_TIMEOUT = 600  # seconds — covers the prompt-eval (prefill) phase


# ---------------------------------------------------------------------------
# Step 1: Fetch outcome data from Server A
# ---------------------------------------------------------------------------

def fetch_outcomes() -> List[Dict]:
    """Fetch score outcome records from Server A.

    Retrieves up to 2000 of the most recent outcomes, which include the
    original LLM prediction, actual price movement, and accuracy grade.

    Returns:
        List of outcome dicts from Server A.

    Raises:
        requests.RequestException: On network errors.
        RuntimeError: If Server A returns a non-200 status.
    """
    headers = {"X-Internal-Key": INTERNAL_KEY}
    resp = requests.get(
        _OUTCOME_ENDPOINT,
        headers=headers,
        params={"limit": 2000},
        timeout=30,
    )

    if resp.status_code != 200:
        raise RuntimeError(
            f"Failed to fetch outcomes: status={resp.status_code}, "
            f"body={resp.text[:300]}"
        )

    outcomes = resp.json()
    logger.info("Fetched %d outcome records from Server A.", len(outcomes))
    return outcomes


# ---------------------------------------------------------------------------
# Step 2: Compute aggregate statistics
# ---------------------------------------------------------------------------

def compute_statistics(outcomes: List[Dict]) -> Dict:
    """Compute aggregate accuracy statistics from outcome data.

    Breaks down accuracy by grade, score_type, source, and predicted score
    magnitude to identify systematic biases.

    Args:
        outcomes: List of outcome dicts from Server A.

    Returns:
        Dict with accuracy metrics and breakdowns.
    """
    total = len(outcomes)
    if total == 0:
        return {}

    # Overall grade distribution.
    grades = Counter(o["accuracy_grade"] for o in outcomes)
    correct_or_close = grades.get("correct", 0) + grades.get("close", 0)
    overall_accuracy = round((correct_or_close / total) * 100, 1)

    # By score_type.
    by_type = {}
    for score_type in ("general", "ticker"):
        type_outcomes = [o for o in outcomes if o["score_type"] == score_type]
        if type_outcomes:
            type_correct = sum(
                1 for o in type_outcomes
                if o["accuracy_grade"] in ("correct", "close")
            )
            by_type[score_type] = round(
                (type_correct / len(type_outcomes)) * 100, 1
            )

    # By source.
    by_source = {}
    for source in ("yahoo", "google", "finviz", "marketwatch"):
        source_outcomes = [o for o in outcomes if o.get("article_source") == source]
        if source_outcomes:
            source_correct = sum(
                1 for o in source_outcomes
                if o["accuracy_grade"] in ("correct", "close")
            )
            by_source[source] = round(
                (source_correct / len(source_outcomes)) * 100, 1
            )

    # Predicted vs actual direction analysis.
    bullish_predictions = [o for o in outcomes if o["predicted_score"] > 0]
    bearish_predictions = [o for o in outcomes if o["predicted_score"] < 0]
    neutral_predictions = [o for o in outcomes if o["predicted_score"] == 0]

    # Average magnitude analysis.
    avg_predicted = (
        sum(abs(o["predicted_score"]) for o in outcomes) / total
    )
    non_null_changes = [
        o for o in outcomes if o.get("actual_change_pct") is not None
    ]
    avg_actual_change = 0.0
    if non_null_changes:
        avg_actual_change = sum(
            abs(float(o["actual_change_pct"])) for o in non_null_changes
        ) / len(non_null_changes)

    return {
        "total": total,
        "overall_accuracy": overall_accuracy,
        "grades": dict(grades),
        "by_type": by_type,
        "by_source": by_source,
        "bullish_count": len(bullish_predictions),
        "bearish_count": len(bearish_predictions),
        "neutral_count": len(neutral_predictions),
        "avg_predicted_magnitude": round(avg_predicted, 2),
        "avg_actual_change_pct": round(avg_actual_change, 2),
    }


# ---------------------------------------------------------------------------
# Step 3: Build the LLM analysis prompt
# ---------------------------------------------------------------------------

def build_analysis_prompt(stats: Dict, outcomes: List[Dict]) -> str:
    """Build a prompt for the LLM to analyse scoring patterns and biases.

    Includes aggregate statistics and a sample of recent outcomes for
    the LLM to identify systematic prediction errors.

    Args:
        stats:    Aggregate accuracy statistics from compute_statistics().
        outcomes: Full list of outcomes (will be truncated for the prompt).

    Returns:
        Formatted prompt string for the LLM.
    """
    # Format sample outcomes (limit to MAX_OUTCOMES_FOR_PROMPT).
    sample = outcomes[:MAX_OUTCOMES_FOR_PROMPT]
    sample_lines = []
    for o in sample:
        title = (o.get("article_title") or "Untitled")[:60]
        pred = o["predicted_score"]
        actual = o.get("actual_change_pct", "N/A")
        grade = o["accuracy_grade"]
        ticker = o["ticker"]
        score_type = o["score_type"]
        sample_lines.append(
            f"  {title} | {score_type}/{ticker} | "
            f"predicted={pred:+d} | actual={actual}% | {grade}"
        )

    sample_text = "\n".join(sample_lines)

    prompt = f"""You are analysing the scoring accuracy of a financial news AI. Your goal is to identify systematic biases and produce calibration rules that improve future predictions.

=== ACCURACY STATISTICS ===
Total outcomes analysed: {stats['total']}
Overall accuracy (correct + close): {stats['overall_accuracy']}%
Grade distribution: {stats['grades']}

By score type:
  General (SPY market): {stats.get('by_type', {}).get('general', 'N/A')}%
  Ticker-specific: {stats.get('by_type', {}).get('ticker', 'N/A')}%

By news source:
  Yahoo: {stats.get('by_source', {}).get('yahoo', 'N/A')}%
  Google: {stats.get('by_source', {}).get('google', 'N/A')}%
  Finviz: {stats.get('by_source', {}).get('finviz', 'N/A')}%
  MarketWatch: {stats.get('by_source', {}).get('marketwatch', 'N/A')}%

Prediction distribution:
  Bullish predictions: {stats['bullish_count']}
  Bearish predictions: {stats['bearish_count']}
  Neutral predictions: {stats['neutral_count']}

Magnitude analysis:
  Average predicted magnitude (abs score): {stats['avg_predicted_magnitude']}
  Average actual price change (abs %): {stats['avg_actual_change_pct']}%

=== SAMPLE OUTCOMES (most recent {len(sample)}) ===
{sample_text}

=== TASK ===
Analyse these patterns and produce scoring calibration rules. Focus on:
1. Direction bias — are predictions consistently too bullish or bearish?
2. Magnitude calibration — are extreme scores (+/-4 or 5) well calibrated?
3. Source reliability — should certain news sources be scored differently?
4. Score type accuracy — general vs ticker-specific patterns
5. Common failure patterns — what types of articles get scored incorrectly?

Return ONLY valid JSON:
{{
  "rules": [
    "Rule 1: description of calibration adjustment",
    "Rule 2: description of calibration adjustment"
  ],
  "analysis_summary": "Brief paragraph summarising key findings",
  "estimated_accuracy_impact": "How these rules should improve accuracy"
}}

Keep rules concise and actionable (max 10 rules). Each rule should be a clear instruction the scoring model can follow. Return valid JSON only, no markdown or explanation."""

    return prompt


# ---------------------------------------------------------------------------
# Step 4: Call Ollama for analysis
# ---------------------------------------------------------------------------

def analyse_with_ollama(prompt: str) -> Dict:
    """Call the local Ollama API to analyse scoring patterns.

    Uses streaming mode so that tokens arrive incrementally, keeping the
    HTTP connection alive on slow CPU-only hardware.  The read timeout
    applies per-chunk rather than to the entire generation, preventing
    false timeouts on long inferences.

    Args:
        prompt: Analysis prompt with statistics and sample outcomes.

    Returns:
        Parsed dict with keys: rules, analysis_summary, estimated_accuracy_impact.

    Raises:
        ValueError: If the LLM response cannot be parsed as valid JSON.
        requests.RequestException: On network/connection errors.
    """
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": True,
        "options": {
            "temperature": 0.3,   # Slightly higher than scoring for creativity
            "num_predict": 1024,  # Allow longer analysis output
        },
    }

    logger.info("Calling Ollama for accuracy analysis (streaming)...")

    # Use a (connect, read) timeout tuple.  The read timeout applies to
    # each chunk, not the total request — streaming keeps it alive.
    resp = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json=payload,
        timeout=(30, _OLLAMA_TIMEOUT),
        stream=True,
    )
    resp.raise_for_status()

    # Collect streamed tokens.  Ollama sends one JSON object per line;
    # each has a "response" field with the next token fragment and a
    # "done" boolean that is True on the final line.
    fragments: List[str] = []
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
    logger.info("Ollama analysis complete — received %d tokens.", token_count)
    return _parse_analysis_json(raw_text)


def _parse_analysis_json(raw_text: str) -> Dict:
    """Extract and parse JSON from the LLM analysis response.

    Handles markdown code fences, trailing commas, and preamble text.

    Args:
        raw_text: Raw text response from the LLM.

    Returns:
        Parsed dict with validated structure.

    Raises:
        ValueError: If no valid JSON can be extracted.
    """
    text = raw_text.strip()

    # Strip markdown code fences if present.
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()

    # Find the outermost JSON object.
    brace_start = text.find("{")
    if brace_start == -1:
        raise ValueError(f"No JSON found in LLM analysis response: {raw_text[:200]}")

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
        raise ValueError(f"Unmatched braces in LLM analysis: {raw_text[:200]}")

    json_str = text[brace_start : brace_end + 1]
    json_str = re.sub(r",\s*([}\]])", r"\1", json_str)

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON from LLM analysis: {e}") from e

    # Validate structure.
    rules = data.get("rules", [])
    if not isinstance(rules, list):
        rules = []
    # Ensure each rule is a string.
    rules = [str(r) for r in rules if r][:10]

    return {
        "rules": rules,
        "analysis_summary": str(data.get("analysis_summary", "")),
        "estimated_accuracy_impact": str(data.get("estimated_accuracy_impact", "")),
    }


# ---------------------------------------------------------------------------
# Step 5: POST rules to Server A
# ---------------------------------------------------------------------------

def post_rules(rules_text: str, analysis_summary: str, sample_size: int,
               accuracy_before: float) -> Dict:
    """Submit new calibration rules to Server A.

    Args:
        rules_text:       Formatted rules string for the LLM prompt.
        analysis_summary: Learner's analysis of scoring patterns.
        sample_size:      Number of outcomes that were analysed.
        accuracy_before:  Overall accuracy % before these rules.

    Returns:
        Response dict from Server A with the new rule version.

    Raises:
        RuntimeError: If Server A rejects the POST.
    """
    headers = {
        "Content-Type": "application/json",
        "X-Internal-Key": INTERNAL_KEY,
    }

    payload = {
        "rules_text": rules_text,
        "analysis_summary": analysis_summary,
        "sample_size": sample_size,
        "accuracy_before": accuracy_before,
    }

    resp = requests.post(
        _RULES_ENDPOINT,
        json=payload,
        headers=headers,
        timeout=30,
    )

    if resp.status_code not in (200, 201):
        raise RuntimeError(
            f"Failed to post rules: status={resp.status_code}, "
            f"body={resp.text[:300]}"
        )

    result = resp.json()
    logger.info(
        "New scoring rules v%s activated on Server A.",
        result.get("rule_version"),
    )
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Entry point: fetch outcomes, analyse patterns, generate and post rules.

    Exits early if there aren't enough outcomes to derive meaningful patterns.
    """
    logger.info("=" * 60)
    logger.info("TickerTap Scoring Learner starting")
    logger.info("  Server A URL:  %s", API_URL)
    logger.info("  Ollama URL:    %s", OLLAMA_URL)
    logger.info("  Ollama model:  %s", OLLAMA_MODEL)
    logger.info("  Min outcomes:  %d", MIN_OUTCOMES)
    logger.info("=" * 60)

    if not INTERNAL_KEY:
        logger.error("TICKERTAP_INTERNAL_KEY is not set. Cannot communicate with Server A.")
        sys.exit(1)

    # 1. Fetch outcome data.
    try:
        outcomes = fetch_outcomes()
    except Exception as exc:
        logger.error("Failed to fetch outcomes: %s", exc)
        sys.exit(1)

    # 2. Check minimum data threshold.
    if len(outcomes) < MIN_OUTCOMES:
        logger.info(
            "Only %d outcomes available (need %d). Exiting — not enough data "
            "for meaningful analysis.",
            len(outcomes),
            MIN_OUTCOMES,
        )
        sys.exit(0)

    # 3. Compute statistics.
    stats = compute_statistics(outcomes)
    logger.info(
        "Statistics: accuracy=%.1f%%, grades=%s",
        stats["overall_accuracy"],
        stats["grades"],
    )

    # 4. Build prompt and call Ollama.
    prompt = build_analysis_prompt(stats, outcomes)
    try:
        analysis = analyse_with_ollama(prompt)
    except ValueError as exc:
        logger.error("LLM analysis parse error: %s", exc)
        sys.exit(1)
    except requests.RequestException as exc:
        logger.error("Ollama connection error: %s", exc)
        sys.exit(1)

    rules = analysis.get("rules", [])
    if not rules:
        logger.info("LLM produced no rules. Exiting.")
        sys.exit(0)

    # 5. Format rules and post to Server A.
    rules_text = "\n".join(f"- {rule}" for rule in rules)
    logger.info("Generated %d rules:\n%s", len(rules), rules_text)

    try:
        post_rules(
            rules_text=rules_text,
            analysis_summary=analysis.get("analysis_summary", ""),
            sample_size=stats["total"],
            accuracy_before=stats["overall_accuracy"],
        )
    except RuntimeError as exc:
        logger.error("Failed to post rules: %s", exc)
        sys.exit(1)

    logger.info("Learner completed successfully.")


if __name__ == "__main__":
    main()
