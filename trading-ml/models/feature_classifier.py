"""
models/feature_classifier.py — Random Forest feature-importance classifier.

Engineers technical-analysis features from OHLCV bars and uses a Random
Forest classifier to predict the next-bar signal direction (bullish /
bearish / neutral).  Returns the prediction plus ranked feature
importances so the user can see which indicators are most influential.

Engineered features (28):
    - Returns: 1-bar, 5-bar, 10-bar, 20-bar
    - SMA ratios: price/SMA5, price/SMA10, price/SMA20, price/SMA50
    - EMA ratios: price/EMA12, price/EMA26
    - RSI(14)
    - MACD, MACD signal
    - Bollinger %B (20, 2σ)
    - ATR(14)
    - ADX(14)
    - Volume ratio (vs 20-bar avg)
    - Stochastic %K, %D
    - On-Balance Volume (OBV) slope
    - Body ratio, Upper/Lower shadow ratios
    - Consecutive up/down bars
    - Intraday range / ATR
    - Gap up/down indicator
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import joblib

logger = logging.getLogger("trading-ml.features")

MODEL_DIR = Path("/app/checkpoints")
MIN_BARS = 50  # Minimum bars required for feature engineering

# Feature names in order
FEATURE_NAMES = [
    "ret_1", "ret_5", "ret_10", "ret_20",
    "sma5_ratio", "sma10_ratio", "sma20_ratio", "sma50_ratio",
    "ema12_ratio", "ema26_ratio",
    "rsi_14",
    "macd", "macd_signal",
    "boll_pct_b",
    "atr_14",
    "adx_14",
    "vol_ratio",
    "stoch_k", "stoch_d",
    "obv_slope",
    "body_ratio", "upper_shadow", "lower_shadow",
    "consec_up", "consec_down",
    "range_atr_ratio",
    "gap_up", "gap_down",
]


class FeatureClassifier:
    """Random Forest classifier over engineered technical features.

    On first call, if no persisted model exists, a default scikit-learn
    RandomForestClassifier is created (untrained) and will be trained
    on the provided data.

    Public methods:
        predict(symbol, bars) → dict with signal, confidence, top_features
        train(symbol, bars, labels) → dict with training metrics
    """

    def __init__(self) -> None:
        """Load or create the Random Forest model."""
        self._model = None
        self._load_model()
        if self._model is None:
            self._create_default()
        logger.info("FeatureClassifier initialised")

    def predict(self, symbol: str, bars: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Predict signal direction from engineered features.

        Args:
            symbol: Ticker symbol (for logging).
            bars:   OHLCV bar dicts (minimum MIN_BARS bars).

        Returns:
            Dict with keys: signal, confidence, top_features.
        """
        features = _engineer_features(bars)
        if features is None:
            return {
                "signal": "neutral",
                "confidence": 0.0,
                "top_features": [],
            }

        X = features[-1:].reshape(1, -1)

        try:
            probs = self._model.predict_proba(X)[0]
            classes = self._model.classes_
            pred_idx = int(np.argmax(probs))
            confidence = float(probs[pred_idx])
            signal_map = {0: "bullish", 1: "bearish", 2: "neutral"}
            signal = signal_map.get(int(classes[pred_idx]), "neutral")
        except Exception:
            # Model not yet trained — use rule-based fallback
            return self._rule_fallback(features[-1])

        # Get feature importances
        top = _get_top_features(self._model, n=5)

        return {
            "signal": signal,
            "confidence": round(confidence, 4),
            "top_features": top,
        }

    def train(
        self,
        symbol: str,
        bars: List[Dict[str, Any]],
        labels: Optional[List[float]] = None,
    ) -> Dict[str, Any]:
        """Train the Random Forest on feature data.

        Generates labels from next-bar returns if not provided.

        Args:
            symbol: Ticker for logging.
            bars:   OHLCV bars.
            labels: Optional class labels (0=bullish, 1=bearish, 2=neutral).

        Returns:
            Training metrics (accuracy, oob_score, feature importances).
        """
        features = _engineer_features(bars)
        if features is None or len(features) < 30:
            return {"status": "skipped", "reason": "insufficient_data"}

        X, y = _build_train_data(features, bars, labels)
        if len(X) < 10:
            return {"status": "skipped", "reason": "insufficient_samples"}

        from sklearn.ensemble import RandomForestClassifier

        self._model = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            min_samples_leaf=5,
            oob_score=True,
            random_state=42,
            n_jobs=-1,
        )
        self._model.fit(X, y)
        self._save_model()

        oob = self._model.oob_score_ if hasattr(self._model, "oob_score_") else 0.0
        top = _get_top_features(self._model, n=5)

        return {
            "accuracy": round(oob, 4),
            "oob_score": round(oob, 4),
            "samples": len(X),
            "top_features": top,
        }

    def _rule_fallback(self, feature_row: np.ndarray) -> Dict[str, Any]:
        """Simple rule-based signal when the model isn't trained yet.

        Args:
            feature_row: Single feature vector of shape (28,).

        Returns:
            Dict with signal, confidence, top_features.
        """
        rsi = feature_row[FEATURE_NAMES.index("rsi_14")]
        macd_val = feature_row[FEATURE_NAMES.index("macd")]

        if rsi < 30 and macd_val > 0:
            return {"signal": "bullish", "confidence": 0.55, "top_features": [{"name": "rsi_14", "importance": 0.3}]}
        if rsi > 70 and macd_val < 0:
            return {"signal": "bearish", "confidence": 0.55, "top_features": [{"name": "rsi_14", "importance": 0.3}]}
        return {"signal": "neutral", "confidence": 0.50, "top_features": []}

    def _create_default(self) -> None:
        """Create an untrained RF with the right structure."""
        from sklearn.ensemble import RandomForestClassifier
        self._model = RandomForestClassifier(
            n_estimators=100, max_depth=10, min_samples_leaf=5,
            oob_score=True, random_state=42, n_jobs=-1,
        )

    def _save_model(self) -> None:
        """Persist RF to disk via joblib."""
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        joblib.dump(self._model, MODEL_DIR / "feature_classifier.pkl")
        logger.info("Saved feature classifier model")

    def _load_model(self) -> None:
        """Load RF from disk if checkpoint exists."""
        path = MODEL_DIR / "feature_classifier.pkl"
        if path.exists():
            self._model = joblib.load(path)
            logger.info("Loaded feature classifier from %s", path)


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------

