"""Where a caller's claim and the completed bars are about the same thing.

An assertion outranks evidence nobody gathered. It does not outrank evidence that was
gathered and says the opposite -- that is a request contradicting itself, which is
INCOMPLETE rather than a verdict. And a record is a record only if it carries the
coordinates that make it auditable: a state word alone is an assertion wearing the shape
of an audit.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import unittest

import numpy as np
import pandas as pd

from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot, SnapshotMeta


AS_OF = "2025-12-31"
POSITION = {"ticker": "TEST", "mode": "active", "entry_price": 100.0, "entry_date": "2025-12-01", "as_of": AS_OF}


def run(overrides=None, *, start="2025-11-03", end=AS_OF, stale=False, splits=None, **request) -> dict:
    index = pd.bdate_range(start=start, end=end)
    rows = [(overrides or {}).get(stamp.date().isoformat(), (100.0, 101.0, 99.0, 100.0)) for stamp in index]
    data = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"], index=index, dtype=float)
    data["Volume"] = np.full(len(data), 1_000_000)
    data["Stock Splits"] = np.zeros(len(data))
    for session, factor in (splits or {}).items():
        data.loc[pd.Timestamp(session), "Stock Splits"] = factor
    meta = SnapshotMeta(
        provider="fixture-prices",
        retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        as_of=date.fromisoformat(end),
        coverage={"completed_only": True},
        stale=stale,
    )
    calls: list[str] = []

    def history(ticker: str, as_of: str):
        calls.append(ticker)
        return ProviderSnapshot(data, meta)

    payload = execute("ticker.risk", {**POSITION, **request}, runtime=Runtime(price_history=history))
    payload["_calls"] = calls
    return payload


class AClearAuditRefutesTheAssertionAboutIt(unittest.TestCase):
    def test_an_asserted_completed_stop_beside_a_clear_window_is_not_a_verdict(self) -> None:
        payload = run(stop_price=94.0, completed_stop={"state": "triggered"})

        data = payload["data"]
        self.assertEqual(data["verdict"], "INCOMPLETE")
        self.assertEqual(data["failed"], [])
        self.assertIn("asserted_breach_contradicted_by_completed_bars", data["missing"])

    def test_an_asserted_stop_the_bars_confirm_is_still_a_sell(self) -> None:
        payload = run({"2025-12-10": (100.0, 101.0, 93.0, 100.0)}, stop_price=94.0, completed_stop={"state": "triggered"})

        self.assertEqual(payload["data"]["verdict"], "SELL")
        self.assertEqual(payload["data"]["failed"], ["completed_stop_breach"])

    def test_an_assertion_the_bars_could_not_check_still_stands(self) -> None:
        payload = run(start="2025-12-10", stop_price=94.0, completed_stop={"state": "triggered"})

        self.assertEqual(payload["data"]["verdict"], "SELL")
        self.assertEqual(payload["data"]["failed"], ["completed_stop_breach"])


class AStateWordIsNotAnAudit(unittest.TestCase):
    def test_a_path_with_no_coordinates_is_read_as_an_assertion(self) -> None:
        payload = run(stop_price=94.0, completed_price_path={"state": "breached"})

        self.assertEqual(payload["_calls"], ["TEST"])
        self.assertEqual(payload["data"]["verdict"], "INCOMPLETE")

    def test_a_path_naming_a_level_the_request_never_declared_is_not_a_record(self) -> None:
        payload = run(stop_price=94.0, completed_price_path={"state": "breached", "governing_role": "invalidation", "checked_level": 95.0, "breach_date": "2025-12-10"})

        self.assertEqual(payload["_calls"], ["TEST"])
        self.assertNotEqual(payload["data"]["verdict"], "SELL")

    def test_a_path_with_its_coordinates_is_the_record_and_is_not_re_derived(self) -> None:
        payload = run(stop_price=94.0, completed_price_path={"state": "breached", "governing_role": "stop", "checked_level": 94.0, "breach_date": "2025-12-10"})

        self.assertEqual(payload["_calls"], [])
        self.assertEqual(payload["data"]["verdict"], "SELL")


class TheExplicitPriceReadsEachLevelTheSameWayTheBarsDo(unittest.TestCase):
    def test_a_price_exactly_at_the_invalidation_has_not_gone_below_it(self) -> None:
        payload = run(stop_price=90.0, invalidation={"price": 95.0, "condition": "completed close below 95"}, current_price=95.0)

        self.assertEqual(payload["data"]["verdict"], "HOLD")
        self.assertEqual(payload["data"]["failed"], [])

    def test_a_close_under_both_levels_proves_the_resting_stop_went_first(self) -> None:
        payload = run(stop_price=90.0, invalidation={"price": 95.0, "condition": "completed close below 95"}, current_price=88.0)

        path = payload["data"]["completed_price_path"]
        self.assertEqual(payload["data"]["failed"], ["completed_stop_breach"])
        self.assertEqual(path["governing_role"], "stop")
        self.assertEqual(path["checked_level"], 90.0)


class ASplitOnTheWindowsFirstSessionIsNotInsideIt(unittest.TestCase):
    def test_a_position_opened_in_the_new_coordinates_is_audited_normally(self) -> None:
        before = {stamp.date().isoformat(): (100.0, 101.0, 99.0, 100.0) for stamp in pd.bdate_range(start="2025-11-03", end="2025-12-12")}
        after = {stamp.date().isoformat(): (50.0, 50.5, 49.0, 50.0) for stamp in pd.bdate_range(start="2025-12-15", end=AS_OF)}
        payload = run({**before, **after}, splits={"2025-12-15": 2.0}, entry_price=50.0, entry_date="2025-12-15", stop_price=45.0)

        data = payload["data"]
        self.assertEqual(data["verdict"], "HOLD")
        self.assertEqual(data["completed_price_path"]["state"], "clear")
        self.assertEqual(data["current_price"], 50.0)


class ThePriceThatCoversTheLastSessionIsNotAGap(unittest.TestCase):
    def test_a_history_one_session_behind_is_not_required_when_the_price_settles_it(self) -> None:
        payload = run(end="2025-12-30", stale=True, stop_price=95.0, current_price=94.0)

        self.assertEqual(payload["data"]["verdict"], "SELL")
        self.assertEqual(payload["status"], "ok")


if __name__ == "__main__":
    unittest.main()
