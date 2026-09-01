"""Behaviour a mutant walked through: each of these fails if the rule beside it is loosened."""

from __future__ import annotations

from datetime import date
import unittest

import numpy as np
import pandas as pd

from scripts.minervini.management_evidence import build_management_evidence
from scripts.minervini.operations import _risk_doctrine_ids


def frame(rows: list[tuple[str, float, float, float, float, int]]) -> pd.DataFrame:
    index = pd.DatetimeIndex([pd.Timestamp(stamp) for stamp, *_ in rows])
    return pd.DataFrame([row[1:] for row in rows], columns=["Open", "High", "Low", "Close", "Volume"], index=index)


def flat_rows(sessions: int, *, start: str = "2025-09-01", close: float = 100.0) -> list[tuple[str, float, float, float, float, int]]:
    index = pd.bdate_range(start=start, periods=sessions)
    return [(str(stamp.date()), close, close * 1.01, close * 0.99, close, 1_000_000) for stamp in index]


class OneSessionPrintedTwiceIsOneSession(unittest.TestCase):
    """The management measurements read the last print of a session, at whatever clock time."""

    def test_the_superseded_print_does_not_reach_the_twenty_day_average(self) -> None:
        rows = flat_rows(40)
        last_date = rows[-1][0]
        rows[-1] = (f"{last_date} 09:30", 100.0, 101.0, 99.0, 80.0, 1_000_000)
        rows.append((f"{last_date} 16:00", 100.0, 101.0, 99.0, 100.0, 1_000_000))
        result = build_management_evidence(frame(rows), entry_date=date.fromisoformat(rows[0][0]), as_of=date.fromisoformat(last_date))

        block = result["twenty_day_average"]
        self.assertEqual(block["state"], "above")
        self.assertEqual(block["close"], 100.0)
        # The superseded 80.0 print would drag a twenty-session mean it was never part of.
        self.assertEqual(block["average"], 100.0)


class ANewHighHasToBeHigher(unittest.TestCase):
    def test_a_close_exactly_equal_to_the_peak_did_not_recover_the_reaction(self) -> None:
        rows = flat_rows(30)
        for offset, close in ((27, 110.0), (28, 105.0), (29, 110.0)):
            stamp, *_ = rows[offset]
            rows[offset] = (stamp, close, close * 1.01, close * 0.99, close, 1_000_000)
        bars = frame(rows)
        result = build_management_evidence(bars, entry_date=bars.index[27].date(), as_of=bars.index[-1].date(), breakout_date=bars.index[27].date())

        reaction = result["post_breakout_behavior"]["natural_reactions"][-1]
        self.assertIsNone(reaction["recovered_in_sessions"])
        self.assertEqual(reaction["low_date"], bars.index[28].date().isoformat())


class CitationsAreCheckedAgainstTheRegistry(unittest.TestCase):
    def test_an_unregistered_id_anywhere_in_the_payload_is_dropped(self) -> None:
        # An empty request: what these two are about is the registry filter, and the echo rule
        # the third argument carries has its own tests beside the guard that motivated it.
        cited = _risk_doctrine_ids("active", {"management_evidence": {"anything": {"doctrine_id": "not.a.registered.claim", "doctrine_ids": ["also.not.registered"]}}}, {})

        self.assertNotIn("not.a.registered.claim", cited)
        self.assertNotIn("also.not.registered", cited)

    def test_a_registered_id_beside_a_measurement_is_kept(self) -> None:
        cited = _risk_doctrine_ids("active", {"management_evidence": {"twenty_day_average": {"doctrine_id": "management.close_below_20_day_average_lowers_probability"}}}, {})

        self.assertIn("management.close_below_20_day_average_lowers_probability", cited)


if __name__ == "__main__":
    unittest.main()
