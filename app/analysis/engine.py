from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any
import math


def _ema(values: list[float], period: int) -> list[float]:
    if not values: return []
    alpha = 2 / (period + 1)
    out = [values[0]]
    for value in values[1:]: out.append(alpha * value + (1 - alpha) * out[-1])
    return out


def _rsi(values: list[float], period: int = 14) -> float:
    if len(values) < period + 1: return 50.0
    gains, losses = [], []
    for a, b in zip(values[-period-1:-1], values[-period:]):
        delta = b - a
        gains.append(max(delta, 0)); losses.append(max(-delta, 0))
    avg_gain = sum(gains) / period; avg_loss = sum(losses) / period
    if avg_loss == 0: return 100.0 if avg_gain else 50.0
    return 100 - (100 / (1 + avg_gain / avg_loss))


def _atr(candles: list[dict[str, float]], period: int = 14) -> float:
    if len(candles) < 2: return 0.0
    trs = []
    for prev, cur in zip(candles[:-1], candles[1:]):
        trs.append(max(cur["high"] - cur["low"], abs(cur["high"] - prev["close"]), abs(cur["low"] - prev["close"])))
    return sum(trs[-period:]) / min(period, len(trs))


def _swing_state(candles: list[dict[str, float]], lookback: int = 3) -> tuple[str, list[dict[str, Any]]]:
    if len(candles) < lookback * 2 + 3: return "NEUTRAL", []
    points = []
    for i in range(lookback, len(candles) - lookback):
        high = candles[i]["high"]; low = candles[i]["low"]
        if high == max(c["high"] for c in candles[i-lookback:i+lookback+1]): points.append({"index": i, "price": high, "kind": "high"})
        if low == min(c["low"] for c in candles[i-lookback:i+lookback+1]): points.append({"index": i, "price": low, "kind": "low"})
    highs = [p["price"] for p in points if p["kind"] == "high"]
    lows = [p["price"] for p in points if p["kind"] == "low"]
    if len(highs) >= 2 and len(lows) >= 2:
        if highs[-1] > highs[-2] and lows[-1] > lows[-2]: return "BULLISH", points[-8:]
        if highs[-1] < highs[-2] and lows[-1] < lows[-2]: return "BEARISH", points[-8:]
    return "NEUTRAL", points[-8:]


def _regime(closes: list[float], atr: float) -> str:
    if len(closes) < 30: return "TRANSITION"
    fast, slow = _ema(closes, 20)[-1], _ema(closes, 50)[-1]
    drift = (closes[-1] - closes[-20]) / max(closes[-20], 1e-9)
    vol = atr / max(closes[-1], 1e-9)
    if vol > 0.035: return "HIGH_VOLATILITY"
    if vol < 0.004: return "LOW_VOLATILITY"
    if fast > slow and drift > 0.01: return "TRENDING_UP"
    if fast < slow and drift < -0.01: return "TRENDING_DOWN"
    if abs(drift) < 0.008: return "RANGING"
    return "TRANSITION"


def _fmt(v: float) -> float:
    return round(float(v), 8)


def analyze(symbol: str, candles: list[dict[str, float]], interval: str = "15m", threshold: int = 65, minimum_rr: float = 2.0) -> dict[str, Any]:
    if len(candles) < 30:
        return {"symbol": symbol, "signal": "NO TRADE", "confidence": 0, "reason": "بيانات غير كافية", "ready": False}
    closes = [float(c["close"]) for c in candles]
    current = closes[-1]; atr = _atr(candles); rsi = _rsi(closes)
    structure, swings = _swing_state(candles)
    regime = _regime(closes, atr)
    ema20, ema50 = _ema(closes, 20)[-1], _ema(closes, 50)[-1]
    avg_vol = sum(float(c["volume"]) for c in candles[-20:]) / 20
    rel_vol = float(candles[-1]["volume"]) / max(avg_vol, 1e-9)
    direction = "LONG" if structure == "BULLISH" and ema20 >= ema50 else "SHORT" if structure == "BEARISH" and ema20 <= ema50 else "NEUTRAL"
    structure_score = 25 if structure != "NEUTRAL" else 10
    htf_score = 20 if direction != "NEUTRAL" and ((direction == "LONG" and regime == "TRENDING_UP") or (direction == "SHORT" and regime == "TRENDING_DOWN")) else 10 if direction != "NEUTRAL" else 5
    liquidity_score = 15 if len(swings) >= 3 else 8
    momentum_score = 15 if (direction == "LONG" and rsi >= 52 and rsi < 78) or (direction == "SHORT" and rsi <= 48 and rsi > 22) else 7
    volume_score = 10 if rel_vol >= 0.85 else 5
    volatility_score = 10 if 0.004 <= atr / max(current, 1e-9) <= 0.035 else 5
    confidence = round(structure_score + htf_score + liquidity_score + momentum_score + volume_score + volatility_score)
    risk_buffer = max(atr * 1.2, current * 0.0025)
    entry = current
    if direction == "LONG":
        sl = current - risk_buffer; tp1 = current + risk_buffer * 2; tp2 = current + risk_buffer * 3
    elif direction == "SHORT":
        sl = current + risk_buffer; tp1 = current - risk_buffer * 2; tp2 = current - risk_buffer * 3
    else:
        sl = current - risk_buffer; tp1 = current + risk_buffer * 2; tp2 = current + risk_buffer * 3
    rr = abs(tp1 - entry) / max(abs(entry - sl), 1e-9)
    reasons = []
    if structure != "NEUTRAL": reasons.append(f"هيكل {structure}")
    if regime in ("TRENDING_UP", "TRENDING_DOWN"): reasons.append(f"نظام سوق {regime}")
    if rel_vol >= 0.85: reasons.append("الحجم النسبي مؤكد")
    if (direction == "LONG" and rsi >= 52) or (direction == "SHORT" and rsi <= 48): reasons.append("الزخم مؤكد")
    reasons.append(f"RR={rr:.2f}")
    signal = direction if direction != "NEUTRAL" and confidence >= threshold and rr >= minimum_rr else "NO TRADE"
    if signal == "NO TRADE":
        if direction == "NEUTRAL": reasons.append("لا يوجد توافق متعدد العوامل")
        if confidence < threshold: reasons.append(f"الثقة أقل من {threshold}")
    return {"symbol": symbol, "interval": interval, "price": _fmt(current), "regime": regime, "htf_trend": "BULLISH" if ema20 > ema50 else "BEARISH", "structure": structure, "liquidity": "SWING CLUSTERS" if swings else "UNKNOWN", "momentum": "CONFIRMED" if momentum_score >= 15 else "WEAK", "volume": "CONFIRMED" if volume_score >= 10 else "WEAK", "confidence": confidence, "signal": signal, "entry": _fmt(entry), "stop_loss": _fmt(sl), "take_profit_1": _fmt(tp1), "take_profit_2": _fmt(tp2), "rr": round(rr, 2), "reasons": reasons, "ready": True, "updated_at": datetime.now(timezone.utc).isoformat()}