def _engineer_features(bars: List[Dict[str, Any]]) -> Optional[np.ndarray]:
    """Compute 28 technical features from OHLCV bars.

    Returns an array of shape (n_valid_bars, 28) where the first
    ~50 bars are consumed for lookback.

    Args:
        bars: OHLCV bar dicts.

    Returns:
        Feature matrix or None if insufficient data.
    """
    if len(bars) < MIN_BARS:
        return None

    closes = np.array([b["close"] for b in bars], dtype=np.float64)
    opens = np.array([b["open"] for b in bars], dtype=np.float64)
    highs = np.array([b["high"] for b in bars], dtype=np.float64)
    lows = np.array([b["low"] for b in bars], dtype=np.float64)
    volumes = np.array([b["volume"] for b in bars], dtype=np.float64)

    n = len(closes)
    rows = []

    # Pre-compute indicators
    sma5 = _sma(closes, 5)
    sma10 = _sma(closes, 10)
    sma20 = _sma(closes, 20)
    sma50 = _sma(closes, 50)
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    rsi = _rsi(closes, 14)
    macd_line, macd_sig = _macd(closes)
    bb_pctb = _bollinger_pctb(closes, 20, 2.0)
    atr = _atr(highs, lows, closes, 14)
    adx = _adx(highs, lows, closes, 14)
    stoch_k, stoch_d = _stochastic(highs, lows, closes, 14)
    obv = _obv(closes, volumes)

    start = MIN_BARS  # skip the warmup period
    for i in range(start, n):
        c = closes[i]
        if c <= 0:
            continue

        # Returns
        ret1 = (c - closes[i - 1]) / closes[i - 1] if closes[i - 1] > 0 else 0
        ret5 = (c - closes[i - 5]) / closes[i - 5] if closes[i - 5] > 0 else 0
        ret10 = (c - closes[i - 10]) / closes[i - 10] if closes[i - 10] > 0 else 0
        ret20 = (c - closes[i - 20]) / closes[i - 20] if closes[i - 20] > 0 else 0

        # SMA ratios
        sma5r = c / sma5[i] - 1 if sma5[i] > 0 else 0
        sma10r = c / sma10[i] - 1 if sma10[i] > 0 else 0
        sma20r = c / sma20[i] - 1 if sma20[i] > 0 else 0
        sma50r = c / sma50[i] - 1 if sma50[i] > 0 else 0

        # EMA ratios
        ema12r = c / ema12[i] - 1 if ema12[i] > 0 else 0
        ema26r = c / ema26[i] - 1 if ema26[i] > 0 else 0

        # Volume ratio
        vol_avg = np.mean(volumes[max(0, i - 20):i]) if i > 0 else volumes[i]
        vol_ratio = volumes[i] / vol_avg if vol_avg > 0 else 1.0

        # Candle shape
        body = abs(closes[i] - opens[i])
        rng = highs[i] - lows[i] if highs[i] > lows[i] else 0.0001
        body_r = body / rng
        upper_sh = (highs[i] - max(opens[i], closes[i])) / rng
        lower_sh = (min(opens[i], closes[i]) - lows[i]) / rng

        # Consecutive up/down
        cup, cdn = 0, 0
        for j in range(i, max(i - 10, 0), -1):
            if closes[j] > closes[j - 1]:
                cup += 1
            else:
                break
        for j in range(i, max(i - 10, 0), -1):
            if closes[j] < closes[j - 1]:
                cdn += 1
            else:
                break

        # Range vs ATR
        range_atr = rng / atr[i] if atr[i] > 0 else 1.0

        # Gap
        gap_up = 1.0 if opens[i] > closes[i - 1] * 1.005 else 0.0
        gap_dn = 1.0 if opens[i] < closes[i - 1] * 0.995 else 0.0

        # OBV slope (5-bar)
        obv_sl = (obv[i] - obv[i - 5]) / (abs(obv[i - 5]) + 1) if i >= 5 else 0

        row = [
            ret1, ret5, ret10, ret20,
            sma5r, sma10r, sma20r, sma50r,
            ema12r, ema26r,
            rsi[i],
            macd_line[i], macd_sig[i],
            bb_pctb[i],
            atr[i],
            adx[i],
            vol_ratio,
            stoch_k[i], stoch_d[i],
            obv_sl,
            body_r, upper_sh, lower_sh,
            cup, cdn,
            range_atr,
            gap_up, gap_dn,
        ]
        rows.append(row)

    if not rows:
        return None
    return np.array(rows, dtype=np.float32)


