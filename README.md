# Weeg Crypto Trading Intelligence

Weeg is a modular crypto-market analysis dashboard. It is an **analysis and paper-trading system**, not an order-execution bot and it makes no profit guarantee. The current build supports 30 USDT pairs, multi-timeframe chart loading, live 1-minute Binance WebSocket updates, explainable LONG/SHORT/NO TRADE scoring, interactive chart navigation, paper-trade journal tabs, and persistence through Supabase with SQLite fallback.

## Run locally

```bash
pip install -r requirements.txt
export SUPABASE_URL="https://<project-ref>.supabase.co"
export SUPABASE_KEY="<publishable-or-service-key>"
export REDIS_URL="redis://..."
python main.py
```

Open `http://localhost:10000`. Render uses the same `python main.py` start command from `render.yaml` and `Procfile`; the application binds to Render's `PORT` automatically. In an existing Render service, set **Language = Python**, **Build Command = `pip install -r requirements.txt`**, and **Start Command = `python main.py`**. Do not leave the service language as Rust, because Render will then run `cargo build --release` and ignore the Python build command.

## Supabase

Apply `migrations/001_weeg_schema.sql` to the selected project before enabling remote persistence. The backend uses the REST interface when `SUPABASE_URL` and `SUPABASE_KEY` are present. The schema stores settings, trade journal records, and event-ready lifecycle data. For production, use a server-side key in Render's protected environment variables and do not expose it to the browser.

## Redis

`REDIS_URL` is accepted for low-latency caching and future fan-out. The current implementation initializes the Redis client when available and keeps an in-process cache for the market stream so the app remains usable when Redis is temporarily unavailable.

## Market and analysis behavior

The market adapter loads historical candles from Binance REST and maintains a reconnecting combined WebSocket for the 30 configured symbols. Each event is normalized into UTC timestamped OHLCV data, deduplicated by candle time, and broadcast to the browser. The analysis engine calculates EMA, RSI, ATR, a swing-based structure state, market regime, volume confirmation, confluence confidence, entry, stop loss, take-profit levels, and risk/reward. Thresholds are config-driven and the engine returns `NO TRADE` when confluence or data sufficiency is inadequate.

The browser provides a TradingView-inspired layout without copying TradingView's interface: a watchlist, symbol search, timeframe controls, candle chart with pan/zoom/fit controls, signal explanation, and open/closed paper-trade tabs. The implementation is deliberately paper-only; no exchange API secret or live order endpoint is used.
