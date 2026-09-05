"""The next earnings date, which is a forecast about the future and never a historical fact.

A calendar entry is mutable the way a sector label is mutable: what it says today is not what it
said last March, and no feed can tell you what it said then. So the snapshot refuses a
historical as_of outright rather than dating today's answer to a past session -- the same rule
the classification snapshot follows, for the same reason.

The other thing a consumer has to know is whether anybody confirmed it. A feed that answers with
two dates is naming a window it guessed at, and a REVIEW raised on a guess should say so.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import unittest

from scripts.minervini.providers import ProviderUnavailable
from scripts.minervini.providers.yfinance import next_earnings_snapshot


RETRIEVED = datetime(2026, 5, 8, 21, 0, tzinfo=timezone.utc)


def snapshot(calendar, **kwargs):
    return next_earnings_snapshot("TEST", calendar=calendar, retrieved_at=RETRIEVED, **kwargs)


class WhatTheCalendarSays(unittest.TestCase):
    def test_one_date_is_a_confirmed_report(self) -> None:
        result = snapshot({"Earnings Date": [date(2026, 5, 14)]})

        self.assertEqual(result.data["earnings_date"], "2026-05-14")
        self.assertEqual(result.data["confirmation"], "confirmed")
        self.assertIsNone(result.data["window"])
        self.assertEqual(result.data["symbol"], "TEST")

    def test_two_dates_are_a_window_the_feed_guessed_at(self) -> None:
        result = snapshot({"Earnings Date": [date(2026, 5, 12), date(2026, 5, 16)]})

        self.assertEqual(result.data["confirmation"], "estimated_range")
        self.assertEqual(result.data["window"], ["2026-05-12", "2026-05-16"])

    def test_the_earliest_date_in_a_window_is_the_one_published(self) -> None:
        # A holder deciding whether a report is ahead of them needs the first session it could
        # land on. The later edge would report a stock as clear on a day it might already report.
        result = snapshot({"Earnings Date": [date(2026, 5, 16), date(2026, 5, 12)]})

        self.assertEqual(result.data["earnings_date"], "2026-05-12")

    def test_a_report_already_behind_is_not_a_next_report(self) -> None:
        with self.assertRaises(ProviderUnavailable) as raised:
            snapshot({"Earnings Date": [date(2026, 4, 30)]})

        self.assertEqual(raised.exception.reason, "earnings_date_not_ahead")

    def test_a_report_due_today_is_still_ahead(self) -> None:
        result = snapshot({"Earnings Date": [date(2026, 5, 8)]})

        self.assertEqual(result.data["earnings_date"], "2026-05-08")


class WhatTheCalendarCannotSay(unittest.TestCase):
    def test_a_historical_as_of_is_refused_rather_than_answered_with_today(self) -> None:
        with self.assertRaises(ProviderUnavailable) as raised:
            snapshot({"Earnings Date": [date(2026, 5, 14)]}, as_of="2025-03-14")

        self.assertEqual(raised.exception.reason, "historical_earnings_calendar_unavailable")

    def test_an_empty_calendar_is_a_typed_gap(self) -> None:
        with self.assertRaises(ProviderUnavailable) as raised:
            snapshot({"Earnings Date": []})

        self.assertEqual(raised.exception.reason, "earnings_date_missing")

    def test_a_response_that_is_not_a_calendar_is_a_typed_gap(self) -> None:
        with self.assertRaises(ProviderUnavailable) as raised:
            snapshot(["2026-05-14"])

        self.assertEqual(raised.exception.reason, "invalid_earnings_calendar_response")

    def test_a_date_the_feed_wrote_as_something_else_is_refused(self) -> None:
        with self.assertRaises(ProviderUnavailable) as raised:
            snapshot({"Earnings Date": ["soon"]})

        self.assertEqual(raised.exception.reason, "invalid_earnings_date")


class TheSnapshotSaysWhatItIs(unittest.TestCase):
    def test_the_coverage_marks_the_answer_as_current_only(self) -> None:
        result = snapshot({"Earnings Date": [date(2026, 5, 14)]})

        self.assertEqual(result.meta.provider, "yfinance")
        self.assertEqual(result.meta.as_of, RETRIEVED.date())
        self.assertEqual(result.meta.coverage["kind"], "forward_looking_current_only")
        self.assertIs(result.meta.coverage["historical"], False)


if __name__ == "__main__":
    unittest.main()
