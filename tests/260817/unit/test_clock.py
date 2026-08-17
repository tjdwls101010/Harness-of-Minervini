from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
import unittest

from scripts.minervini.clock import resolve_as_of


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


if __name__ == "__main__":
    unittest.main()
