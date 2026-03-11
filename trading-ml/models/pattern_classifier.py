"""
models/pattern_classifier.py — 1D-CNN candlestick pattern classifier.

Classifies the most recent candlestick formation from OHLCV bars into
recognised patterns (doji, hammer, engulfing, etc.) using a 1D
convolutional neural network.

Architecture:
    Input   → [window × 4] normalised OHLC ratios
    Conv1d  → 32 filters, kernel=3, ReLU
    Conv1d  → 64 filters, kernel=3, ReLU
    Pool    → AdaptiveAvgPool1d(1)
    Linear  → N_PATTERNS classes + softmax

Supported patterns:
    doji, hammer, inverted_hammer, engulfing_bull, engulfing_bear,
    morning_star, evening_star, three_white_soldiers,
    three_black_crows, spinning_top, no_pattern
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger("trading-ml.pattern")

MODEL_DIR = Path("/app/checkpoints")
WINDOW = 20  # Number of bars analysed for pattern recognition

PATTERNS = [
    "doji",
    "hammer",
    "inverted_hammer",
    "engulfing_bull",
    "engulfing_bear",
    "morning_star",
    "evening_star",
    "three_white_soldiers",
    "three_black_crows",
    "spinning_top",
    "no_pattern",
]

PATTERN_DESCRIPTIONS = {
    "doji": "Indecision candle — open and close nearly equal.",
    "hammer": "Bullish reversal — small body at top, long lower shadow.",
    "inverted_hammer": "Potential bullish reversal — small body at bottom, long upper shadow.",
    "engulfing_bull": "Bullish engulfing — large green candle fully engulfs prior red.",
    "engulfing_bear": "Bearish engulfing — large red candle fully engulfs prior green.",
    "morning_star": "Bullish reversal — three-candle pattern after a downtrend.",
    "evening_star": "Bearish reversal — three-candle pattern after an uptrend.",
    "three_white_soldiers": "Strong bullish — three consecutive large green candles.",
    "three_black_crows": "Strong bearish — three consecutive large red candles.",
    "spinning_top": "Indecision — small body with upper and lower shadows.",
    "no_pattern": "No recognisable candlestick pattern detected.",
}


class PatternClassifier:
    """1D-CNN candlestick pattern classifier.

    Uses a convolutional network on normalised OHLC ratios to detect
    candlestick patterns.  Falls back to rule-based heuristics when the
    CNN is unavailable or poorly trained.

    Public methods:
        predict(symbol, bars) → dict with pattern, confidence, description
        train(symbol, bars, labels) → dict with training metrics
    """

    def __init__(self) -> None:
        """Initialise the pattern classifier model."""
        try:
            import torch
            import torch.nn as nn
            self._torch = torch
            self._device = torch.device("cpu")
            self._model = _PatternCNN(len(PATTERNS)).to(self._device)
            self._cnn_available = True
            self._load_checkpoint()
            logger.info("PatternClassifier CNN initialised")
        except ImportError:
            logger.warning("PyTorch not available — using rule-based fallback")
            self._cnn_available = False

    def predict(self, symbol: str, bars: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Classify the most recent candlestick pattern.

        Args:
            symbol: Ticker symbol (for logging).
            bars:   OHLCV bar dicts (last WINDOW bars used).

        Returns:
            Dict with keys: pattern, confidence, description.
        """
        # Always run rule-based as a baseline
        rule_result = _rule_based_classify(bars)

        if not self._cnn_available or len(bars) < WINDOW:
            return rule_result

        features = _bars_to_ohlc_ratios(bars[-WINDOW:])
        if features is None:
            return rule_result

        tensor = self._torch.tensor(features, dtype=self._torch.float32)
        tensor = tensor.unsqueeze(0).permute(0, 2, 1)  # (1, 4, WINDOW)

        self._model.eval()
        with self._torch.no_grad():
            logits = self._model(tensor)
            probs = self._torch.softmax(logits, dim=1).squeeze().cpu().numpy()

        pred_idx = int(np.argmax(probs))
        confidence = float(probs[pred_idx])

        # If CNN is low-confidence, defer to rules
        if confidence < 0.4:
            return rule_result

        pattern = PATTERNS[pred_idx]
        return {
            "pattern": pattern,
            "confidence": round(confidence, 4),
            "description": PATTERN_DESCRIPTIONS.get(pattern, ""),
        }

    def train(
        self,
        symbol: str,
        bars: List[Dict[str, Any]],
        labels: Optional[List[float]] = None,
    ) -> Dict[str, Any]:
        """Train / fine-tune the CNN on labelled candle data.

        Args:
            symbol: Ticker for logging.
            bars:   Training OHLCV bars.
            labels: Pattern class indices (0..N_PATTERNS-1).

        Returns:
            Dict with training loss and accuracy.
        """
        if not self._cnn_available:
            return {"status": "skipped", "reason": "pytorch_unavailable"}
        if len(bars) < WINDOW + 1:
            return {"status": "skipped", "reason": "insufficient_data"}

        import torch
        import torch.nn as nn

        X, y = _build_pattern_sequences(bars, WINDOW, labels)
        if len(X) == 0:
            return {"status": "skipped", "reason": "no_valid_sequences"}

        X_tensor = torch.tensor(X, dtype=torch.float32).permute(0, 2, 1).to(self._device)
        y_tensor = torch.tensor(y, dtype=torch.long).to(self._device)

        self._model.train()
        optimizer = torch.optim.Adam(self._model.parameters(), lr=1e-3)
        criterion = nn.CrossEntropyLoss()

        total_loss = 0.0
        correct = 0
        total = 0
        epochs = 5

        for _ in range(epochs):
            optimizer.zero_grad()
            logits = self._model(X_tensor)
            loss = criterion(logits, y_tensor)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
            preds = logits.argmax(dim=1)
            correct += (preds == y_tensor).sum().item()
            total += len(y_tensor)

        self._save_checkpoint()
        return {
            "loss": round(total_loss / epochs, 6),
            "accuracy": round(correct / total, 4) if total > 0 else 0.0,
            "samples": len(X),
        }

    def _save_checkpoint(self) -> None:
        """Persist CNN weights to disk."""
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        self._torch.save(self._model.state_dict(), MODEL_DIR / "pattern_classifier.pt")

    def _load_checkpoint(self) -> None:
        """Load CNN weights if a checkpoint exists."""
        path = MODEL_DIR / "pattern_classifier.pt"
        if path.exists():
            self._model.load_state_dict(
                self._torch.load(path, map_location=self._device, weights_only=True),
            )
            logger.info("Loaded pattern classifier checkpoint")


