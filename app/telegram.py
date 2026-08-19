from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger("weeg.telegram")


class TelegramNotifier:
    def __init__(self, bot_token: str | None, chat_id: str | None):
        self.bot_token = (bot_token or "").strip() or None
        self.chat_id = (chat_id or "").strip() or None

    @property
    def configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def _url(self) -> str:
        return f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

    async def send_message(self, text: str) -> dict[str, int]:
        if not self.configured:
            return {"sent": 0, "failed": 0}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    self._url(),
                    json={
                        "chat_id": self.chat_id,
                        "text": text,
                        "disable_web_page_preview": True,
                    },
                )
                response.raise_for_status()
            return {"sent": 1, "failed": 0}
        except Exception as exc:
            log.warning("telegram delivery failed: %s", type(exc).__name__)
            return {"sent": 0, "failed": 1}

    @staticmethod
    def format_trade_opened(trade: dict[str, Any]) -> str:
        frames = trade.get("mtf_timeframes") or {}
        alignment = trade.get("mtf_alignment") or "—"
        return "\n".join(
            (
                "Weeg | فتح صفقة ورقية",
                f"العملة: {trade.get('symbol', '—')}",
                f"الاتجاه: {trade.get('direction', '—')}",
                f"الإطار: {trade.get('timeframe', '—')}",
                f"الدخول: {trade.get('entry', '—')}",
                f"وقف الخسارة: {trade.get('stop_loss', '—')}",
                f"TP1: {trade.get('take_profit_1', '—')}",
                f"TP2: {trade.get('take_profit_2', '—')}",
                f"RR: {trade.get('risk_reward', '—')} | الثقة: {trade.get('confidence', '—')}%",
                f"MTF: {alignment} | 4h={frames.get('4h', {}).get('signal', '—')} | 1h={frames.get('1h', {}).get('signal', '—')} | 15m={frames.get('15m', {}).get('signal', '—')}",
                f"الوقت: {trade.get('created_at') or trade.get('signal_time') or '—'}",
            )
        )

    @staticmethod
    def format_trade_closed(trade: dict[str, Any]) -> str:
        result = trade.get("result") or ("WIN" if trade.get("status") == "CLOSED" else "LOSS")
        return "\n".join(
            (
                "Weeg | إغلاق صفقة ورقية",
                f"العملة: {trade.get('symbol', '—')}",
                f"الاتجاه: {trade.get('direction', '—')}",
                f"السبب: {trade.get('exit_reason', '—')}",
                f"الدخول: {trade.get('entry', '—')}",
                f"سعر الخروج: {trade.get('exit_price', '—')}",
                f"النتيجة: {result}",
                f"PnL: {trade.get('pnl', '—')}%",
                f"وقت الخروج: {trade.get('closed_at', '—')}",
            )
        )

    async def trade_opened(self, trade: dict[str, Any]) -> dict[str, int]:
        return await self.send_message(self.format_trade_opened(trade))

    async def trade_closed(self, trade: dict[str, Any]) -> dict[str, int]:
        return await self.send_message(self.format_trade_closed(trade))
