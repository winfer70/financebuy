"""
sentiment.py — Financial sentiment classification for TickerTap.

Loads the ProsusAI/FinBERT model (purpose-built for financial text) as a
singleton pipeline.  Exposes `classify_headlines()` to batch-classify
headline strings into positive / negative / neutral with confidence scores.

If the model fails to load (missing torch, download error, OOM) the module
degrades gracefully — every headline is labelled "neutral" with score 0.0.
"""

import logging
from typing import Dict, List

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model singleton — loaded once on first import, reused across requests.
# ---------------------------------------------------------------------------
_pipeline = None
_load_failed = False


def _load_model():
    """Attempt to load the FinBERT sentiment-analysis pipeline.

    Returns:
        A transformers Pipeline object, or None if loading fails.
    """
    global _pipeline, _load_failed
    if _pipeline is not None:
        return _pipeline
    if _load_failed:
        return None
    try:
        from transformers import pipeline as hf_pipeline

        logger.info("Loading FinBERT sentiment model (first request may download ~440 MB)…")
        _pipeline = hf_pipeline(
            "sentiment-analysis",
            model="ProsusAI/finbert",
            tokenizer="ProsusAI/finbert",
            device=-1,  # CPU-only; use 0 for GPU if available
        )
        logger.info("FinBERT model loaded successfully.")
        return _pipeline
    except Exception as exc:
        logger.warning("Failed to load FinBERT model — sentiment will default to neutral: %s", exc)
        _load_failed = True
        return None


def classify_headlines(headlines: List[str]) -> List[Dict]:
    """Classify a batch of financial headlines as positive/negative/neutral.

    Args:
        headlines: List of headline strings to classify.

    Returns:
        List of dicts with keys ``label`` (str) and ``score`` (float 0–1).
        Label is one of "positive", "negative", "neutral".
        On model failure every entry returns {"label": "neutral", "score": 0.0}.
    """
    if not headlines:
        return []

    neutral_fallback = {"label": "neutral", "score": 0.0}
    pipe = _load_model()
    if pipe is None:
        return [neutral_fallback.copy() for _ in headlines]

    try:
        # Truncate headlines to avoid tokeniser overflow (FinBERT max 512 tokens).
        truncated = [h[:512] for h in headlines]
        results = pipe(truncated, batch_size=32, truncation=True)
        # Normalise labels to lowercase ("Positive" → "positive").
        return [
            {"label": r["label"].lower(), "score": round(r["score"], 4)}
            for r in results
        ]
    except Exception as exc:
        logger.warning("Sentiment classification failed: %s", exc)
        return [neutral_fallback.copy() for _ in headlines]