# ---------------------------------------------------------------------------
# PyTorch model definition
# ---------------------------------------------------------------------------

try:
    import torch
    import torch.nn as nn

    class _PatternCNN(nn.Module):
        """1D-CNN for candlestick pattern classification.

        Args:
            num_classes: Number of output pattern classes.
        """

        def __init__(self, num_classes: int) -> None:
            super().__init__()
            self.conv1 = nn.Conv1d(4, 32, kernel_size=3, padding=1)
            self.conv2 = nn.Conv1d(32, 64, kernel_size=3, padding=1)
            self.pool = nn.AdaptiveAvgPool1d(1)
            self.fc = nn.Linear(64, num_classes)
            self.relu = nn.ReLU()

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            """Forward pass: (batch, 4, seq) → (batch, num_classes).

            Args:
                x: Input tensor of shape (batch, 4, seq_len).

            Returns:
                Logits tensor of shape (batch, num_classes).
            """
            x = self.relu(self.conv1(x))
            x = self.relu(self.conv2(x))
            x = self.pool(x).squeeze(-1)
            return self.fc(x)

except ImportError:
    class _PatternCNN:
        """Placeholder when PyTorch is unavailable."""
        pass


# ---------------------------------------------------------------------------
# Rule-based pattern detection (fallback / baseline)
# ---------------------------------------------------------------------------

