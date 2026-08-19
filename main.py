from __future__ import annotations
import asyncio, logging, uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from app.config import get_settings
from app.data.market import MarketData
from app.analysis.engine import analyze
from app.analysis.backtest import run_backtest
from app.storage.store import Store

settings = get_settings()
market = MarketData(settings.binance_rest_url, settings.binance_ws_url, settings.symbol_list)
store = Store(settings.database_path, settings.supabase_url, settings.supabase_auth_keys, settings.redis_url)
log = logging.getLogger("weeg.auto_signals")
AUTO_SCAN_SECONDS = 60
STORAGE_RETRY_SECONDS = 30
EXIT_SCAN_SECONDS = 5

class TradeInput(BaseModel):
    symbol: str
    direction: str
    timeframe: str = "15m"
    entry: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    confidence: float = Field(ge=0, le=100)
    risk_reward: float
    regime: str = "TRANSITION"
    structure_state: str = "NEUTRAL"
    liquidity_state: str = "UNKNOWN"
    fvg_state: str = "UNKNOWN"
    volume_state: str = "UNKNOWN"
    momentum_state: str = "UNKNOWN"

class SettingsInput(BaseModel):
    symbols: list[str] | None = None
    confidence_threshold: int | None = None
    minimum_rr: float | None = None
    risk_per_trade: float | None = None

async def _scan_and_store_auto_signals() -> list[dict]:
    saved = []
    for symbol in settings.symbol_list:
        try:
            rows = await market.ensure_history(symbol, settings.default_interval)
            result = analyze(symbol, rows, settings.default_interval, settings.confidence_threshold, settings.minimum_rr)
            if not result.get("ready") or result.get("signal") not in ("LONG", "SHORT"):
                continue
            existing = await store.find_open_auto_trade(symbol, settings.default_interval)
            if existing:
                continue
            trade = {
                "id": str(uuid.uuid4()),
                "symbol": symbol,
                "direction": result["signal"],
                "timeframe": settings.default_interval,
                "signal_time": result.get("updated_at") or datetime.now(timezone.utc).isoformat(),
                "entry": result["entry"],
                "stop_loss": result["stop_loss"],
                "take_profit_1": result["take_profit_1"],
                "take_profit_2": result["take_profit_2"],
                "risk_reward": result["rr"],
                "confidence": result["confidence"],
                "regime": result["regime"],
                "structure_state": result.get("structure"),
                "liquidity_state": result.get("liquidity"),
                "volume_state": result.get("volume"),
                "momentum_state": result.get("momentum"),
                "status": "OPEN",
                "source": "auto_signal",
                "auto_created": True,
                "asset_profile": result.get("asset_profile"),
                "signal_reasons": result.get("reasons", []),
            }
            saved.append(await store.create_trade(trade))
        except Exception as exc:
            log.warning("auto signal scan failed for %s: %s", symbol, exc)
    return saved


async def _auto_signal_loop():
    while True:
        try:
            if not store.has_persistent_storage:
                await store.check_persistent_storage()
            if store.has_persistent_storage:
                saved = await _scan_and_store_auto_signals()
                if saved:
                    log.info("saved %d automatic paper signal(s)", len(saved))
                delay = AUTO_SCAN_SECONDS
            else:
                log.warning("automatic signal scan paused: backend=%s error=%s", store.backend_name, store.storage_last_error)
                delay = STORAGE_RETRY_SECONDS
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("automatic signal loop failed: %s", exc)
            delay = STORAGE_RETRY_SECONDS
        await asyncio.sleep(delay)


def evaluate_trade_exit(trade: dict, current_price: float) -> dict | None:
    try:
        current = float(current_price)
        entry = float(trade["entry"])
        stop_loss = float(trade["stop_loss"])
        take_profit_1 = float(trade["take_profit_1"])
    except (KeyError, TypeError, ValueError):
        return None

    direction = trade.get("direction")
    if direction == "LONG":
        stopped = current <= stop_loss
        target_hit = current >= take_profit_1
        gross_pnl = (current - entry) / max(abs(entry), 1e-9) * 100
    elif direction == "SHORT":
        stopped = current >= stop_loss
        target_hit = current <= take_profit_1
        gross_pnl = (entry - current) / max(abs(entry), 1e-9) * 100
    else:
        return None

    if not stopped and not target_hit:
        return None
    reason = "STOP_LOSS" if stopped else "TAKE_PROFIT_1"
    return {
        "status": "STOPPED" if stopped else "CLOSED",
        "result": "LOSS" if stopped else "WIN",
        "pnl": round(gross_pnl, 8),
        "exit_reason": reason,
        "closed_at": datetime.now(timezone.utc).isoformat(),
    }


