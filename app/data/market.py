from __future__ import annotations
import asyncio, json, logging, urllib.parse
from collections import defaultdict, deque
from typing import Any
import httpx
import websockets

log = logging.getLogger("weeg.market")

class MarketData:
    def __init__(self, rest_url: str, ws_url: str, symbols: list[str]):
        self.rest_url, self.ws_url, self.symbols = rest_url.rstrip("/"), ws_url, symbols
        self.candles: dict[tuple[str, str], deque] = defaultdict(lambda: deque(maxlen=500))
        self.tickers: dict[str, dict[str, Any]] = {}
        self._task: asyncio.Task | None = None
        self._listeners: set[asyncio.Queue] = set()

    async def load_history(self, symbol: str, interval: str, limit: int = 250) -> list[dict[str, Any]]:
        url = f"{self.rest_url}/api/v3/klines"
        params = urllib.parse.urlencode({"symbol": symbol, "interval": interval, "limit": min(limit, 1000)})
        try:
            async with httpx.AsyncClient(timeout=15, headers={"User-Agent": "Mozilla/5.0 Weeg/1.0", "Accept": "application/json"}) as client:
                response = await client.get(url, params={"symbol": symbol, "interval": interval, "limit": min(limit, 1000)})
                response.raise_for_status(); rows = response.json()
        except Exception:
            process = await asyncio.create_subprocess_exec("curl", "-sSfL", "-A", "Mozilla/5.0 Weeg/1.0", f"{url}?{params}", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, stderr = await process.communicate()
            if process.returncode != 0: raise RuntimeError(stderr.decode(errors="ignore")[:240])
            rows = json.loads(stdout.decode())
        result = [{"time": int(r[0] / 1000), "open": float(r[1]), "high": float(r[2]), "low": float(r[3]), "close": float(r[4]), "volume": float(r[5]), "closed": True} for r in rows]
        self.candles[(symbol, interval)].clear(); self.candles[(symbol, interval)].extend(result)
        if result: self.tickers[symbol] = {"symbol": symbol, "price": result[-1]["close"], "change": 0.0, "volume": result[-1]["volume"], "updated_at": result[-1]["time"]}
        return result

    async def ensure_history(self, symbol: str, interval: str) -> list[dict[str, Any]]:
        cached = list(self.candles[(symbol, interval)])
        return cached if len(cached) >= 30 else await self.load_history(symbol, interval)

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._listeners.add(queue); return queue

    def unsubscribe(self, queue: asyncio.Queue): self._listeners.discard(queue)

    async def _broadcast(self, event: dict[str, Any]):
        for queue in list(self._listeners):
            try: queue.put_nowait(event)
            except asyncio.QueueFull: pass

    async def start(self):
        if self._task is None: self._task = asyncio.create_task(self._run())

    async def stop(self):
        if self._task: self._task.cancel(); await asyncio.gather(self._task, return_exceptions=True)

    async def _run(self):
        streams = "/".join(f"{s.lower()}@kline_1m" for s in self.symbols)
        url = f"{self.ws_url}?streams={streams}"
        delay = 1
        while True:
            try:
                async with websockets.connect(url, ping_interval=20, ping_timeout=20, close_timeout=5) as socket:
                    delay = 1
                    async for raw in socket:
                        payload = json.loads(raw); data = payload.get("data", {}); k = data.get("k")
                        if not k: continue
                        symbol, interval = k["s"], k["i"]
                        candle = {"time": int(k["t"] / 1000), "open": float(k["o"]), "high": float(k["h"]), "low": float(k["l"]), "close": float(k["c"]), "volume": float(k["v"]), "closed": bool(k["x"])}
                        cache = self.candles[(symbol, interval)]
                        if cache and cache[-1]["time"] == candle["time"]: cache[-1] = candle
                        else: cache.append(candle)
                        previous = cache[-2]["close"] if len(cache) > 1 else candle["close"]
                        self.tickers[symbol] = {"symbol": symbol, "price": candle["close"], "change": (candle["close"] - previous) / max(previous, 1e-9) * 100, "volume": candle["volume"], "updated_at": candle["time"]}
                        await self._broadcast({"type": "candle", "symbol": symbol, "interval": interval, "candle": candle, "ticker": self.tickers[symbol]})
            except asyncio.CancelledError: raise
            except Exception as exc:
                log.warning("market websocket reconnect: %s", exc)
                await asyncio.sleep(delay); delay = min(delay * 2, 30)
