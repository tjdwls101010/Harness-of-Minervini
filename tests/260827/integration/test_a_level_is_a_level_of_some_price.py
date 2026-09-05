"""Where the record and the price beside it have to agree.

Four rules meet here. A stop is a price you transact at and an invalidation is a threshold
price has to go through, so one includes its level and the other does not. Within one
session the Low prints before the close, so a stop and an invalidation broken on the same
day did not break in the same order as their levels. A window refused for a coordinate-system
break is refused for the price handed in too. And whichever observation the record was built
from is the one that has to be published beside it.
"""

from __future__ import annotations

from tests.providers import rows_snapshot

from datetime import date, datetime, timezone
import unittest
import numpy as np
import pandas as pd

from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot


AS_OF = "2025-12-31"
POSITION = {"ticker": "TEST", "mode": "active", "entry_price": 100.0, "entry_date": "2025-12-01", "as_of": AS_OF}


def snapshot(index: pd.DatetimeIndex, rows: list[tuple[float, float, float, float]], *, splits: dict[str, float] | None = None) -> ProviderSnapshot[pd.DataFrame]:
    data = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"], index=index, dtype=float)
    data["Volume"] = np.full(len(data), 1_000_000)
    data["Stock Splits"] = np.zeros(len(data))
    for session, factor in (splits or {}).items():
        data.loc[pd.Timestamp(session), "Stock Splits"] = factor
    return rows_snapshot(data, provider="fixture-prices", retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc), as_of=date.fromisoformat(AS_OF), coverage={"completed_only": True})


def run(overrides: dict[str, tuple[float, float, float, float]], *, start: str = "2025-11-03", end: str = AS_OF, splits: dict[str, float] | None = None, **request) -> dict:
    index = pd.bdate_range(start=start, end=end)
    rows = [overrides.get(stamp.date().isoformat(), (100.0, 101.0, 99.0, 100.0)) for stamp in index]
    return execute("ticker.risk", {**POSITION, **request}, runtime=Runtime(price_history=lambda ticker, as_of: snapshot(index, rows, splits=splits)))


class AThresholdIsCrossedRatherThanTouched(unittest.TestCase):
    def test_a_close_exactly_at_the_invalidation_has_not_gone_below_it(self) -> None:
        payload = run(
            {"2025-12-10": (96.0, 97.0, 94.0, 95.0)},
            stop_price=90.0,
            invalidation={"price": 95.0, "condition": "completed close below 95"},
        )

        self.assertNotIn("invalidation_breach", payload["data"]["failed"])
        audits = {audit["role"]: audit for audit in payload["data"]["completed_price_path"]["audits"]}
        self.assertEqual(audits["invalidation"]["state"], "clear")

    def test_a_last_close_exactly_at_the_invalidation_has_not_gone_below_it(self) -> None:
        # The same equality reached the other way: not a price handed in, but the last close
        # the provider returned, which is what the reducer reads as the current price.
        payload = run(
            {AS_OF: (96.0, 97.0, 94.0, 95.0)},
            stop_price=90.0,
            invalidation={"price": 95.0, "condition": "completed close below 95"},
        )

        self.assertEqual(payload["data"]["current_price"], 95.0)
        self.assertNotIn("invalidation_breach", payload["data"]["failed"])
        self.assertEqual(payload["data"]["verdict"], "HOLD")

    def test_a_price_exactly_at_the_stop_did_reach_the_order(self) -> None:
        # The other side of the same rule, read from a price rather than a bar: an order
        # resting at 90 is filled by a print of 90.
        payload = run({}, stop_price=90.0, current_price=90.0)

        self.assertEqual(payload["data"]["verdict"], "SELL")
        self.assertEqual(payload["data"]["failed"], ["completed_stop_breach"])

    def test_a_low_exactly_at_the_stop_did_reach_the_order(self) -> None:
        payload = run({"2025-12-10": (100.0, 101.0, 90.0, 100.0)}, stop_price=90.0)

        self.assertEqual(payload["data"]["failed"], ["completed_stop_breach"])
        self.assertEqual(payload["data"]["completed_price_path"]["breach_date"], "2025-12-10")