def _build_train_data(
    features: np.ndarray,
    bars: List[Dict[str, Any]],
    labels: Optional[List[float]] = None,
) -> tuple:
    """Build X, y arrays for RF training.

    Labels: 0=bullish (>+0.2%), 1=bearish (<-0.2%), 2=neutral.

    Args:
        features: Feature matrix from _engineer_features.
        bars:     Original bars (for deriving labels).
        labels:   Optional pre-computed.

    Returns:
        Tuple (X, y) of numpy arrays.
    """
    # features aligns with bars[MIN_BARS:]
    n = len(features)
    X, y = [], []

    for i in range(n - 1):
        bar_idx = MIN_BARS + i
        if bar_idx + 1 >= len(bars):
            break

        X.append(features[i])

        if labels is not None and i < len(labels):
            y.append(int(labels[i]))
        else:
            cur_c = bars[bar_idx]["close"]
            nxt_c = bars[bar_idx + 1]["close"]
            if cur_c > 0:
                ret = (nxt_c - cur_c) / cur_c
                if ret > 0.002:
                    y.append(0)
                elif ret < -0.002:
                    y.append(1)
                else:
                    y.append(2)
            else:
                y.append(2)

    if not X:
        return np.array([]), np.array([])
    return np.array(X), np.array(y)


def _get_top_features(model, n: int = 5) -> List[Dict[str, Any]]:
    """Extract top-N feature importances from the RF model.

    Args:
        model: Fitted RandomForestClassifier.
        n:     Number of top features to return.

    Returns:
        List of {name, importance} dicts sorted by importance.
    """
    if not hasattr(model, "feature_importances_"):
        return []
    importances = model.feature_importances_
    indices = np.argsort(importances)[::-1][:n]
    return [
        {"name": FEATURE_NAMES[i] if i < len(FEATURE_NAMES) else f"f{i}",
         "importance": round(float(importances[i]), 4)}
        for i in indices
    ]


# ---------------------------------------------------------------------------
# Technical indicator helpers
# ---------------------------------------------------------------------------

