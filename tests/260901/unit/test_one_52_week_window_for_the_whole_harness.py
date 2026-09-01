"""The market's 52-week window counted bars while the eligibility stack measured a year.

Decision 307 moved `technical.py` to a date-bounded window: the trailing 52 x 7 days, and
nothing published unless the history reaches back that far. `market_evidence` was left
counting sessions -- `52 x convention.trading_week(5) = 260` -- and the two answers differ
in both directions.

Too strict: a real US year is about 252 sessions, so demanding 260 asks for thirteen months.
Too loose: a name whose sessions were thinned by a halt reaches 260 bars over years, and the
"52-week high" it publishes is one the stock printed long before the year in question.

One reader, and both modules ask it.
"""

from __future__ import annotations

from datetime import date
import unittest

import pandas as pd

from scripts.minervini.market_evidence import build_market_evidence


AS_OF = "2026-08-28"


def bars(index, closes: list[float], highs: list[float] | None = None) -> list[dict]:
    highs = highs if highs is not None else closes
    return [
        {"date": stamp.date().isoformat(), "open": close, "high": high, "low": close * 0.99, "close": close, "volume": 1_000_000, "completed": True}
        for stamp, close, high in zip(index, closes, highs)
    ]



def _reading_date(history: dict[str, list[dict[str, object]]]) -> date:
    """The last session the fixture carries -- the date the group reading is taken at.

    A fixture with no dated session has no group reading to take, so any date will do there.
    """

    dated = []
    for rows in history.values():
        for row in rows:
            try:
                dated.append(date.fromisoformat(str(row.get("date"))))
            except (TypeError, ValueError):
                # A fixture that deliberately carries a broken date has no reading to take.
                continue
    return max(dated) if dated else date(2026, 1, 2)

def leader(rows: list[dict]) -> dict:
    evidence = build_market_evidence(
        qqq_daily_ohlcv=None,
        finviz_html=None,
        sector_rows=None,
        industry_rows=None,
        leader_rows=[{"ticker": "LEAD", "rs_rating": 99}],
        leader_history={"LEAD": rows},
        trade_traction=None,
        as_of=_reading_date({"LEAD": rows}),
    )
    return evidence["leaders"][0]


class TheWindowIsBoundedByDateAndNotByBarCount(unittest.TestCase):
    def test_a_year_of_sessions_that_does_not_span_a_year_measures_nothing(self) -> None:
        """260 business days end 361 days back. The count is met and the year is not."""

        index = pd.bdate_range(end=AS_OF, periods=260)
        self.assertLess((index[-1] - index[0]).days, 364)

        reading = leader(bars(index, [100.0] * 259 + [110.0]))

        self.assertEqual(reading["behavior"], {"state": "unavailable", "reason": "completed_sessions_short_of_a_52_week_window"})
        self.assertEqual(reading["distance_from_52w_high"]["state"], "unavailable")

    def test_a_thinned_history_cannot_reach_past_the_year_for_its_high(self) -> None:
        """Every third session, so 260 bars span three years. The window is still one."""

        index = pd.bdate_range(end=AS_OF, periods=780)[::3]
        self.assertGreater((index[-1] - index[0]).days, 1000)
        highs = [100.0] * len(index)
        highs[10] = 300.0

        reading = leader(bars(index, [100.0] * len(index), highs))

        self.assertEqual(reading["distance_from_52w_high"]["measured"], 0.0)

    def test_a_history_that_does_span_the_year_still_measures(self) -> None:
        index = pd.bdate_range(end=AS_OF, periods=270)
        self.assertGreaterEqual((index[-1] - index[0]).days, 364)

        reading = leader(bars(index, [100.0] * 269 + [110.0]))

        self.assertEqual(reading["distance_from_52w_high"]["measured"], 0.0)
        self.assertEqual(reading["on_52w_low_list"]["measured"], False)


if __name__ == "__main__":
    unittest.main()
