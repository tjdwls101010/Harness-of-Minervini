"""What a handed-in record has to carry, and what a block may cite.

A record the bars would produce always names the prices it read and the one that crossed,
and always falls inside the window the level it is about was in force. A block that cites a
claim has to have read that claim's inputs, and a value it could not compute has to say
which of the session's own numbers it was missing.
"""

from __future__ import annotations

from tests.providers import rows_snapshot

from datetime import date, datetime, timezone
import unittest
import numpy as np
import pandas as pd

from scripts.minervini.management_evidence import build_management_evidence
from scripts.minervini.operations import Runtime, execute


AS_OF = "2025-12-31"
POSITION = {"ticker": "TEST", "mode": "active", "entry_price": 100.0, "entry_date": "2025-12-01", "as_of": AS_OF}


def run(overrides=None, **request) -> dict:
    calls: list[str] = []
    index = pd.bdate_range(start="2025-10-01", end=AS_OF)
    rows = [(overrides or {}).get(stamp.date().isoformat(), (100.0, 101.0, 98.0, 100.0)) for stamp in index]
    data = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"], index=index, dtype=float)
    data["Volume"] = np.full(len(data), 1_000_000)
    data["Stock Splits"] = np.zeros(len(data))
    snapshot = rows_snapshot(data, provider="fixture-prices", retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc), as_of=date.fromisoformat(AS_OF), coverage={"completed_only": True})

    def history(ticker: str, as_of: str):
        calls.append(ticker)
        return snapshot

    payload = execute("ticker.risk", {**POSITION, **request}, runtime=Runtime(price_history=history))
    return {**payload, "_calls": calls}


class ARecordNamesThePricesItRead(unittest.TestCase):
    def test_a_record_with_no_basis_is_an_assertion_and_meets_the_bars(self) -> None:
        payload = run(stop_price=94.0, completed_price_path={"state": "breached", "governing_role": "stop", "checked_level": 94.0, "breach_date": "2025-12-10", "breach_low": 93.0})

        self.assertEqual(payload["_calls"], ["TEST"])
        self.assertEqual(payload["data"]["verdict"], "INCOMPLETE")

    def test_a_record_with_no_crossing_price_is_an_assertion_and_meets_the_bars(self) -> None:
        payload = run(stop_price=94.0, completed_price_path={"state": "breached", "basis": "completed_daily_low", "governing_role": "stop", "checked_level": 94.0, "breach_date": "2025-12-10"})

        self.assertEqual(payload["_calls"], ["TEST"])
        self.assertEqual(payload["data"]["verdict"], "INCOMPLETE")

    def test_a_complete_record_is_the_record_and_is_not_re_derived(self) -> None:
        payload = run(stop_price=94.0, completed_price_path={"state": "breached", "basis": "completed_daily_low", "governing_role": "stop", "checked_level": 94.0, "breach_date": "2025-12-10", "breach_low": 93.0})

        self.assertEqual(payload["_calls"], [])
        self.assertEqual(payload["data"]["verdict"], "SELL")


class ARecordFallsInsideItsOwnLevelsWindow(unittest.TestCase):
    def test_a_stop_cannot_be_broken_before_it_took_effect(self) -> None:
        payload = run(stop_price=95.0, stop_effective_date="2025-12-15", initial_stop_price=90.0, completed_price_path={"state": "breached", "basis": "completed_daily_low", "governing_role": "stop", "checked_level": 95.0, "breach_date": "2025-12-10", "breach_low": 94.0})

        self.assertEqual(payload["_calls"], ["TEST"])
        self.assertNotEqual(payload["data"]["verdict"], "SELL")

    def test_an_initial_stop_cannot_be_broken_after_it_was_raised_away(self) -> None:
        payload = run(stop_price=95.0, stop_effective_date="2025-12-15", initial_stop_price=90.0, completed_price_path={"state": "breached", "basis": "completed_daily_low", "governing_role": "initial_stop", "checked_level": 90.0, "breach_date": "2025-12-20", "breach_low": 89.0})

        self.assertEqual(payload["_calls"], ["TEST"])
        self.assertNotEqual(payload["data"]["verdict"], "SELL")

    def test_an_initial_stop_broken_before_the_raise_is_a_record(self) -> None:
        payload = run(stop_price=95.0, stop_effective_date="2025-12-15", initial_stop_price=90.0, completed_price_path={"state": "breached", "basis": "completed_daily_low", "governing_role": "initial_stop", "checked_level": 90.0, "breach_date": "2025-12-10", "breach_low": 89.0})

        self.assertEqual(payload["_calls"], [])
        self.assertEqual(payload["data"]["verdict"], "SELL")


def flat(count: int, *, low: float | None = None) -> pd.DataFrame:
    index = pd.bdate_range(end=AS_OF, periods=count)
    data = pd.DataFrame([(100.0, 101.0, 99.0, 100.0)] * count, columns=["Open", "High", "Low", "Close"], index=index, dtype=float)
    data["Volume"] = np.full(count, 1_000_000)
    data["Stock Splits"] = np.zeros(count)
    if low is not None:
        data.iloc[-1, data.columns.get_loc("Low")] = low
    return data


class ABlockCitesOnlyWhatItRead(unittest.TestCase):
    def test_a_gap_count_with_no_gap_never_opened_a_session_bar(self) -> None:
        bars = flat(80)
        block = build_management_evidence(bars, entry_date=bars.index[60].date(), as_of=bars.index[-1].date(), breakout_date=bars.index[60].date())["gaps_since_breakout"]

        self.assertIsNone(block["latest_gap"])
        self.assertIn("daily_bar", block["claim_inputs_not_read"])

    def test_a_climax_that_could_not_read_the_last_low_names_it(self) -> None:
        bars = flat(80, low=float("nan"))
        block = build_management_evidence(bars, entry_date=bars.index[60].date(), as_of=bars.index[-1].date())["climax"]

        self.assertIsNone(block["last_closing_range_pct"])
        self.assertIn("last_session_low", block["missing_inputs"])


class TheFloorOfWhatWasReachedIsOneRule(unittest.TestCase):
    def test_a_position_opened_today_reads_the_last_close_in_both_places(self) -> None:
        payload = run(entry_date=AS_OF, stop_price=90.0, base_top=80.0)

        data = payload["data"]
        self.assertEqual(data["risk_controls"]["favorable_excursion_basis"], "current_price")
        self.assertEqual(data["management_evidence"]["base_extension"]["max_extension_pct"], 25.0)


if __name__ == "__main__":
    unittest.main()
