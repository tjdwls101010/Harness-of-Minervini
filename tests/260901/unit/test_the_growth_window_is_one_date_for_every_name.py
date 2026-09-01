""""Four weeks earlier" has to be one moment, or the two counts are not comparable.

The group new-high reading counts how many of an industry's ranked names print a 52-week
high now against how many did one leader-confirmation window earlier. The window is
registered in weeks and was converted to a bar offset through `convention.trading_week`, so
every name stepped back twenty of *its own* sessions. A name that trades every session steps
back 28 days; one whose sessions were thinned by a halt steps back 60, or 84. The `earlier`
number was then a sum over names observed on different dates, and a group could read as
growing because one constituent was measured further back than the others.

Decision 311 drew this line for the 52-week window and it lands here too, with the reason
inverted. A bar count is right for the length of a thing being measured -- a six-week flag is
that stock's own sequence of bars. It is wrong for an address of a moment several names
share: the moment is on the calendar, and each name answers for it with whatever session it
had at or before that date.
"""

from __future__ import annotations

from datetime import date, timedelta
import unittest

import pandas as pd

from scripts.minervini import doctrine
from scripts.minervini.market_evidence import build_market_evidence
from scripts.minervini.windows import DAYS_IN_A_WEEK, session_at_or_before, year_window_start


AS_OF = date(2026, 8, 28)
LOOKBACK_WEEKS = doctrine.parameter("convention.group_member_reading", "new_high_growth_lookback_weeks")
LOOKBACK_DAYS = LOOKBACK_WEEKS * DAYS_IN_A_WEEK


def rows(dates: list[date], highs: list[float]) -> list[dict[str, object]]:
    return [{"date": day.isoformat(), "high": high, "low": high * 0.99, "close": high, "completed": True} for day, high in zip(dates, highs)]


def daily_history() -> list[dict[str, object]]:
    """Trades every session and has printed a new high on every one of them."""

    dates = [stamp.date() for stamp in pd.bdate_range(end=AS_OF, periods=520)]
    return rows(dates, [50.0 + index * 0.1 for index in range(len(dates))])


def thinned_history() -> list[dict[str, object]]:
    """One bar every three calendar days: at a new high now and four weeks back, not twelve.

    It peaks at 100 four months ago, gives that up into a trough two months ago, and takes
    the old high back out inside the last four weeks. Twenty of its own bars reach 60 days
    back, into the trough; the calendar's four weeks reach a session that had already cleared
    the old peak.
    """

    dates = sorted(AS_OF - timedelta(days=3 * index) for index in range(220))

    def high(day: date) -> float:
        ago = (AS_OF - day).days
        if ago >= 120:
            return 50.0 + (660 - ago) / (660 - 120) * 50.0
        if ago >= 60:
            return 100.0 - (120 - ago) / 60.0 * 20.0
        return 80.0 + (60 - ago) / 60.0 * 50.0

    return rows(dates, [high(day) for day in dates])


THANKSGIVING = date(2025, 11, 27)
HOLIDAY_AS_OF = date(2025, 12, 5)
# Four weeks before that Friday. Twenty bars before it is a day earlier, because the history
# is missing the session the exchange did not hold.
FOUR_WEEKS_BACK = date(2025, 11, 7)


def liquid_history_missing_a_holiday() -> list[dict[str, object]]:
    """Trades every session the exchange held, which is one fewer than twenty business days.

    It climbs to its high on 6 November, gives that up the next session, and takes out a new
    high on the last bar. Read four weeks back on the calendar it was not at a new high; read
    twenty of its own bars back -- one day earlier, because Thanksgiving is not in the series
    -- it was. So the two readings disagree for a name nobody would call thinly traded.
    """

    dates = [stamp.date() for stamp in pd.bdate_range("2024-01-02", HOLIDAY_AS_OF) if stamp.date() != THANKSGIVING]
    highs = []
    for index, day in enumerate(dates):
        if day < FOUR_WEEKS_BACK:
            highs.append(50.0 + index * 0.1)
        elif day < HOLIDAY_AS_OF:
            highs.append(90.0)
        else:
            highs.append(500.0)
    return rows(dates, highs)


def reading(history: dict[str, list[dict[str, object]]], as_of: date = AS_OF) -> dict:
    evidence = build_market_evidence(
        qqq_daily_ohlcv=None,
        finviz_html=None,
        sector_rows=None,
        industry_rows=[{"industry": "Semis", "avg_rs": 92.0, "count": 20, "rank": 1, "as_of": as_of.isoformat()}],
        leader_rows=[{"ticker": ticker, "rs_rating": 95} for ticker in history],
        trade_traction={"state": "supports"},
        leader_history=history,
        leader_groups={ticker: {"industry": "Semis"} for ticker in history},
        as_of=as_of,
    )
    return evidence["industries"][0]["new_highs"]


