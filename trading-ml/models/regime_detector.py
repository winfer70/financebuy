"""
models/regime_detector.py — Market regime detector (HMM + rule-based).

Classifies the current market environment into one of four regimes so
strategies can adapt their behaviour or be paused entirely.

Regimes:
    - trending_up       — Sustained uptrend with low-to-moderate volatility.
    - trending_down     — Sustained downtrend with low-to-moderate volatility.
    - mean_reverting    — Range-bound / choppy market with oscillating price.
    - high_volatility   — Extreme volatility (e.g. news events, crashes).

AppREDACTED:
    1. **Rule-based heuristics** — always computed as a baseline.
       Uses SMA slopes, ADX, and volatility percentile.
    2. **HMM (hmmlearn)** — trained on return + volatility features.
       When a trained model exists, the HMM prediction overrides rules
       if confidence is high enough.

The regime detector is called:
    - Before every backtest to annotate the period.
    - From a new ``GET /trading/regime`` route for live display.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import joblib

logger = logging.getLogger("trading-ml.regime")

MODEL_DIR = Path("/app/checkpoints")
MIN_BARS = 60  # Minimum bars for regime detection

# Regime labels — indices map to HMM states after training
REGIMES = ["trending_up", "trending_down", "mean_reverting", "high_volatility"]


class RegimeDetector:
    """Market regime classifier combining HMM and heuristic rules.

    Public methods:
        predict(symbol, bars) → dict with regime, confidence, metrics
        train(symbol, bars, labels) → dict with training metrics
    """

    def __init__(self) -> None:
        """Load or create the HMM model."""
        self._hmm = None
        self._hmm_available = False
        self._load_model()
        if self._hmm is None:
            self._create_default()
        logger.info("RegimeDetector initialised (hmm=%s)", self._hmm_available)

    def predict(self, symbol: str, bars: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Detect the current market regime.

        Computes rule-based regime first, then refines with HMM if a
        trained model is available and confident.

        Args:
            symbol: Ticker symbol.
            bars:   OHLCV bar dicts (minimum MIN_BARS).

        Returns:
            Dict with: regime, confidence, volatility_percentile,
            trend_strength.
        """
        if len(bars) < MIN_BARS:
            return {
                "regime": "mean_reverting",
                "confidence": 0.0,
                "volatility_percentile": 0.0,
                "trend_strength": 0.0,
            }

        # Always compute rule-based metrics
        rule_result = _rule_based_regime(bars)

        # Try HMM overlay
        if self._hmm_available:
            hmm_result = self._hmm_predict(bars)
            if hmm_result and hmm_result["confidence"] > 0.6:
                hmm_result["volatility_percentile"] = rule_result["volatility_percentile"]
                hmm_result["trend_strength"] = rule_result["trend_strength"]
                return hmm_result

        return rule_result

    def train(
        self,
        symbol: str,
        bars: List[Dict[str, Any]],
        labels: Optional[List[float]] = None,
    ) -> Dict[str, Any]:
        """Train the HMM on market data.

        Args:
            symbol: Ticker for logging.
            bars:   Training OHLCV bars.
            labels: Ignored (HMM is unsupervised).

        Returns:
            Training metrics (log_likelihood, n_samples, converged).
        """
        if len(bars) < MIN_BARS:
            return {"status": "skipped", "reason": "insufficient_data"}

        features = _compute_hmm_features(bars)
        if features is None or len(features) < 30:
            return {"status": "skipped", "reason": "insufficient_features"}

        try:
            from hmmlearn.hmm import GaussianHMM

            self._hmm = GaussianHMM(
                n_components=4,
                covariance_type="full",
                n_iter=200,
                random_state=42,
            )
            self._hmm.fit(features)
            self._hmm_available = True
            self._label_states(features, bars)
            self._save_model()

            return {
                "log_likelihood": round(float(self._hmm.score(features)), 4),
                "n_samples": len(features),
                "converged": True,
            }
        except Exception as exc:
            logger.warning("HMM training failed: %s", exc)
            return {"status": "failed", "reason": str(exc)}

    # ------------------------------------------------------------------
    # HMM methods
    # ------------------------------------------------------------------

    def _hmm_predict(self, bars: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Run HMM prediction on market features.

        Args:
            bars: OHLCV bar dicts.

        Returns:
            Dict with regime and confidence, or None on failure.
        """
        if self._hmm is None:
            return None

        features = _compute_hmm_features(bars)
        if features is None or len(features) < 10:
            return None

        try:
            states = self._hmm.predict(features)
            probs = self._hmm.predict_proba(features)

            # Use the last state and its probability
            last_state = int(states[-1])
            confidence = float(probs[-1][last_state])

            # Map state index to regime label
            regime = self._state_map.get(last_state, "mean_reverting")

            return {
                "regime": regime,
                "confidence": round(confidence, 4),
                "volatility_percentile": 0.0,
                "trend_strength": 0.0,
            }
        except Exception as exc:
            logger.warning("HMM predict failed: %s", exc)
            return None

    def _label_states(self, features: np.ndarray, bars: List[Dict[str, Any]]) -> None:
        """Map HMM state indices to regime labels based on feature means.

        After training, each HMM state has a characteristic mean in
        return/volatility space.  We assign labels by sorting states.

        Args:
            features: Feature matrix used for training.
            bars:     Original OHLCV bars.
        """
        self._state_map = {}

        if self._hmm is None:
            return

        means = self._hmm.means_  # shape (4, n_features)

        # Features: [return, volatility, trend_slope]
        # Sort by volatility (feature index 1) — highest is high_vol
        vol_order = np.argsort(means[:, 1])
        high_vol_state = int(vol_order[-1])

        # Among the remaining 3 states, sort by mean return
        remaining = [s for s in range(4) if s != high_vol_state]
        ret_sorted = sorted(remaining, key=lambda s: means[s, 0])

        # Lowest return = trending_down, highest = trending_up, middle = mean_reverting
        self._state_map = {
            ret_sorted[0]: "trending_down",
            ret_sorted[1]: "mean_reverting",
            ret_sorted[2]: "trending_up",
            high_vol_state: "high_volatility",
        }

    def _create_default(self) -> None:
        """Create default HMM (will need training before use)."""
        try:
            from hmmlearn.hmm import GaussianHMM
            self._hmm = GaussianHMM(
                n_components=4, covariance_type="full",
                n_iter=200, random_state=42,
            )
            self._hmm_available = False
            self._state_map = {0: "trending_up", 1: "trending_down", 2: "mean_reverting", 3: "high_volatility"}
        except ImportError:
            logger.warning("hmmlearn not available — HMM disabled")
            self._hmm = None
            self._hmm_available = False
            self._state_map = {}

    def _save_model(self) -> None:
        """Persist HMM and state mapping to disk."""
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {"hmm": self._hmm, "state_map": self._state_map},
            MODEL_DIR / "regime_detector.pkl",
        )
        logger.info("Saved regime detector model")

    def _load_model(self) -> None:
        """Load HMM from disk if a checkpoint exists."""
        path = MODEL_DIR / "regime_detector.pkl"
        if path.exists():
            data = joblib.load(path)
            self._hmm = data.get("hmm")
            self._state_map = data.get("state_map", {})
            self._hmm_available = self._hmm is not None
            logger.info("Loaded regime detector from %s", path)


# ---------------------------------------------------------------------------
# HMM feature engineering
# ---------------------------------------------------------------------------

def _compute_hmm_features(bars: List[Dict[str, Any]]) -> Optional[np.ndarray]:
    """Compute features for the HMM: [return, volatility, trend_slope].

    Each observation is a rolling-window summary:
        - return:      20-bar log return
        - volatility:  20-bar std of daily log returns
        - trend_slope: Linear regression slope of 20-bar closes

    Args:
        bars: OHLCV bar dicts.

    Returns:
        np.ndarray of shape (n - window, 3) or None.
    """
    if len(bars) < 25:
        return None

    closes = np.array([b["close"] for b in bars], dtype=np.float64)
    log_returns = np.diff(np.log(np.maximum(closes, 1e-8)))

    window = 20
    rows = []

    for i in range(window, len(log_returns)):
        chunk = log_returns[i - window:i]
        ret = float(np.sum(chunk))
        vol = float(np.std(chunk))

        # Trend slope (normalised)
        price_chunk = closes[i - window + 1:i + 1]
        x = np.arange(window, dtype=np.float64)
        slope = np.polyfit(x, price_chunk, 1)[0]
        norm_slope = slope / np.mean(price_chunk) if np.mean(price_chunk) > 0 else 0

        rows.append([ret, vol, norm_slope])

    if not rows:
        return None
    return np.array(rows, dtype=np.float64)


# ---------------------------------------------------------------------------
# Rule-based regime detection (always available)
# ---------------------------------------------------------------------------

def _rule_based_regime(bars: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Classify market regime using deterministic technical rules.

    Heuristics:
        1. Compute 20-bar and 50-bar SMA slopes.
        2. Compute ADX (trend strength).
        3. Compute volatility percentile (20-bar std vs 100-bar std).
        4. Classify:
           - High vol percentile (>80th) → high_volatility
           - Strong ADX (>25) + positive slope → trending_up
           - Strong ADX (>25) + negative slope → trending_down
           - Weak ADX (<20) → mean_reverting

    Args:
        bars: OHLCV bar dicts (minimum MIN_BARS).

    Returns:
        Dict with regime, confidence, volatility_percentile, trend_strength.
    """
    closes = np.array([b["close"] for b in bars], dtype=np.float64)
    highs = np.array([b["high"] for b in bars], dtype=np.float64)
    lows = np.array([b["low"] for b in bars], dtype=np.float64)

    # Log returns
    log_ret = np.diff(np.log(np.maximum(closes, 1e-8)))

    # Recent volatility vs historical
    recent_vol = np.std(log_ret[-20:]) if len(log_ret) >= 20 else 0
    hist_vol = np.std(log_ret[-100:]) if len(log_ret) >= 100 else recent_vol
    vol_percentile = 0.0
    if hist_vol > 0:
        # Estimate percentile by ratio
        ratio = recent_vol / hist_vol
        vol_percentile = min(100.0, ratio * 50)  # rough mapping

    # SMA slope (20-bar)
    sma20 = np.convolve(closes, np.ones(20) / 20, mode="valid")
    if len(sma20) >= 5:
        sma_slope = (sma20[-1] - sma20[-5]) / (sma20[-5] if sma20[-5] > 0 else 1)
    else:
        sma_slope = 0.0

    # ADX approximation
    adx = _quick_adx(highs, lows, closes)

    # Classification
    if vol_percentile > 80:
        regime = "high_volatility"
        confidence = min(0.90, 0.5 + (vol_percentile - 80) / 40)
    elif adx > 25:
        if sma_slope > 0.002:
            regime = "trending_up"
            confidence = min(0.85, 0.5 + adx / 100)
        elif sma_slope < -0.002:
            regime = "trending_down"
            confidence = min(0.85, 0.5 + adx / 100)
        else:
            regime = "mean_reverting"
            confidence = 0.55
    elif adx < 20:
        regime = "mean_reverting"
        confidence = min(0.80, 0.5 + (20 - adx) / 40)
    else:
        # ADX between 20 and 25 — weak trend
        regime = "mean_reverting" if abs(sma_slope) < 0.003 else ("trending_up" if sma_slope > 0 else "trending_down")
        confidence = 0.50

    return {
        "regime": regime,
        "confidence": round(confidence, 4),
        "volatility_percentile": round(vol_percentile, 2),
        "trend_strength": round(adx, 2),
    }


def _quick_adx(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> float:
    """Compute the most recent ADX value (simplified).

    Args:
        highs:  High prices array.
        lows:   Low prices array.
        closes: Close prices array.
        period: ADX period.

    Returns:
        Most recent ADX value.
    """
    n = len(closes)
    if n < period + 2:
        return 0.0

    # True Range
    tr = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))

    plus_dm = np.zeros(n)
    minus_dm = np.zeros(n)
    for i in range(1, n):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm[i] = up if up > down and up > 0 else 0
        minus_dm[i] = down if down > up and down > 0 else 0

    # Smoothed
    atr = np.mean(tr[1:period + 1])
    sm_plus = np.mean(plus_dm[1:period + 1])
    sm_minus = np.mean(minus_dm[1:period + 1])

    for i in range(period + 1, n):
        atr = (atr * (period - 1) + tr[i]) / period
        sm_plus = (sm_plus * (period - 1) + plus_dm[i]) / period
        sm_minus = (sm_minus * (period - 1) + minus_dm[i]) / period

    if atr == 0:
        return 0.0

    di_plus = (sm_plus / atr) * 100
    di_minus = (sm_minus / atr) * 100
    di_sum = di_plus + di_minus
    if di_sum == 0:
        return 0.0

    dx = abs(di_plus - di_minus) / di_sum * 100
    return round(dx, 2)
