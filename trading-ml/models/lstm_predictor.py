"""
models/lstm_predictor.py — LSTM price direction predictor.

Uses a 2-layer LSTM network to predict the next-bar price direction
(up / down / neutral) from a sequence of OHLCV bars.  Features are
normalised returns and volume ratios computed from the raw bars.

Architecture:
    Input  → [seq_len × n_features] normalised returns
    LSTM   → 2 layers, hidden_dim=64, dropout=0.2
    Linear → 3-class softmax (up / down / neutral)

The model supports:
    - ``predict(symbol, bars)``  → inference on a bar sequence
    - ``train(symbol, bars, labels)`` → online training with new data
    - ``save()`` / ``load()``    → persist to / restore from disk
"""

from __future__ import annotations

import logging
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger("trading-ml.lstm")

# Model persistence directory
MODEL_DIR = Path("/app/checkpoints")

# Hyperparameters
SEQ_LEN = 30        # Number of bars per input sequence
N_FEATURES = 5      # open_ret, high_ret, low_ret, close_ret, vol_ratio
HIDDEN_DIM = 64
NUM_LAYERS = 2
DROPOUT = 0.2
NUM_CLASSES = 3      # up, down, neutral
NEUTRAL_THRESHOLD = 0.002  # ±0.2% treated as neutral