class WithinOneSessionTheLowPrintsFirst(unittest.TestCase):
    def test_a_stop_taken_out_intraday_owns_a_session_the_close_also_invalidated(self) -> None:
        payload = run(
            {"2025-12-10": (100.0, 101.0, 89.0, 94.0)},
            stop_price=90.0,
            invalidation={"price": 95.0, "condition": "completed close below 95"},
        )

        data = payload["data"]
        self.assertEqual(data["failed"], ["completed_stop_breach"])
        path = data["completed_price_path"]
        self.assertEqual(path["governing_role"], "stop")
        self.assertEqual(path["basis"], "completed_daily_low")
        self.assertEqual(path["checked_level"], 90.0)
        self.assertEqual(path["breach_low"], 89.0)

    def test_two_low_based_levels_broken_together_are_still_named_by_the_higher(self) -> None:
        payload = run(
            {"2025-12-20": (100.0, 101.0, 88.0, 100.0)},
            stop_price=90.0,
            initial_stop_price=94.0,
            stop_effective_date="2025-12-15",
        )

        self.assertEqual(payload["data"]["completed_price_path"]["governing_role"], "initial_stop")
        self.assertEqual(payload["data"]["completed_price_path"]["checked_level"], 94.0)


class ARefusedWindowRefusesThePriceToo(unittest.TestCase):
    def test_a_split_inside_the_window_is_not_settled_by_a_price_from_the_far_side(self) -> None:
        after = {stamp.date().isoformat(): (50.0, 50.5, 49.5, 50.0) for stamp in pd.bdate_range(start="2025-12-15", end=AS_OF)}
        payload = run(after, stop_price=90.0, current_price=50.0, splits={"2025-12-15": 2.0})

        data = payload["data"]
        self.assertEqual(data["verdict"], "INCOMPLETE")
        self.assertIsNone(data["current_price"])
        path = data["completed_price_path"]
        self.assertEqual(path["state"], "unavailable")
        self.assertEqual(path["reason"], "share_split_inside_stop_window")
        self.assertEqual(path["last_bar_checked"], "2025-12-12")


class TheRecordAndThePriceBesideItAgree(unittest.TestCase):
    def test_a_terminal_price_is_the_price_published_beside_its_own_record(self) -> None:
        payload = run({}, stop_price=95.0, current_price=94.0)

        data = payload["data"]
        self.assertEqual(data["verdict"], "SELL")
        path = data["completed_price_path"]
        self.assertEqual(path["breach_price"], 94.0)
        self.assertEqual(data["current_price"], 94.0)
        governing = next(audit for audit in path["audits"] if audit["role"] == "stop")
        # The bars still covered the window; the price only added what they could not say.
        self.assertEqual(governing["first_bar_checked"], "2025-12-01")
        self.assertEqual(governing["last_bar_checked"], AS_OF)


class APopulationOfHighsIsReadWhole(unittest.TestCase):
    def test_an_unreadable_high_since_entry_withholds_the_peak(self) -> None:
        payload = run(
            {"2025-12-18": (100.0, float("nan"), 99.0, 100.0), "2025-12-25": (100.0, 130.0, 99.0, 100.0)},
            start="2025-12-01",
            stop_price=90.0,
        )

        data = payload["data"]
        self.assertIsNone(data["max_high_since_entry"])
        self.assertEqual(data["max_high_withheld_reason"], "invalid_high_since_entry")

    def test_a_history_that_begins_after_entry_withholds_the_peak(self) -> None:
        payload = run({"2025-12-25": (100.0, 130.0, 99.0, 100.0)}, start="2025-12-04", stop_price=90.0, entry_date="2025-11-27")

        self.assertIsNone(payload["data"]["max_high_since_entry"])
        self.assertEqual(payload["data"]["max_high_withheld_reason"], "history_starts_after_entry_date")


class ARefusalNamesTheBarsThatSpokeFirst(unittest.TestCase):
    def test_an_unreadable_low_reports_the_prefix_it_had_already_audited(self) -> None:
        payload = run(
            {"2025-12-03": (100.0, 101.0, float("nan"), 100.0)},
            start="2025-12-01",
            end="2025-12-05",
            stop_price=90.0,
        )

        path = payload["data"]["completed_price_path"]
        self.assertEqual(path["reason"], "invalid_low_in_stop_window")
        self.assertEqual(path["first_bar_checked"], "2025-12-01")
        self.assertEqual(path["last_bar_checked"], "2025-12-02")
        self.assertEqual(path["bars_checked"], 2)


if __name__ == "__main__":
    unittest.main()
