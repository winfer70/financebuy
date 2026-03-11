"""
api.py — Internal FastAPI service for the trading-ml container.

Exposes four inference endpoints (one per model) plus a health check.
This service is internal-only — called by the TickerTap backend and
trading worker, never exposed to end users.

Endpoints:
    GET  /health             → service health / loaded models
    POST /predict/lstm       → LSTM price direction prediction
    POST /predict/pattern    → CNN candlestick pattern classification
    POST /predict/features   → Random Forest feature classification
    POST /predict/regime     → Market regime detection (HMM + rules)
    POST /train/{model_name} → Trigger online training for a model
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from models import (
    LSTMPredictor,
    PatternClassifier,
    FeatureClassifier,
    RegimeDetector,
    REGISTRY,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("trading-ml")

app = FastAPI(title="TickerTap Trading ML", version="1.0.0")

# ---------------------------------------------------------------------------
# Singleton model instances — loaded once on startup
# ---------------------------------------------------------------------------
_lstm: Optional[LSTMPredictor] = None
_pattern: Optional[PatternClassifier] = None
_features: Optional[FeatureClassifier] = None
_regime: Optional[RegimeDetector] = None


@app.on_event("startup")
async def _load_models() -> None:
    """Instantiate all model singletons at startup."""
    global _lstm, _pattern, _features, _regime
    logger.info("Loading ML models …")
    _lstm = LSTMPredictor()
    _pattern = PatternClassifier()
    _features = FeatureClassifier()
    _regime = RegimeDetector()
    logger.info("All models loaded.")


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class OHLCVRow(BaseModel):
    """Single OHLCV bar sent in inference requests."""
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class PredictRequest(BaseModel):
    """Common request body for all prediction endpoints."""
    symbol: str = Field(..., min_length=1, max_length=10)
    bars: List[OHLCVRow] = Field(..., min_length=5)


class LSTMResponse(BaseModel):
    """LSTM predictor response."""
    direction: str  # "up" | "down" | "neutral"
    confidence: float
    predicted_return: float


class PatternResponse(BaseModel):
    """Pattern classifier response."""
    pattern: str
    confidence: float
    description: str


class FeatureResponse(BaseModel):
    """Feature classifier response."""
    signal: str  # "bullish" | "bearish" | "neutral"
    confidence: float
    top_features: List[Dict[str, Any]]


class RegimeResponse(BaseModel):
    """Regime detector response."""
    regime: str  # "trending_up" | "trending_down" | "mean_reverting" | "high_volatility"
    confidence: float
    volatility_percentile: float
    trend_strength: float


class TrainRequest(BaseModel):
    """Request body for online training."""
    symbol: str = Field(..., min_length=1, max_length=10)
    bars: List[OHLCVRow] = Field(..., min_length=30)
    labels: Optional[List[float]] = None


class TrainResponse(BaseModel):
    """Training response."""
    model: str
    status: str
    metrics: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> Dict[str, Any]:
    """Health check: returns loaded model status.

    Returns:
        Dict with service status and per-model readiness flags.
    """
    return {
        "status": "ok",
        "models": {
            "lstm_predictor": _lstm is not None,
            "pattern_classifier": _pattern is not None,
            "feature_classifier": _features is not None,
            "regime_detector": _regime is not None,
        },
    }


# ---------------------------------------------------------------------------
# Prediction endpoints
# ---------------------------------------------------------------------------

@app.post("/predict/lstm", response_model=LSTMResponse)
async def predict_lstm(req: PredictRequest) -> LSTMResponse:
    """Run the LSTM price direction predictor.

    Args:
        req: Symbol + OHLCV bars (minimum 30 bars recommended).

    Returns:
        LSTMResponse with predicted direction, confidence, and return.
    """
    if _lstm is None:
        raise HTTPException(503, "LSTM model not loaded")
    result = _lstm.predict(req.symbol, [b.model_dump() for b in req.bars])
    return LSTMResponse(**result)


@app.post("/predict/pattern", response_model=PatternResponse)
async def predict_pattern(req: PredictRequest) -> PatternResponse:
    """Run the CNN candlestick pattern classifier.

    Args:
        req: Symbol + OHLCV bars (last 20 bars used).

    Returns:
        PatternResponse with pattern name, confidence, and description.
    """
    if _pattern is None:
        raise HTTPException(503, "Pattern classifier not loaded")
    result = _pattern.predict(req.symbol, [b.model_dump() for b in req.bars])
    return PatternResponse(**result)


@app.post("/predict/features", response_model=FeatureResponse)
async def predict_features(req: PredictRequest) -> FeatureResponse:
    """Run the Random Forest feature classifier.

    Args:
        req: Symbol + OHLCV bars (minimum 50 bars recommended).

    Returns:
        FeatureResponse with signal, confidence, and top feature importances.
    """
    if _features is None:
        raise HTTPException(503, "Feature classifier not loaded")
    result = _features.predict(req.symbol, [b.model_dump() for b in req.bars])
    return FeatureResponse(**result)


@app.post("/predict/regime", response_model=RegimeResponse)
async def predict_regime(req: PredictRequest) -> RegimeResponse:
    """Run the market regime detector.

    Args:
        req: Symbol + OHLCV bars (minimum 60 bars recommended).

    Returns:
        RegimeResponse with regime type, confidence, and metrics.
    """
    if _regime is None:
        raise HTTPException(503, "Regime detector not loaded")
    result = _regime.predict(req.symbol, [b.model_dump() for b in req.bars])
    return RegimeResponse(**result)


# ---------------------------------------------------------------------------
# Training endpoints
# ---------------------------------------------------------------------------

@app.post("/train/{model_name}", response_model=TrainResponse)
async def train_model(model_name: str, req: TrainRequest) -> TrainResponse:
    """Trigger online training / model update for the specified model.

    Args:
        model_name: One of: lstm_predictor, pattern_classifier,
                    feature_classifier, regime_detector.
        req:        Training data (symbol + bars + optional labels).

    Returns:
        TrainResponse with training metrics and status.
    """
    if model_name not in REGISTRY:
        raise HTTPException(404, f"Unknown model: {model_name}")

    model_map = {
        "lstm_predictor": _lstm,
        "pattern_classifier": _pattern,
        "feature_classifier": _features,
        "regime_detector": _regime,
    }
    model = model_map.get(model_name)
    if model is None:
        raise HTTPException(503, f"Model {model_name} not loaded")

    bars_data = [b.model_dump() for b in req.bars]
    metrics = model.train(req.symbol, bars_data, req.labels)

    return TrainResponse(
        model=model_name,
        status="completed",
        metrics=metrics or {},
    )
