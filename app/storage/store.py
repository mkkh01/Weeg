from __future__ import annotations
import json, sqlite3
from datetime import datetime, timezone
from typing import Any
import httpx

class Store:
    def __init__(self, db_path: str, supabase_url: str | None = None, supabase_key: str | None = None, redis_url: str | None = None):
        self.db_path, self.supabase_url, self.supabase_key, self.redis_url = db_path, supabase_url, supabase_key, redis_url
        self._init_sqlite()
        self.redis = None
        if redis_url:
            try:
                import redis.asyncio as redis
                self.redis = redis.from_url(redis_url, decode_responses=True)
            except Exception: self.redis = None

    def _init_sqlite(self):
        with sqlite3.connect(self.db_path) as db:
            db.execute("create table if not exists trades (id text primary key, payload text not null, status text not null, created_at text not null)")
            db.execute("create table if not exists settings (id integer primary key check(id=1), payload text not null)")
            db.commit()

    async def _supabase(self, table: str, method: str = "GET", params: dict | None = None, data: Any = None):
        if not (self.supabase_url and self.supabase_key): return None
        headers = {"apikey": self.supabase_key, "Authorization": f"Bearer {self.supabase_key}", "Content-Type": "application/json", "Prefer": "return=representation"}
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.request(method, f"{self.supabase_url.rstrip('/')}/rest/v1/{table}", headers=headers, params=params, json=data)
            response.raise_for_status(); return response.json()

    async def list_trades(self, status: str | None = None) -> list[dict[str, Any]]:
        try:
            params = {"select": "*", "order": "signal_time.desc", "limit": "200"}
            if status: params["status"] = f"eq.{status}"
            remote = await self._supabase("weeg_trades", params=params)
            if remote is not None: return remote
        except Exception: pass
        with sqlite3.connect(self.db_path) as db:
            query = "select payload from trades"; args = []
            if status: query += " where status=?"; args.append(status)
            query += " order by created_at desc limit 200"
            return [json.loads(row[0]) for row in db.execute(query, args).fetchall()]

    async def find_open_auto_trade(self, symbol: str, timeframe: str) -> dict[str, Any] | None:
        try:
            remote = await self._supabase(
                "weeg_trades",
                params={
                    "select": "*",
                    "symbol": f"eq.{symbol.upper()}",
                    "timeframe": f"eq.{timeframe}",
                    "auto_created": "eq.true",
                    "status": "in.(PENDING,OPEN,PARTIAL)",
                    "order": "signal_time.desc",
                    "limit": "1",
                },
            )
            if remote:
                return remote[0]
        except Exception:
            pass
        with sqlite3.connect(self.db_path) as db:
            row = db.execute(
                "select payload from trades where json_extract(payload, '$.symbol')=? and json_extract(payload, '$.timeframe')=? and json_extract(payload, '$.auto_created')=1 and status in ('PENDING','OPEN','PARTIAL') order by created_at desc limit 1",
                (symbol.upper(), timeframe),
            ).fetchone()
            return json.loads(row[0]) if row else None

    async def create_trade(self, trade: dict[str, Any]) -> dict[str, Any]:
        trade = {**trade, "created_at": datetime.now(timezone.utc).isoformat()}
        try:
            remote = await self._supabase("weeg_trades", method="POST", data=trade)
            if remote: return remote[0]
        except Exception: pass
        with sqlite3.connect(self.db_path) as db:
            db.execute("insert or replace into trades(id,payload,status,created_at) values(?,?,?,?)", (trade["id"], json.dumps(trade), trade.get("status", "OPEN"), trade["created_at"]))
            db.commit()
        return trade

    async def update_trade(self, trade_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        try:
            remote = await self._supabase("weeg_trades", method="PATCH", params={"id": f"eq.{trade_id}"}, data=patch)
            if remote: return remote[0]
        except Exception: pass
        with sqlite3.connect(self.db_path) as db:
            row = db.execute("select payload from trades where id=?", (trade_id,)).fetchone()
            if not row: return None
            trade = {**json.loads(row[0]), **patch}
            db.execute("update trades set payload=?, status=? where id=?", (json.dumps(trade), trade.get("status", "OPEN"), trade_id)); db.commit()
            return trade

    async def get_settings(self) -> dict[str, Any]:
        try:
            remote = await self._supabase("weeg_settings", params={"select": "*", "limit": "1"})
            if remote: return remote[0]
        except Exception: pass
        with sqlite3.connect(self.db_path) as db:
            row = db.execute("select payload from settings where id=1").fetchone()
            return json.loads(row[0]) if row else {}

    async def save_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        try:
            remote = await self._supabase("weeg_settings", method="POST", data=settings)
            if remote: return remote[0]
        except Exception: pass
        with sqlite3.connect(self.db_path) as db:
            db.execute("insert or replace into settings(id,payload) values(1,?)", (json.dumps(settings),)); db.commit()
        return settings