def _rule_based_classify(bars: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Classify candlestick patterns using deterministic rules.

    Analyses the last 3 bars for common single-candle and multi-candle
    patterns.

    Args:
        bars: OHLCV bar dicts.

    Returns:
        Dict with pattern, confidence, description.
    """
    if len(bars) < 3:
        return {"pattern": "no_pattern", "confidence": 0.5, "description": PATTERN_DESCRIPTIONS["no_pattern"]}

    b = bars[-1]  # most recent bar
    o, h, low, c = b.get("open", 0), b.get("high", 0), b.get("low", 0), b.get("close", 0)
    body = abs(c - o)
    full_range = h - low if h > low else 0.0001
    body_ratio = body / full_range

    # Previous bars
    prev = bars[-2]
    po, pc = prev.get("open", 0), prev.get("close", 0)
    prev_body = abs(pc - po)

    # Doji — very small body relative to range
    if body_ratio < 0.1:
        return {"pattern": "doji", "confidence": 0.75, "description": PATTERN_DESCRIPTIONS["doji"]}

    # Hammer — small body at top, long lower shadow
    upper_shadow = h - max(o, c)
    lower_shadow = min(o, c) - low
    if body_ratio < 0.3 and lower_shadow > body * 2 and upper_shadow < body * 0.5:
        return {"pattern": "hammer", "confidence": 0.70, "description": PATTERN_DESCRIPTIONS["hammer"]}

    # Inverted hammer — small body at bottom, long upper shadow
    if body_ratio < 0.3 and upper_shadow > body * 2 and lower_shadow < body * 0.5:
        return {"pattern": "inverted_hammer", "confidence": 0.65, "description": PATTERN_DESCRIPTIONS["inverted_hammer"]}

    # Bullish engulfing
    if c > o and pc < po and c > po and o < pc and body > prev_body:
        return {"pattern": "engulfing_bull", "confidence": 0.70, "description": PATTERN_DESCRIPTIONS["engulfing_bull"]}

    # Bearish engulfing
    if c < o and pc > po and c < po and o > pc and body > prev_body:
        return {"pattern": "engulfing_bear", "confidence": 0.70, "description": PATTERN_DESCRIPTIONS["engulfing_bear"]}

    # Three white soldiers
    if len(bars) >= 3:
        b1, b2, b3 = bars[-3], bars[-2], bars[-1]
        if (b1["close"] > b1["open"] and b2["close"] > b2["open"] and
            b3["close"] > b3["open"] and b2["close"] > b1["close"] and
            b3["close"] > b2["close"]):
            return {"pattern": "three_white_soldiers", "confidence": 0.65, "description": PATTERN_DESCRIPTIONS["three_white_soldiers"]}

    # Three black crows
    if len(bars) >= 3:
        b1, b2, b3 = bars[-3], bars[-2], bars[-1]
        if (b1["close"] < b1["open"] and b2["close"] < b2["open"] and
            b3["close"] < b3["open"] and b2["close"] < b1["close"] and
            b3["close"] < b2["close"]):
            return {"pattern": "three_black_crows", "confidence": 0.65, "description": PATTERN_DESCRIPTIONS["three_black_crows"]}

    # Spinning top
    if body_ratio < 0.35 and upper_shadow > body * 0.5 and lower_shadow > body * 0.5:
        return {"pattern": "spinning_top", "confidence": 0.60, "description": PATTERN_DESCRIPTIONS["spinning_top"]}

    return {"pattern": "no_pattern", "confidence": 0.50, "description": PATTERN_DESCRIPTIONS["no_pattern"]}


# ---------------------------------------------------------------------------
# Feature helpers
# ---------------------------------------------------------------------------

def _bars_to_ohlc_ratios(bars: List[Dict[str, Any]]) -> Optional[np.ndarray]:
    """Convert bars to normalised OHLC ratios for the CNN.

    Each bar is represented as 4 features:
        body_ratio, upper_shadow_ratio, lower_shadow_ratio, close_vs_prev

    Args:
        bars: OHLCV bar dicts.

    Returns:
        np.ndarray of shape (len(bars), 4) or None.
    """
    rows = []
    for i, b in enumerate(bars):
        o, h, low, c = b.get("open", 0), b.get("high", 0), b.get("low", 0), b.get("close", 0)
        rng = h - low if h > low else 0.0001
        body = (c - o) / rng
        upper = (h - max(o, c)) / rng
        lower = (min(o, c) - low) / rng

        prev_c = bars[i - 1].get("close", c) if i > 0 else c
        close_vs_prev = (c - prev_c) / prev_c if prev_c > 0 else 0

        rows.append([body, upper, lower, close_vs_prev])

    if not rows:
        return None
    return np.array(rows, dtype=np.float32)


def _build_pattern_sequences(
    bars: List[Dict[str, Any]],
    window: int,
    labels: Optional[List[float]] = None,
) -> tuple:
    """Build windowed training sequences for the pattern CNN.

    Args:
        bars:    OHLCV bar dicts.
        window:  Bars per sample.
        labels:  Optional class labels.

    Returns:
        Tuple of (X, y) numpy arrays.
    """
    all_ratios = _bars_to_ohlc_ratios(bars)
    if all_ratios is None or len(all_ratios) < window:
        return np.array([]), np.array([])

    X = []
    y = []
    for i in range(window, len(all_ratios)):
        X.append(all_ratios[i - window : i])
        if labels is not None and i < len(labels):
            y.append(int(labels[i]))
        else:
            # Auto-label from rule-based classifier
            chunk_bars = bars[i - window : i + 1]
            result = _rule_based_classify(chunk_bars)
            idx = PATTERNS.index(result["pattern"]) if result["pattern"] in PATTERNS else len(PATTERNS) - 1
            y.append(idx)

    min_len = min(len(X), len(y))
    if min_len == 0:
        return np.array([]), np.array([])
    return np.array(X[:min_len]), np.array(y[:min_len])
