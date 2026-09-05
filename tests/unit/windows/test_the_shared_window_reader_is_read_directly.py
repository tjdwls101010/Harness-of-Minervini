"""The reader both modules now depend on, tested where it lives.

The first cut of this slice tested only what `market_evidence` published, which left the
shared reader and `technical.py`'s use of it covered by nothing. An adversarial round walked
in through exactly that gap: a date that is present and unreadable crashed the series, a
history whose parsed dates run out of order was sliced positionally as though they did not,
and dropping the time off a timestamp moved the boundary the window opens on.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import unittest

import numpy as np
import pandas as pd

from scripts.minervini import technical
from scripts.minervini.market_evidence import build_market_evidence, carries_a_readable_bar
from scripts.minervini.windows import DAYS_IN_THE_YEAR_THE_SOURCES_NAME as YEAR, year_window_start


AS_OF = "2026-08-28"


def days(*offsets: int, end: date = date(2026, 8, 28)) -> list[date]:
    return [end - timedelta(days=offset) for offset in sorted(offsets, reverse=True)]


def frame(index, highs: list[float]) -> pd.DataFrame:
    closes = np.array(highs, dtype=float)
    return pd.DataFrame({"Close": closes, "High": closes, "Low": closes * 0.9, "Volume": 1e6}, index=pd.Index(index))


def rows(index, **overrides) -> list[dict]:
    built = [
        {"date": stamp.date().isoformat(), "open": 100.0, "high": 100.0, "low": 99.0, "close": 100.0, "completed": True}
        for stamp in index
    ]
    for position, value in overrides.pop("dates", {}).items():
        if value is None:
            del built[position]["date"]
        else:
            built[position]["date"] = value
    return built



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

def leader(bars: list[dict]) -> dict:
    evidence = build_market_evidence(
        qqq_daily_ohlcv=None,
        finviz_html=None,
        sector_rows=None,
        industry_rows=None,
        leader_rows=[{"ticker": "LEAD", "rs_rating": 99}],
        leader_history={"LEAD": bars},
        trade_traction=None,
        as_of=_reading_date({"LEAD": bars}),
    )
    return evidence["leaders"][0]


class TheReaderAnswersOrDeclinesAndNeverGuesses(unittest.TestCase):
    def test_the_year_is_the_52_weeks_the_sources_name(self) -> None:
        self.assertEqual(YEAR, 52 * 7)

    def test_a_span_one_day_short_of_the_year_is_not_a_window(self) -> None:
        self.assertIsNone(year_window_start(days(YEAR - 1, 0), 1))
        self.assertEqual(year_window_start(days(YEAR, 0), 1), 0)

    def test_nothing_to_read_and_nowhere_to_read_from_are_both_declined(self) -> None:
        self.assertIsNone(year_window_start([], 0))
        self.assertIsNone(year_window_start(days(0), -1))
        self.assertIsNone(year_window_start(days(0), 5))

    def test_a_window_ending_partway_back_needs_a_year_behind_that_session(self) -> None:
        """Not a year behind the latest bar: the window is the one ending where it was asked to."""

        dates = days(500, 400, YEAR, 100, 0)

        # A window ending at the bar a year back would have to reach two years back.
        self.assertIsNone(year_window_start(dates, 2))
        # Ending at the latest bar, it opens on the bar exactly a year behind it.
        self.assertEqual(year_window_start(dates, 4), 2)

    def test_the_boundary_session_itself_is_inside_the_window(self) -> None:
        dates = days(YEAR + 1, YEAR, 10, 0)

        self.assertEqual(year_window_start(dates, 3), 1)

    def test_a_timestamp_keeps_its_time_because_the_span_is_a_duration(self) -> None:
        """Two stamps 363 days and 17 hours apart are not a year, whatever their dates read."""

        stamps = [pd.Timestamp("2025-01-01 16:00", tz="America/New_York"), pd.Timestamp("2025-12-31 09:30", tz="America/New_York")]

        self.assertIsNone(year_window_start(stamps, 1))


class TheEligibilityWindowIsUnchangedByTheMove(unittest.TestCase):
    def test_an_index_whose_parsed_dates_run_out_of_order_measures_nothing(self) -> None:
        """Monotonic as text and not as dates. A positional slice would take a peak outside the year."""

        bars = frame(["01-Jan-2024", "02-Jan-2025", "31-Dec-2024", "31-Dec-2025"], [10.0, 20.0, 999.0, 30.0])

        self.assertIsNone(technical._year_window(bars))

    def test_stamps_short_of_the_year_by_hours_publish_no_window(self) -> None:
        index = pd.DatetimeIndex([pd.Timestamp("2025-01-01 16:00", tz="America/New_York"), pd.Timestamp("2025-12-31 09:30", tz="America/New_York")])

        self.assertIsNone(technical._year_window(frame(index, [100.0, 20.0])))

    def test_an_ordinary_daily_history_still_measures_the_whole_year(self) -> None:
        index = pd.bdate_range(end=AS_OF, periods=300)
        window = technical._year_window(frame(index, [100.0] * 300))

        self.assertIsNotNone(window)
        self.assertGreaterEqual((index[-1] - window.index[0]).days, 0)
        self.assertLessEqual((index[-1] - window.index[0]).days, YEAR)


class ABrokenDateIsABrokenBar(unittest.TestCase):
    INDEX = pd.bdate_range(end=AS_OF, periods=270)

    def test_a_not_a_time_in_a_date_field_refuses_the_history(self) -> None:
        """It arrives as a datetime and is not one, so the fast path handed back a non-date."""

        reading = leader(rows(self.INDEX, dates={5: pd.NaT}))

        self.assertEqual(reading["behavior"], {"state": "unavailable", "reason": "leader_price_history_not_read"})

    def test_a_date_that_is_not_a_date_refuses_the_history(self) -> None:
        reading = leader(rows(self.INDEX, dates={5: "d0005"}))

        self.assertEqual(reading["behavior"]["reason"], "leader_price_history_not_read")

    def test_rows_that_disagree_about_having_a_date_are_refused_rather_than_read_undated(self) -> None:
        """Otherwise the readable-bar predicate and the leader's own reading disagree."""

        bars = rows(self.INDEX, dates={100: None})

        self.assertFalse(carries_a_readable_bar(bars))
        self.assertEqual(leader(bars)["behavior"]["reason"], "leader_price_history_not_read")

    def test_a_history_that_never_claimed_dates_keeps_its_prices_and_loses_the_window(self) -> None:
        bars = [{"open": 100.0, "high": 100.0, "low": 99.0, "close": 100.0, "completed": True} for _ in range(270)]

        self.assertTrue(carries_a_readable_bar(bars))
        self.assertEqual(leader(bars)["behavior"], {"state": "unavailable", "reason": "leader_price_history_carries_no_session_dates"})


if __name__ == "__main__":
    unittest.main()