class LSTMPredictor:
    """LSTM-based next-bar price direction predictor.

    Instantiation creates the network architecture.  If a saved
    checkpoint exists in ``/app/checkpoints/lstm_predictor.pt``, it
    is loaded automatically.

    Public methods:
        predict(symbol, bars) → dict with direction, confidence, predicted_return
        train(symbol, bars, labels) → dict with loss, accuracy metrics
    """

    def __init__(self) -> None:
        """Initialise the LSTM model, loading a checkpoint if available."""
        try:
            import torch
            import torch.nn as nn
            self._torch = torch
            self._nn = nn
            self._device = torch.device("cpu")

            self._model = _LSTMNet(
                N_FEATURES, HIDDEN_DIM, NUM_LAYERS, NUM_CLASSES, DROPOUT,
            ).to(self._device)

            self._available = True
            self._load_checkpoint()
            logger.info("LSTMPredictor initialised (params=%d)",
                        sum(p.numel() for p in self._model.parameters()))
        except ImportError:
            logger.warning("PyTorch not available — LSTMPredictor disabled")
            self._available = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def predict(self, symbol: str, bars: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Predict next-bar direction from OHLCV bars.

        Args:
            symbol: Ticker symbol (for logging only).
            bars:   List of OHLCV dicts (minimum SEQ_LEN bars).

        Returns:
            Dict with keys: direction, confidence, predicted_return.
        """
        if not self._available:
            return {"direction": "neutral", "confidence": 0.0, "predicted_return": 0.0}

        features = _bars_to_features(bars)
        if features is None or len(features) < SEQ_LEN:
            return {"direction": "neutral", "confidence": 0.0, "predicted_return": 0.0}

        # Take the most recent SEQ_LEN bars
        seq = features[-SEQ_LEN:]
        tensor = self._torch.tensor(seq, dtype=self._torch.float32).unsqueeze(0).to(self._device)

        self._model.eval()
        with self._torch.no_grad():
            logits = self._model(tensor)
            probs = self._torch.softmax(logits, dim=1).squeeze().cpu().numpy()

        # Classes: 0=up, 1=down, 2=neutral
        pred_idx = int(np.argmax(probs))
        labels = ["up", "down", "neutral"]
        confidence = float(probs[pred_idx])

        # Estimate predicted return from recent momentum
        closes = [b.get("close", 0) for b in bars[-5:]]
        if len(closes) >= 2 and closes[-2] > 0:
            recent_return = (closes[-1] - closes[-2]) / closes[-2]
        else:
            recent_return = 0.0

        return {
            "direction": labels[pred_idx],
            "confidence": round(confidence, 4),
            "predicted_return": round(recent_return * confidence, 6),
        }

    def train(
        self,
        symbol: str,
        bars: List[Dict[str, Any]],
        labels: Optional[List[float]] = None,
    ) -> Dict[str, Any]:
        """Online training with new OHLCV data.

        Generates labels from actual next-bar returns if *labels* is
        not provided.  Runs a few epochs of SGD over the data.

        Args:
            symbol: Ticker for logging.
            bars:   Training OHLCV bars.
            labels: Optional pre-computed labels (0=up, 1=down, 2=neutral).

        Returns:
            Dict with training metrics (loss, accuracy).
        """
        if not self._available:
            return {"status": "skipped", "reason": "pytorch_unavailable"}

        import torch
        import torch.nn as nn

        features = _bars_to_features(bars)
        if features is None or len(features) < SEQ_LEN + 1:
            return {"status": "skipped", "reason": "insufficient_data"}

        # Build sequences and labels
        X, y = _build_sequences(features, bars, SEQ_LEN, labels)
        if len(X) == 0:
            return {"status": "skipped", "reason": "no_valid_sequences"}

        X_tensor = torch.tensor(X, dtype=torch.float32).to(self._device)
        y_tensor = torch.tensor(y, dtype=torch.long).to(self._device)

        # Train for a few epochs
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
            "epochs": epochs,
        }

    # ------------------------------------------------------------------
    # Checkpoint persistence
    # ------------------------------------------------------------------

    def _save_checkpoint(self) -> None:
        """Save model weights to disk."""
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        path = MODEL_DIR / "lstm_predictor.pt"
        self._torch.save(self._model.state_dict(), path)
        logger.info("Saved LSTM checkpoint to %s", path)

    def _load_checkpoint(self) -> None:
        """Load model weights from disk if checkpoint exists."""
        path = MODEL_DIR / "lstm_predictor.pt"
        if path.exists():
            self._model.load_state_dict(
                self._torch.load(path, map_location=self._device, weights_only=True),
            )
            logger.info("Loaded LSTM checkpoint from %s", path)


# ---------------------------------------------------------------------------
# Internal: PyTorch model definition
# ---------------------------------------------------------------------------

class _LSTMNet:
    """PyTorch LSTM network — defined via lazy class to defer import."""
    pass


# Redefine properly once torch is importable
try:
    import torch
    import torch.nn as nn

    class _LSTMNet(nn.Module):
        """2-layer LSTM with a classification head.

        Args:
            input_dim:  Number of input features per timestep.
            hidden_dim: LSTM hidden state size.
            num_layers: Number of stacked LSTM layers.
            num_classes: Output classes (up / down / neutral).
            dropout:    Dropout between LSTM layers.
        """

        def __init__(
            self,
            input_dim: int,
            hidden_dim: int,
            num_layers: int,
            num_classes: int,
            dropout: float,
        ) -> None:
            super().__init__()
            self.lstm = nn.LSTM(
                input_dim, hidden_dim, num_layers,
                batch_first=True, dropout=dropout if num_layers > 1 else 0,
            )
            self.fc = nn.Linear(hidden_dim, num_classes)

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            """Forward pass: sequence → class logits.

            Args:
                x: Input tensor of shape (batch, seq_len, input_dim).

            Returns:
                Logits tensor of shape (batch, num_classes).
            """
            out, _ = self.lstm(x)
            # Use the last hidden state
            return self.fc(out[:, -1, :])

except ImportError:
    pass


# ---------------------------------------------------------------------------
# Feature engineering helpers
# ---------------------------------------------------------------------------

def _bars_to_features(bars: List[Dict[str, Any]]) -> Optional[np.ndarray]:
    """Convert OHLCV bar dicts to a normalised feature array.

    Features per bar (5):
        0: open_return  — (open - prev_close) / prev_close
        1: high_return  — (high - close) / close
        2: low_return   — (low - close) / close
        3: close_return — (close - prev_close) / prev_close
        4: vol_ratio    — volume / rolling_20_avg_volume

    Args:
        bars: List of OHLCV dicts.

    Returns:
        np.ndarray of shape (n_bars-1, 5) or None if data insufficient.
    """
    if len(bars) < 2:
        return None

    features = []
    volumes = [b.get("volume", 0) for b in bars]

    for i in range(1, len(bars)):
        prev_close = bars[i - 1].get("close", 0)
        if prev_close <= 0:
            continue

        cur = bars[i]
        o = cur.get("open", 0)
        h = cur.get("high", 0)
        low = cur.get("low", 0)
        c = cur.get("close", 0)
        v = cur.get("volume", 0)

        open_ret = (o - prev_close) / prev_close
        high_ret = (h - c) / c if c > 0 else 0
        low_ret = (low - c) / c if c > 0 else 0
        close_ret = (c - prev_close) / prev_close

        # Rolling 20-bar average volume
        start = max(0, i - 20)
        avg_vol = np.mean(volumes[start:i]) if i > 0 else v
        vol_ratio = v / avg_vol if avg_vol > 0 else 1.0

        features.append([open_ret, high_ret, low_ret, close_ret, vol_ratio])

    if not features:
        return None
    return np.array(features, dtype=np.float32)


def _build_sequences(
    features: np.ndarray,
    bars: List[Dict[str, Any]],
    seq_len: int,
    labels: Optional[List[float]] = None,
) -> tuple:
    """Build training sequences and labels from feature array.

    Labels are derived from actual next-bar returns:
        return >  NEUTRAL_THRESHOLD  → 0 (up)
        return < -NEUTRAL_THRESHOLD  → 1 (down)
        else                         → 2 (neutral)

    Args:
        features: Feature array from ``_bars_to_features``.
        bars:     Original OHLCV bar dicts.
        seq_len:  Sequence length for each sample.
        labels:   Optional pre-computed class labels.

    Returns:
        Tuple of (X, y) numpy arrays.
    """
    X_list = []
    y_list = []

    for i in range(seq_len, len(features)):
        X_list.append(features[i - seq_len : i])

        if labels is not None and i < len(labels):
            y_list.append(int(labels[i]))
        else:
            # Derive label from next-bar return (features index offset by 1 from bars)
            bar_idx = i + 1  # features[0] corresponds to bars[1]
            if bar_idx < len(bars) - 1:
                cur_close = bars[bar_idx].get("close", 0)
                next_close = bars[bar_idx + 1].get("close", 0)
                if cur_close > 0:
                    ret = (next_close - cur_close) / cur_close
                    if ret > NEUTRAL_THRESHOLD:
                        y_list.append(0)
                    elif ret < -NEUTRAL_THRESHOLD:
                        y_list.append(1)
                    else:
                        y_list.append(2)
                else:
                    y_list.append(2)
            else:
                y_list.append(2)

    # Trim to matching lengths
    min_len = min(len(X_list), len(y_list))
    if min_len == 0:
        return np.array([]), np.array([])

    return np.array(X_list[:min_len]), np.array(y_list[:min_len])
