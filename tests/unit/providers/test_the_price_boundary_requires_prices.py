"""A frame with no price column is not a history of completed sessions.

`_complete_rows` checks every column the frame carries and requires nothing of the columns it
does not, so a frame with no `Close` at all passed as complete. The provider then published it
as a session's worth of evidence, the multiple came back unavailable for want of a last close,
and a declared breakout date on that same session was refused as a session that never happened.

Two smaller things at the same boundary. The next-report date is compared with today, and today
for a US listing is a New York date -- before New York midnight the UTC clock has already
turned, so a report due this afternoon read as one filed yesterday. And a repeated session
keeps its last print only if the sort that ordered them was stable.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import random
import unittest

import pandas as pd

from scripts.minervini.operations import _valuation_closes
from scripts.minervini.providers import ProviderUnavailable
from scripts.minervini.providers.yfinance import completed_daily_bars, next_earnings_snapshot


class Feed:
    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame

    def history(self, **_: object) -> pd.DataFrame:
        return self.frame


class AFrameWithoutPricesIsRefused(unittest.TestCase):
    def test_a_history_missing_its_close_column_never_becomes_evidence(self) -> None:
        frame = pd.DataFrame(
            {"Open": [10.0], "High": [11.0], "Low": [9.0], "Volume": [1000]},
            index=pd.to_datetime(["2026-05-08"]),
        )

        with self.assertRaises(ProviderUnavailable) as raised:
            completed_daily_bars("TEST", as_of="2026-05-08", ticker=Feed(frame), now=datetime(2026, 5, 9, 21, 0, tzinfo=timezone.utc))

        self.assertEqual(raised.exception.reason, "daily_bars_missing_price_columns")


class TodayIsAsNewYorkCountsIt(unittest.TestCase):
    def test_a_report_due_this_afternoon_is_still_ahead_after_utc_midnight(self) -> None:
        # 2026-05-08 00:30 UTC is 2026-05-07 20:30 in New York.
        snapshot = next_earnings_snapshot(
            "TEST",
            calendar={"Earnings Date": [date(2026, 5, 7)]},
            retrieved_at=datetime(2026, 5, 8, 0, 30, tzinfo=timezone.utc),
        )

        self.assertEqual(snapshot.data["earnings_date"], "2026-05-07")


class ARepeatedSessionKeepsItsLastPrint(unittest.TestCase):
    def test_the_order_the_provider_sent_decides_which_print_is_last(self) -> None:
        rows = [("2026-05-08" if index % 2 else "2026-05-07", float(index)) for index in range(20)]
        random.Random(7).shuffle(rows)
        frame = pd.DataFrame({"Close": [value for _, value in rows]}, index=pd.to_datetime([day for day, _ in rows]))
        expected = [value for day, value in rows if day == "2026-05-08"][-1]

        closes = _valuation_closes(frame, as_of=date(2026, 5, 8), breakout_date=date(2026, 5, 8))

        self.assertEqual(closes["last_close"], expected)
        self.assertEqual(closes["breakout_close"], expected)


if __name__ == "__main__":
    unittest.main()
