from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from typing import List
from datetime import date, timedelta
import hashlib

from ..dependencies import get_current_user

router = APIRouter()


class OHLCVBar(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    is_earnings: bool = False


class QuoteOut(BaseModel):
    symbol: str
    name: str
    price: float
    open: float
    high: float
    low: float
    prev_close: float
    volume: int
    change: float
    change_pct: float


_UNIVERSE = {
    "AAPL":  {"name": "Apple Inc.",            "base": 189.45},
    "MSFT":  {"name": "Microsoft Corp.",        "base": 378.90},
    "NVDA":  {"name": "NVIDIA Corp.",           "base": 721.28},
    "TSLA":  {"name": "Tesla Inc.",             "base": 213.65},
    "AMZN":  {"name": "Amazon.com Inc.",        "base": 196.40},
    "GOOGL": {"name": "Alphabet Inc.",          "base": 172.30},
    "META":  {"name": "Meta Platforms Inc.",    "base": 492.80},
    "SPY":   {"name": "SPDR S&P 500 ETF",       "base": 583.12},
    "QQQ":   {"name": "Invesco QQQ Trust",      "base": 505.44},
    "AMD":   {"name": "Advanced Micro Devices", "base": 178.50},
}


def _r(seed: int, lo: float = 0.0, hi: float = 1.0) -> float:
    h = int(hashlib.md5(str(seed).encode()).hexdigest(), 16)
    return lo + (h % 1_000_000) / 1_000_000 * (hi - lo)


def _generate_ohlcv(symbol: str, base_price: float, years: int = 5) -> List[OHLCVBar]:
    anchor = date(2026, 2, 23)
    start = anchor - timedelta(days=years * 365)
    sym_seed = int(hashlib.md5(symbol.encode()).hexdigest(), 16) % 100_000
    price = base_price * (0.30 + _r(sym_seed, 0.0, 0.15))
    bars: List[OHLCVBar] = []
    earnings_offset = 0
    for i in range(years * 365):
        d = start + timedelta(days=i)
        if d.weekday() >= 5:
            continue
        r1 = _r(sym_seed + i * 7 + 1, -1, 1)
        r2 = _r(sym_seed + i * 7 + 2, 0, 1)
        r3 = _r(sym_seed + i * 7 + 3, 0, 1)
        shock = 0.0
        if i - earnings_offset > 62 and r3 < 0.03:
            shock = (1 if _r(sym_seed + i, 0, 1) < 0.6 else -1) * (0.03 + r2 * 0.06)
            earnings_offset = i
        price = max(1.0, price * (1 + 0.0006 + r1 * (0.013 + r2 * 0.009) + shock))
        spread = price * (0.006 + r2 * 0.018)
        op = price * (1 + _r(sym_seed + i * 7 + 4, -1, 1) * 0.005)
        hi = max(op, price) + r2 * spread * 0.7
        lo = min(op, price) - r3 * spread * 0.7
        vol = int((4e7 if base_price < 300 else 1.5e7) * (0.4 + r2 * 1.2))
        bars.append(OHLCVBar(date=d.isoformat(), open=round(op, 2), high=round(hi, 2),
                             low=round(max(0.01, lo), 2), close=round(price, 2),
                             volume=vol, is_earnings=abs(shock) > 0))
    if not bars:
        return bars
    scale = base_price / bars[-1].close
    return [OHLCVBar(date=b.date, open=round(b.open*scale,2), high=round(b.high*scale,2),
                     low=round(b.low*scale,2), close=round(b.close*scale,2),
                     volume=b.volume, is_earnings=b.is_earnings) for b in bars]


@router.get("/quote/{symbol}", response_model=QuoteOut)
async def get_quote(symbol: str, current_user: str = Depends(get_current_user)):
    sym = symbol.upper()
    info = _UNIVERSE.get(sym)
    if not info:
        raise HTTPException(status_code=404, detail=f"Symbol '{sym}' not found")
    bars = _generate_ohlcv(sym, info["base"], years=1)
    last, prev = bars[-1], bars[-2]
    chg = last.close - prev.close
    return QuoteOut(symbol=sym, name=info["name"], price=last.close, open=last.open,
                    high=last.high, low=last.low, prev_close=prev.close, volume=last.volume,
                    change=round(chg, 2), change_pct=round(chg / prev.close * 100, 2))


@router.get("/ohlcv/{symbol}", response_model=List[OHLCVBar])
async def get_ohlcv(symbol: str, years: int = Query(default=5, ge=1, le=10),
                    current_user: str = Depends(get_current_user)):
    sym = symbol.upper()
    info = _UNIVERSE.get(sym)
    if not info:
        raise HTTPException(status_code=404, detail=f"Symbol '{sym}' not found")
    return _generate_ohlcv(sym, info["base"], years=years)


@router.get("/symbols", response_model=List[dict])
async def list_symbols(current_user: str = Depends(get_current_user)):
    return [{"symbol": s, "name": i["name"], "price": i["base"]} for s, i in _UNIVERSE.items()]
