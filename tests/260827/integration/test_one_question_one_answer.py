"""Places where the same question was being answered twice, and the two answers differed.

How far a position got. Whether a window crosses a corporate action. What an audit of one
level proves about another. Whether a block that measured nothing may say it reported.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import unittest

import numpy as np
import pandas as pd

from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot, SnapshotMeta
from scripts.minervini.management_evidence import build_management_evidence
from scripts.minervini.risk import reduce_risk


AS_OF = "2025-12-31"
POSITION = {"ticker": "TEST", "mode": "active", "entry_price": 100.0, "entry_date": "2025-12-01", "as_of": AS_OF}


def run(overrides=None, *, start="2025-10-01", splits=None, split_cells=None, **request) -> dict:
    index = pd.bdate_range(start=start, end=AS_OF)
    rows = [(overrides or {}).get(stamp.date().isoformat(), (100.0, 101.0, 99.0, 100.0)) for stamp in index]
    data = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"], index=index, dtype=float)
    data["Volume"] = np.full(len(data), 1_000_000)
    data["Stock Splits"] = np.zeros(len(data))
    for session, factor in {**(splits or {}), **(split_cells or {})}.items():
        data.loc[pd.Timestamp(session), "Stock Splits"] = factor
    snapshot = ProviderSnapshot(data, SnapshotMeta(provider="fixture-prices", retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc), as_of=date.fromisoformat(AS_OF), coverage={"completed_only": True}))
    return execute("ticker.risk", {**POSITION, **request}, runtime=Runtime(price_history=lambda ticker, as_of: snapshot))


class HowFarItGotIsOneNumber(unittest.TestCase):
    def test_the_entry_session_high_is_outside_every_reading_of_the_peak(self) -> None:
        payload = run({"2025-12-01": (100.0, 150.0, 99.0, 100.0), "2025-12-02": (100.0, 110.0, 99.0, 100.0)}, stop_price=90.0, base_top=100.0)

        data = payload["data"]
        self.assertEqual(data["max_high_since_entry"], 110.0)
        self.assertEqual(data["management_evidence"]["base_extension"]["max_extension_pct"], 10.0)


class ASplitOnAWindowsFirstSessionIsOutsideIt(unittest.TestCase):
    def test_the_management_blocks_read_that_boundary_the_way_the_audit_does(self) -> None:
        after = {stamp.date().isoformat(): (50.0, 51.0, 49.0, 50.0) for stamp in pd.bdate_range(start="2025-12-04", end=AS_OF)}
        payload = run(after, splits={"2025-12-04": 2.0}, entry_price=50.0, entry_date="2025-12-04", stop_price=45.0, base_top=45.0)

        blocks = payload["data"]["management_evidence"]
        self.assertEqual(payload["data"]["completed_price_path"]["state"], "clear")
        self.assertEqual(blocks["twenty_day_average"]["close"], 50.0)
        self.assertEqual(blocks["base_extension"]["state"], "reported")


class AnUnreadableEventCellIsNotAnAbsentEvent(unittest.TestCase):
    def test_a_nan_in_the_split_column_beside_a_split_sized_fall_is_missing_evidence(self) -> None:
        after = {stamp.date().isoformat(): (50.0, 51.0, 49.0, 50.0) for stamp in pd.bdate_range(start="2025-12-15", end=AS_OF)}
        payload = run(after, split_cells={"2025-12-15": float("nan")}, stop_price=90.0)

        data = payload["data"]
        self.assertEqual(data["verdict"], "INCOMPLETE")
        self.assertEqual(data["completed_price_path"]["reason"], "corporate_action_evidence_missing")
        self.assertIsNotNone(data["max_high_withheld_reason"])


class AnAuditOfOneLevelProvesOnlyItsOwnKind(unittest.TestCase):
    def test_a_cleared_close_says_nothing_about_the_lows_a_stop_rests_under(self) -> None:
        result = reduce_risk({
            "mode": "active",
            "as_of": AS_OF,
            "entry_price": 100.0,
            "entry_date": "2025-12-01",
            "stop_price": 90.0,
            "invalidation": {"price": 95.0},
            "current_price": 100.0,
            "completed_price_path": {
                "state": "clear",
                "audits": [{"role": "invalidation", "level": 95.0, "basis": "completed_daily_close", "state": "clear", "effective_from": "2025-12-01", "through": AS_OF, "bars_checked": 23}],
            },
        })

        self.assertEqual(result["verdict"], "INCOMPLETE")
        self.assertIn("completed_price_path", result["missing"])


class ABreachThatHappenedCannotBeUnreadLater(unittest.TestCase):
    def test_an_unreadable_close_after_the_exit_does_not_erase_it(self) -> None:
        overrides = {"2025-12-02": (80.0, 81.0, 79.0, 80.0), "2025-12-03": (79.0, 80.0, 78.0, 79.0), "2025-12-15": (100.0, 101.0, 99.0, float("nan"))}
        payload = run(overrides, stop_price=60.0, management_average="ema21")

        data = payload["data"]
        self.assertEqual(data["verdict"], "SELL")
        self.assertEqual(data["failed"], ["management_average_exit"])
        self.assertEqual(data["management_evidence"]["moving_average_trail"]["ema21"]["breach_date"], "2025-12-03")


class ABlockThatMeasuredNothingSaysSo(unittest.TestCase):
    def test_a_decline_with_neither_timeframe_readable_is_unavailable(self) -> None:
        index = pd.bdate_range(start="2025-12-01", end="2025-12-30")
        data = pd.DataFrame([(100.0, 101.0, 99.0, 100.0)] * len(index), columns=["Open", "High", "Low", "Close"], index=index, dtype=float)
        data["Volume"] = np.full(len(data), 1_000_000)
        data["Stock Splits"] = np.zeros(len(data))
        result = build_management_evidence(data, entry_date=index[0].date(), as_of=date.fromisoformat(AS_OF), stage2_start=date.fromisoformat(AS_OF))

        self.assertEqual(result["largest_decline_since_stage2_start"]["state"], "unavailable")


class ASuppliedRecordMustMatchTheRequestItIsAbout(unittest.TestCase):
    def supplied(self, path: dict, **request) -> dict:
        return run({}, completed_price_path=path, **request)

    def test_a_record_naming_no_role_is_not_a_record(self) -> None:
        payload = self.supplied({"state": "breached", "checked_level": 95.0, "breach_date": "2025-12-10"}, invalidation={"price": 95.0})

        self.assertNotEqual(payload["data"]["verdict"], "SELL")

    def test_a_record_whose_level_is_not_the_declared_one_is_not_a_record(self) -> None:
        payload = self.supplied({"state": "breached", "governing_role": "stop", "checked_level": 100.0, "breach_date": "2025-12-10"}, stop_price=94.0)

        self.assertNotEqual(payload["data"]["verdict"], "SELL")

    def test_a_record_dated_outside_the_position_is_not_a_record(self) -> None:
        payload = self.supplied({"state": "breached", "governing_role": "stop", "checked_level": 94.0, "breach_date": "2026-01-10"}, stop_price=94.0)

        self.assertNotEqual(payload["data"]["verdict"], "SELL")


if __name__ == "__main__":
    unittest.main()