async def _manage_open_trades():
    while True:
        try:
            for trade in await store.list_active_trades():
                symbol = str(trade.get("symbol", "")).upper()
                price = market.tickers.get(symbol, {}).get("price")
                if not symbol or price is None:
                    continue
                patch = evaluate_trade_exit(trade, price)
                if not patch:
                    continue
                updated = await store.update_trade(str(trade["id"]), patch)
                if updated:
                    log.info("trade %s closed at %s: %s price=%s", trade.get("id"), symbol, patch["exit_reason"], price)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("trade exit manager failed: %s", exc)
        await asyncio.sleep(EXIT_SCAN_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await store.check_persistent_storage()
    await market.start()
    auto_task = asyncio.create_task(_auto_signal_loop())
    if not store.has_persistent_storage:
        log.error("automatic signal loop waiting for persistent Supabase storage; backend=%s error=%s", store.backend_name, store.storage_last_error)
    exit_task = asyncio.create_task(_manage_open_trades())
    try:
        yield
    finally:
        if auto_task:
            auto_task.cancel()
        exit_task.cancel()
        tasks = [exit_task] + ([auto_task] if auto_task else [])
        await asyncio.gather(*tasks, return_exceptions=True)
        await market.stop()

app = FastAPI(title="Weeg Crypto Trading Intelligence", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list if settings.cors_origins != "*" else ["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def index(): return FileResponse(Path("templates/index.html"))

@app.get("/api/health")
async def health():
    persistent = store.has_persistent_storage
    return {
        "status": "ok",
        "service": "weeg",
        "symbols": len(settings.symbol_list),
        "live_feed": market._task is not None,
        "storage_backend": store.backend_name,
        "supabase_url_configured": bool(settings.supabase_url),
        "supabase_key_configured": bool(settings.supabase_auth_keys),
        "supabase_key_count": store.supabase_key_count,
        "supabase_key_source": store.storage_key_source,
        "persistent_storage_configured": store.persistent_storage_configured,
        "persistent_storage": persistent,
        "storage_last_error": store.storage_last_error,
        "storage_last_check_at": store.storage_last_check_at,
        "auto_signal_enabled": persistent,
        "auto_signal_storage": persistent,
        "warning": None if persistent else "التخزين الدائم غير جاهز؛ الفحص الآلي ينتظر اتصال Supabase ولن يحفظ صفقات في SQLite المؤقت",
    }

@app.get("/api/market/candles")
async def candles(symbol: str = "BTCUSDT", interval: str = "15m", limit: int = 250):
    symbol = symbol.upper()
    if symbol not in settings.symbol_list: raise HTTPException(404, "العملة غير موجودة في القائمة")
    rows = await market.ensure_history(symbol, interval)
    return {"symbol": symbol, "interval": interval, "candles": rows[-min(limit, 500):]}

@app.get("/api/market/overview")
async def overview(interval: str = "15m"):
    async def one(symbol: str):
        try:
            rows = await market.ensure_history(symbol, interval)
            result = analyze(symbol, rows, interval, settings.confidence_threshold, settings.minimum_rr)
            result["ticker"] = market.tickers.get(symbol, {})
            return result
        except Exception as exc:
            return {"symbol": symbol, "signal": "NO TRADE", "confidence": 0, "reason": str(exc), "ready": False}
    return sorted(await asyncio.gather(*(one(s) for s in settings.symbol_list)), key=lambda x: (x.get("confidence", 0), x.get("rr", 0)), reverse=True)

@app.get("/api/signals/{symbol}")
async def signal(symbol: str, interval: str = "15m"):
    symbol = symbol.upper(); rows = await market.ensure_history(symbol, interval)
    return analyze(symbol, rows, interval, settings.confidence_threshold, settings.minimum_rr)

@app.get("/api/backtest/{symbol}")
async def backtest(symbol: str, interval: str = "15m", limit: int = 500):
    symbol = symbol.upper(); rows = await market.ensure_history(symbol, interval)
    return run_backtest(symbol, rows[-min(limit, 500):], interval, threshold=settings.confidence_threshold, minimum_rr=settings.minimum_rr)

@app.get("/api/trades")
async def trades(status: str | None = None): return await store.list_trades(status.upper() if status else None)

@app.post("/api/trades/paper")
async def create_paper_trade(payload: TradeInput):
    if payload.direction not in ("LONG", "SHORT"): raise HTTPException(400, "direction must be LONG or SHORT")
    trade = {"id": str(uuid.uuid4()), **payload.model_dump(), "symbol": payload.symbol.upper(), "status": "OPEN", "signal_time": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()}
    return await store.create_trade(trade)

@app.patch("/api/trades/{trade_id}")
async def update_trade(trade_id: str, patch: dict):
    result = await store.update_trade(trade_id, patch)
    if result is None: raise HTTPException(404, "الصفقة غير موجودة")
    return result

@app.get("/api/settings")
async def get_app_settings():
    saved = await store.get_settings()
    return {"symbols": settings.symbol_list, "confidence_threshold": settings.confidence_threshold, "minimum_rr": settings.minimum_rr, "risk_per_trade": settings.risk_per_trade, **saved}

@app.post("/api/settings")
async def save_app_settings(payload: SettingsInput):
    data = payload.model_dump(exclude_none=True)
    if "symbols" in data: data["symbols"] = [s.upper() for s in data["symbols"]]
    return await store.save_settings(data)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept(); queue = market.subscribe()
    try:
        await websocket.send_json({"type": "connected", "symbols": settings.symbol_list})
        while True: await websocket.send_json(await queue.get())
    except (WebSocketDisconnect, asyncio.CancelledError): pass
    finally: market.unsubscribe(queue)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(__import__("os").getenv("PORT", "10000")))
