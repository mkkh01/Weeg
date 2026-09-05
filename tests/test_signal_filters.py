import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.analysis.engine import apply_signal_filters


class SignalFilterTests(unittest.TestCase):
    def base(self, signal, **overrides):
        result = {
            "signal": signal,
            "ready": True,
            "confidence": 90,
            "regime": "TRENDING_UP",
            "asset_profile": "major",
            "reasons": [],
        }
        result.update(overrides)
        return result

    def test_short_is_disabled_by_default(self):
        result = apply_signal_filters(self.base("SHORT"))
        self.assertEqual(result["signal"], "NO TRADE")
        self.assertFalse(result["ready"])
        self.assertIn("SHORT معطل تشغيليًا", result["filter_vetoes"])

    def test_short_can_be_enabled_explicitly(self):
        result = apply_signal_filters(self.base("SHORT"), enable_short=True)
        self.assertEqual(result["signal"], "SHORT")
        self.assertTrue(result["ready"])

    def test_long_is_blocked_in_ranging(self):
        result = apply_signal_filters(self.base("LONG", regime="RANGING"))
        self.assertEqual(result["signal"], "NO TRADE")
        self.assertIn("LONG ممنوع في نظام RANGING", result["filter_vetoes"])

    def test_long_is_blocked_below_confidence_threshold(self):
        result = apply_signal_filters(self.base("LONG", confidence=84))
        self.assertEqual(result["signal"], "NO TRADE")
        self.assertIn("الثقة أقل من 85 المطلوبة لـ LONG", result["filter_vetoes"])

    def test_long_is_blocked_for_mid_cap_by_default(self):
        result = apply_signal_filters(self.base("LONG", asset_profile="mid_cap"))
        self.assertEqual(result["signal"], "NO TRADE")
        self.assertIn("LONG ممنوع للأصول من ملف mid_cap", result["filter_vetoes"])

    def test_long_requires_fvg_when_enabled(self):
        result = apply_signal_filters(self.base("LONG", fvg_retest_ready=False), long_require_fvg=True)
        self.assertEqual(result["signal"], "NO TRADE")
        self.assertIn("LONG يحتاج إعادة اختبار FVG صاعد غير ممتلئ", result["filter_vetoes"])

    def test_long_passes_with_fvg_retest(self):
        result = apply_signal_filters(self.base("LONG", fvg_retest_ready=True), long_require_fvg=True)
        self.assertEqual(result["signal"], "LONG")

    def test_long_is_blocked_near_recent_high(self):
        result = apply_signal_filters(self.base("LONG", price=99.8, recent_high=100.0, atr=1.0))
        self.assertEqual(result["signal"], "NO TRADE")
        self.assertIn("LONG مرفوض قرب قمة حديثة", result["filter_vetoes"])

    def test_long_is_blocked_when_extended_above_ema(self):
        result = apply_signal_filters(self.base("LONG", price=102.0, ema20=100.0, atr=1.0))
        self.assertEqual(result["signal"], "NO TRADE")
        self.assertIn("LONG مرفوض بسبب امتداد سعري فوق EMA20", result["filter_vetoes"])

    def test_long_passes_when_policy_conditions_are_met(self):
        result = apply_signal_filters(self.base("LONG"))
        self.assertEqual(result["signal"], "LONG")
        self.assertTrue(result["ready"])
        self.assertEqual(result["filter_vetoes"], [])


if __name__ == "__main__":
    unittest.main()
