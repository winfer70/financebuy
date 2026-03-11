"""
models/__init__.py — ML model registry for the trading-ml container.

Re-exports model classes and provides a lazy-loading registry so
``api.py`` can instantiate models by name without hard-coding imports.

Available models:
    - LSTMPredictor      — LSTM-based price direction predictor
    - PatternClassifier   — 1D-CNN candlestick pattern classifier
    - FeatureClassifier   — Random Forest feature-importance classifier
    - RegimeDetector      — HMM + rule-based market regime detector
"""

from .lstm_predictor import LSTMPredictor
from .pattern_classifier import PatternClassifier
from .feature_classifier import FeatureClassifier
from .regime_detector import RegimeDetector

REGISTRY = {
    "lstm_predictor": LSTMPredictor,
    "pattern_classifier": PatternClassifier,
    "feature_classifier": FeatureClassifier,
    "regime_detector": RegimeDetector,
}

__all__ = [
    "LSTMPredictor",
    "PatternClassifier",
    "FeatureClassifier",
    "RegimeDetector",
    "REGISTRY",
]