class EveryNameAnswersForTheSameEarlierDate(unittest.TestCase):
    def test_a_thinned_name_is_read_four_weeks_back_and_not_twelve(self) -> None:
        measured = reading({"DAILY": daily_history(), "THIN": thinned_history()})["measured"]

        self.assertEqual(measured["of_names_read"], 2)
        self.assertEqual(measured["now"], 2)
        # Both were at a new high four weeks ago. Stepping the thinned name back twenty of
        # its own bars landed in its trough and reported the group as growing.
        self.assertEqual(measured["earlier"], 2)

    def test_a_group_that_did_not_grow_is_not_reported_as_growing(self) -> None:
        self.assertEqual(reading({"DAILY": daily_history(), "THIN": thinned_history()})["state"], "observed")

    def test_the_reading_names_the_two_dates_it_compared(self) -> None:
        """A reader cannot judge the count without knowing which two moments it spans."""

        measured = reading({"DAILY": daily_history()})["measured"]

        self.assertEqual(measured["read_at"], AS_OF.isoformat())
        self.assertEqual(measured["compared_with"], (AS_OF - timedelta(days=LOOKBACK_DAYS)).isoformat())
        self.assertEqual(measured["lookback_weeks"], LOOKBACK_WEEKS)

    def test_the_trading_week_is_no_longer_cited_for_a_window_it_does_not_size(self) -> None:
        cited = reading({"DAILY": daily_history()})["window_doctrine_ids"]

        self.assertIn("convention.group_member_reading", cited)
        self.assertNotIn("convention.trading_week", cited)


class TheSessionAtOrBeforeADateIsReadDirectly(unittest.TestCase):
    def days(self, *offsets: int) -> list[date]:
        return [AS_OF - timedelta(days=offset) for offset in offsets]

    def test_an_exact_hit_is_that_session(self) -> None:
        self.assertEqual(session_at_or_before(self.days(30, 20, 10, 0), AS_OF - timedelta(days=20)), 1)

    def test_a_date_between_two_sessions_is_the_earlier_one(self) -> None:
        """The bar the name actually had at that date, which is the last one before it."""

        self.assertEqual(session_at_or_before(self.days(30, 20, 10, 0), AS_OF - timedelta(days=15)), 1)

    def test_a_date_after_the_last_session_is_the_last_session(self) -> None:
        self.assertEqual(session_at_or_before(self.days(30, 20, 10), AS_OF), 2)

    def test_a_date_before_the_first_session_is_nothing(self) -> None:
        self.assertIsNone(session_at_or_before(self.days(30, 20, 10), AS_OF - timedelta(days=40)))

    def test_an_empty_history_is_nothing(self) -> None:
        self.assertIsNone(session_at_or_before([], AS_OF))

    def test_sessions_out_of_order_are_nothing_rather_than_a_guess(self) -> None:
        self.assertIsNone(session_at_or_before(self.days(10, 30, 20), AS_OF - timedelta(days=15)))


if __name__ == "__main__":
    unittest.main()


class TheReaderRefusesWhatItCannotOrder(unittest.TestCase):
    """A not-a-time is not a moment, and neither reader may raise on one.

    Both window readers order their input before doing anything with it, and `pd.NaT` is an
    instance of `datetime` that refuses every comparison. Decision 311 caught this at the one
    caller that parses provider dates; the readers themselves still promised to return nothing
    for a sequence they cannot order and raised instead. A gap escaping a reducer as a
    TypeError is a gap published as an internal error.
    """

    def moments(self) -> list[object]:
        return [date(2026, 1, 1), pd.NaT, date(2026, 1, 3)]

    def test_a_not_a_time_between_two_sessions_is_refused_rather_than_raised(self) -> None:
        self.assertIsNone(session_at_or_before(self.moments(), date(2026, 1, 2)))

    def test_the_year_window_refuses_the_same_sequence(self) -> None:
        self.assertIsNone(year_window_start(self.moments(), 2))

    def test_a_not_a_time_at_the_end_is_refused(self) -> None:
        self.assertIsNone(session_at_or_before([date(2026, 1, 1), pd.NaT], date(2026, 1, 3)))


class TheDateComesFromTheClockAndNotFromTheBars(unittest.TestCase):
    """Two things a bar offset gets wrong that a thinned name is not needed to show."""

    def test_a_liquid_name_missing_one_holiday_is_still_read_four_weeks_back(self) -> None:
        """Twenty of its own bars reach a day further back, and that day answers differently."""

        measured = reading({"LIQUID": liquid_history_missing_a_holiday()}, HOLIDAY_AS_OF)["measured"]

        self.assertEqual(measured["compared_with"], FOUR_WEEKS_BACK.isoformat())
        self.assertEqual(measured["now"], 1)
        self.assertEqual(measured["earlier"], 0)

    def test_the_reading_answers_for_the_date_it_was_given_and_not_the_last_bar(self) -> None:
        """The same history, read at a session inside it, is a reading of that session.

        A date derived from whichever bar happened to be newest would ignore the argument
        entirely and answer here exactly as it answers above.
        """

        history = {"LIQUID": liquid_history_missing_a_holiday()}
        measured = reading(history, FOUR_WEEKS_BACK)["measured"]

        self.assertEqual(measured["read_at"], FOUR_WEEKS_BACK.isoformat())
        # On that session it had already given up its high, so nothing was at one.
        self.assertEqual(measured["now"], 0)
        self.assertEqual(reading(history, HOLIDAY_AS_OF)["measured"]["now"], 1)
