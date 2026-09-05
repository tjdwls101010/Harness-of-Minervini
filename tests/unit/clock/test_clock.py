from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
import unittest

from scripts.minervini.clock import is_regular_session_open, resolve_as_of


ET = ZoneInfo("America/New_York")


class AnalysisClockTests(unittest.TestCase):
    def test_default_uses_the_last_completed_regular_session_before_the_close(self) -> None:
        resolved = resolve_as_of(now=datetime(2026, 8, 17, 11, 0, tzinfo=ET))

        self.assertEqual(resolved.date.isoformat(), "2026-08-14")
        self.assertEqual(resolved.mode, "last_completed_session")
        self.assertTrue(resolved.completed_session)

    def test_explicit_as_of_is_preserved_as_an_audit_boundary(self) -> None:
        resolved = resolve_as_of("2026-08-12", now=datetime(2026, 8, 17, 11, 0, tzinfo=ET))

        self.assertEqual(resolved.date.isoformat(), "2026-08-12")
        self.assertEqual(resolved.mode, "explicit")
        self.assertEqual(resolved.timezone, "America/New_York")

    def test_explicit_as_of_must_name_an_actual_us_trading_session(self) -> None:
        with self.assertRaisesRegex(ValueError, "trading session"):
            resolve_as_of("2026-08-09", now=datetime(2026, 8, 17, 11, 0, tzinfo=ET))


class RegularSessionWindowTests(unittest.TestCase):
    def test_the_session_is_open_between_the_opening_bell_and_the_close(self) -> None:
        self.assertTrue(is_regular_session_open(datetime(2026, 8, 17, 11, 0, tzinfo=ET)))

    def test_premarket_and_afterhours_are_not_the_regular_session(self) -> None:
        self.assertFalse(is_regular_session_open(datetime(2026, 8, 17, 9, 29, tzinfo=ET)))
        self.assertFalse(is_regular_session_open(datetime(2026, 8, 17, 16, 0, tzinfo=ET)))
        self.assertFalse(is_regular_session_open(datetime(2026, 8, 18, 0, 57, tzinfo=ET)))

    def test_a_non_trading_day_is_never_open(self) -> None:
        self.assertFalse(is_regular_session_open(datetime(2026, 8, 15, 12, 0, tzinfo=ET)))

    def test_an_early_close_day_shuts_at_one_pm(self) -> None:
        self.assertTrue(is_regular_session_open(datetime(2026, 11, 27, 12, 59, tzinfo=ET)))
        self.assertFalse(is_regular_session_open(datetime(2026, 11, 27, 13, 0, tzinfo=ET)))


if __name__ == "__main__":
    unittest.main()