def _sma(data: np.ndarray, period: int) -> np.ndarray:
    """Simple Moving Average. Returns array of same length (NaN-filled start)."""
    out = np.full_like(data, 0.0)
    cumsum = np.cumsum(data)
    out[period - 1:] = (cumsum[period - 1:] - np.concatenate([[0], cumsum[:-period]])) / period
    return out

def _ema(data: np.ndarray, period: int) -> np.ndarray:
    """Exponential Moving Average."""
    out = np.zeros_like(data)
    alpha = 2.0 / (period + 1)
    out[0] = data[0]
    for i in range(1, len(data)):
        out[i] = alpha * data[i] + (1 - alpha) * out[i - 1]
    return out

def _rsi(closes: np.ndarray, period: int = 14) -> np.ndarray:
    """Relative Strength Index."""
    out = np.full_like(closes, 50.0)
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = np.zeros(len(closes))
    avg_loss = np.zeros(len(closes))
    if len(gains) >= period:
        avg_gain[period] = np.mean(gains[:period])
        avg_loss[period] = np.mean(losses[:period])
        for i in range(period + 1, len(closes)):
            avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gains[i - 1]) / period
            avg_loss[i] = (avg_loss[i - 1] * (period - 1) + losses[i - 1]) / period
        for i in range(period, len(closes)):
            if avg_loss[i] == 0:
                out[i] = 100.0
            else:
                rs = avg_gain[i] / avg_loss[i]
                out[i] = 100.0 - 100.0 / (1.0 + rs)
    return out

def _macd(closes: np.ndarray) -> tuple:
    """MACD line and signal line."""
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd_line = ema12 - ema26
    macd_signal = _ema(macd_line, 9)
    return macd_line, macd_signal

def _bollinger_pctb(closes: np.ndarray, period: int = 20, num_std: float = 2.0) -> np.ndarray:
    """Bollinger Bands %B."""
    out = np.full_like(closes, 0.5)
    for i in range(period, len(closes)):
        window = closes[i - period:i]
        mean = np.mean(window)
        std = np.std(window)
        upper = mean + num_std * std
        lower = mean - num_std * std
        bw = upper - lower
        out[i] = (closes[i] - lower) / bw if bw > 0 else 0.5
    return out

def _atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> np.ndarray:
    """Average True Range."""
    out = np.zeros(len(closes))
    tr = np.zeros(len(closes))
    for i in range(1, len(closes)):
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
    if len(tr) > period:
        out[period] = np.mean(tr[1:period + 1])
        for i in range(period + 1, len(tr)):
            out[i] = (out[i - 1] * (period - 1) + tr[i]) / period
    return out

def _adx(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> np.ndarray:
    """Average Directional Index (simplified)."""
    out = np.zeros(len(closes))
    atr_arr = _atr(highs, lows, closes, period)
    plus_dm = np.zeros(len(closes))
    minus_dm = np.zeros(len(closes))
    for i in range(1, len(closes)):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm[i] = up if up > down and up > 0 else 0
        minus_dm[i] = down if down > up and down > 0 else 0
    smooth_plus = _ema(plus_dm, period)
    smooth_minus = _ema(minus_dm, period)
    for i in range(period, len(closes)):
        if atr_arr[i] > 0:
            di_plus = (smooth_plus[i] / atr_arr[i]) * 100
            di_minus = (smooth_minus[i] / atr_arr[i]) * 100
            di_sum = di_plus + di_minus
            if di_sum > 0:
                out[i] = abs(di_plus - di_minus) / di_sum * 100
    return out

def _stochastic(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> tuple:
    """Stochastic %K and %D."""
    k = np.full_like(closes, 50.0)
    for i in range(period, len(closes)):
        high_max = np.max(highs[i - period:i])
        low_min = np.min(lows[i - period:i])
        rng = high_max - low_min
        k[i] = ((closes[i] - low_min) / rng * 100) if rng > 0 else 50.0
    d = _sma(k, 3)
    return k, d

def _obv(closes: np.ndarray, volumes: np.ndarray) -> np.ndarray:
    """On-Balance Volume."""
    out = np.zeros(len(closes))
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            out[i] = out[i - 1] + volumes[i]
        elif closes[i] < closes[i - 1]:
            out[i] = out[i - 1] - volumes[i]
        else:
            out[i] = out[i - 1]
    return out
