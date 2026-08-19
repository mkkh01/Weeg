import asyncio

from app.telegram import TelegramNotifier


def test_telegram_disabled_does_not_send():
    result = asyncio.run(TelegramNotifier(None, None).send_message("test"))
    assert result == {"sent": 0, "failed": 0}


def test_trade_open_message_contains_mtf_snapshot():
    notifier = TelegramNotifier(None, None)
    message = notifier.format_trade_opened({
        "symbol": "BTCUSDT",
        "direction": "LONG",
        "timeframe": "15m",
        "entry": 100,
        "stop_loss": 98,
        "take_profit_1": 104,
        "take_profit_2": 106,
        "risk_reward": 2,
        "confidence": 82,
        "mtf_alignment": "ALIGNED",
        "mtf_timeframes": {
            "4h": {"signal": "LONG"},
            "1h": {"signal": "LONG"},
            "15m": {"signal": "LONG"},
        },
    })
    assert "BTCUSDT" in message
    assert "MTF: ALIGNED" in message
    assert "4h=LONG" in message


def test_trade_close_message_contains_exit_data():
    notifier = TelegramNotifier(None, None)
    message = notifier.format_trade_closed({
        "symbol": "BTCUSDT",
        "direction": "LONG",
        "exit_reason": "TAKE_PROFIT_1",
        "entry": 100,
        "exit_price": 104,
        "result": "WIN",
        "pnl": 4,
        "closed_at": "2026-08-19T20:00:00+00:00",
    })
    assert "سعر الخروج: 104" in message
    assert "النتيجة: WIN" in message
    assert "TAKE_PROFIT_1" in message
