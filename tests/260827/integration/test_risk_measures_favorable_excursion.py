"""The operation measures how far a position got, so the reducer is not guessing from the last close."""

from __future__ import annotations

from datetime import date, datetime, timezone
import unittest

import numpy as np
import pandas as pd

from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot, SnapshotMeta


AS_OF = "2025-12-31"
POSITION = {"ticker": "TEST", "mode": "active", "entry_price": 100.0, "entry_date": "2025-10-01", "stop_price": 94.0, "as_of": AS_OF}


def bars(closes: list[float], *, end: str = AS_OF) -> ProviderSnapshot[pd.DataFrame]:
    index = pd.bdate_range(end=end, periods=len(closes))
    close = pd.Series(closes, index=index, dtype=float)
    frame = pd.DataFrame({"Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close, "Volume": np.full(len(close), 1_000_000)}, index=index)
    return ProviderSnapshot(frame, SnapshotMeta(provider="fixture-prices", retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc), as_of=date.fromisoformat(end), coverage={"completed_only": True}))


def a_run_to(peak: float, then_back_to: float, *, sessions: int = 90) -> list[float]:
    up = list(np.linspace(100.0, peak, sessions // 2))
    down = list(np.linspace(peak, then_back_to, sessions - len(up)))
    return up + down


def protection(payload: dict) -> list[str]:
    """Only the three-R actions; the same bars may also carry structural reviews."""

    return [action["action"] for action in payload["data"]["management_actions"] if action["doctrine_id"] == "risk.profit_protection_at_3r"]


class TheHighSinceEntryIsMeasuredFromTheBars(unittest.TestCase):
    def run_risk(self, closes: list[float]) -> dict:
        return execute("ticker.risk", POSITION, runtime=Runtime(price_history=lambda ticker, as_of: bars(closes)))

    def test_three_r_reached_at_the_high_is_seen_even_when_the_last_close_is_below_it(self) -> None:
        payload = self.run_risk(a_run_to(125.0, 110.0))

        self.assertEqual(payload["data"]["verdict"], "HOLD")
        self.assertAlmostEqual(payload["data"]["max_high_since_entry"], 126.25)
        self.assertEqual(protection(payload), ["RAISE_STOP"])
        self.assertEqual(payload["data"]["management_actions"][0]["evidence"]["measured_from"], "max_high_since_entry")

    def test_bars_before_the_entry_date_do_not_count_as_something_the_position_reached(self) -> None:
        # The stock was at 140 before the position existed; since entry it never left 100-105.
        history = list(np.linspace(140.0, 100.0, 40)) + list(np.linspace(100.0, 105.0, 50))
        payload = execute("ticker.risk", {**POSITION, "entry_date": "2025-10-28"}, runtime=Runtime(price_history=lambda ticker, as_of: bars(history)))

        self.assertEqual(payload["data"]["verdict"], "HOLD")
        self.assertLess(payload["data"]["max_high_since_entry"], 110.0)
        self.assertEqual(protection(payload), [])


if __name__ == "__main__":
    unittest.main()


class WhatTheReviewerOfSliceAFound(unittest.TestCase):
    """Round p3a: two inputs the measurement had not been asked about."""

    def test_a_history_that_repeats_a_session_still_yields_one_high(self) -> None:
        # The provider layer permits a repeated session; the highest bar sits on the repeated date.
        closes = a_run_to(125.0, 110.0)
        snapshot = bars(closes)
        frame = snapshot.data
        doubled = pd.concat([frame, frame.iloc[[frame["High"].argmax()]]]).sort_index()
        payload = execute("ticker.risk", POSITION, runtime=Runtime(price_history=lambda ticker, as_of: ProviderSnapshot(doubled, snapshot.meta)))

        self.assertAlmostEqual(payload["data"]["max_high_since_entry"], 126.25)
        self.assertEqual(payload["data"]["max_high_date"], frame["High"].idxmax().date().isoformat())

    def test_a_bar_the_provider_returned_past_as_of_is_not_something_the_position_reached(self) -> None:
        closes = list(np.linspace(100.0, 105.0, 89)) + [140.0]
        later = bars(closes, end="2026-01-02")  # the 140 print is the session after as_of
        payload = execute("ticker.risk", POSITION, runtime=Runtime(price_history=lambda ticker, as_of: later))

        self.assertLess(payload["data"]["max_high_since_entry"], 110.0)
        self.assertEqual(protection(payload), [])

    def test_a_stop_raised_later_but_still_below_entry_is_not_the_initial_risk(self) -> None:
        # Entry 100, stop lifted from 94 to 97 on the 15th. Measured against 97 the run to 110
        # would read as 3.3R; the initial risk is unknown without the initial stop, so no 3R.
        payload = execute(
            "ticker.risk",
            {**POSITION, "stop_price": 97.0, "stop_effective_date": "2025-10-15"},
            runtime=Runtime(price_history=lambda ticker, as_of: bars(a_run_to(110.0, 108.0))),
        )

        self.assertEqual(payload["data"]["verdict"], "HOLD")
        self.assertIsNone(payload["data"]["risk_controls"]["r_multiple_reached"])
        self.assertEqual(protection(payload), [])


class TheEntrySessionIsNotCreditedToThePosition(unittest.TestCase):
    """A daily High cannot say whether it printed before or after the fill."""

    def spiking_entry(self) -> ProviderSnapshot[pd.DataFrame]:
        closes = [100.0] * 70
        index = pd.bdate_range(end=AS_OF, periods=len(closes))
        close = pd.Series(closes, index=index, dtype=float)
        high = close * 1.01
        entry_position = list(index.date).index(date.fromisoformat("2025-10-01"))
        high.iloc[entry_position] = 130.0
        frame = pd.DataFrame({"Open": close, "High": high, "Low": close * 0.99, "Close": close, "Volume": np.full(len(close), 1_000_000)}, index=index)
        return ProviderSnapshot(frame, SnapshotMeta(provider="fixture-prices", retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc), as_of=date.fromisoformat(AS_OF), coverage={"completed_only": True}))

    def test_a_spike_inside_the_entry_session_does_not_create_a_reached_gain(self) -> None:
        payload = execute("ticker.risk", POSITION, runtime=Runtime(price_history=lambda ticker, as_of: self.spiking_entry()))

        data = payload["data"]
        self.assertEqual(data["verdict"], "HOLD")
        self.assertNotEqual(data.get("max_high_since_entry"), 130.0)
        self.assertEqual(protection(payload), [])
