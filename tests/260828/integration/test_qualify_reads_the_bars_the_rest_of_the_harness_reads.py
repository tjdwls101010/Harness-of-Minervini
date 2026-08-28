"""The eligibility gate measures the same bars every other surface refuses to measure.

`setup_structure.read_bars` is the harness's one definition of a usable price history. It
was made the owner after a slice whose defects all shared one root -- values, dtypes,
timezones and index representations quietly becoming numbers or dates, and then moving
between surfaces with a different meaning. Five surfaces read through it. `ticker.qualify`
does not, and it is the hard gate: eight Trend Template criteria and Stage 2, the AND gate
that rejects a candidate before any deeper work runs.

Its own reading is `pd.to_numeric(history["Close"], errors="coerce").dropna()`, which is
precisely the laundering that reading was written to stop. Every history below is one the
shared reader names and refuses; every one of them is measured here instead, and the
envelope says `ok` beside the answer.

Two of them are worse than a wrong number. A history whose closes are half holes is
measured on the survivors, so a data gap is read as a short history and the capability
switches to the recent-IPO route -- an AVOID reached through the exception that exists for
genuinely young stocks. And a provider that prints every session twice is measured over
twice as many rows, so the 200-session average the source asks for spans a hundred trading
days. Both contradict the constitution's own line: unavailable evidence produces
INCOMPLETE, never a guessed pass or fail.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import unittest

import numpy as np
import pandas as pd

from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot, SnapshotMeta
from scripts.minervini.setup_structure import read_bars


AS_OF = "2025-12-31"


def rising(sessions: int = 300) -> pd.DataFrame:
    """A history that qualifies on all eight criteria, so every rejection below is the only change."""

    index = pd.bdate_range(end=AS_OF, periods=sessions)
    close = pd.Series(np.linspace(50.0, 200.0, sessions), index=index, dtype=float)
    return pd.DataFrame(
        {"Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close, "Volume": np.full(sessions, 1_000_000.0)},
        index=index,
    )


def _snapshot(payload, provider: str):
    return ProviderSnapshot(
        payload,
        SnapshotMeta(provider=provider, retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc), as_of=date.fromisoformat(AS_OF), coverage={"completed_only": True}),
    )


def qualify(history: pd.DataFrame) -> dict:
    return execute(
        "ticker.qualify",
        {"ticker": "TEST", "as_of": AS_OF},
        runtime=Runtime(
            price_history=lambda ticker, as_of: _snapshot(history, "fixture-prices"),
            rs_rating=lambda ticker, as_of: _snapshot({"rating": 95, "rating_date": AS_OF}, "ibd-rs-rating"),
        ),
    )


def doubled() -> pd.DataFrame:
    frame = rising()
    return pd.concat([frame, frame]).sort_index()


def intraday_pairs() -> pd.DataFrame:
    stamps = pd.DatetimeIndex([day + pd.Timedelta(hours=hour) for day in pd.bdate_range(end=AS_OF, periods=150) for hour in (10, 16)])
    close = pd.Series(np.linspace(50.0, 200.0, 300), index=stamps, dtype=float)
    return pd.DataFrame({"Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close, "Volume": np.full(300, 1_000_000.0)}, index=stamps)


def holed() -> pd.DataFrame:
    frame = rising()
    frame.iloc[100:250, frame.columns.get_loc("Close")] = np.nan
    return frame


def negative_close() -> pd.DataFrame:
    frame = rising()
    frame.iloc[10, frame.columns.get_loc("Close")] = -5.0
    return frame


def inverted_bar() -> pd.DataFrame:
    frame = rising()
    frame.iloc[50, frame.columns.get_loc("High")] = 1.0
    return frame


def booleans() -> pd.DataFrame:
    frame = rising()
    frame["Close"] = True
    return frame


def complex_closes() -> pd.DataFrame:
    frame = rising()
    frame["Close"] = frame["Close"].astype(complex) + 1j
    return frame


def timestamps_as_prices() -> pd.DataFrame:
    frame = rising()
    frame["Close"] = pd.to_datetime("2020-01-01")
    return frame


def positional_index() -> pd.DataFrame:
    return rising().reset_index(drop=True)


def repeated_column() -> pd.DataFrame:
    """A provider flattening a multi-level header prints one label twice."""

    frame = rising()
    return pd.concat([frame, frame["Close"]], axis=1)


def no_bars_at_all() -> pd.DataFrame:
    return rising().iloc[0:0]


def labelled_index() -> pd.DataFrame:
    frame = rising()
    frame.index = [str(position) for position in range(len(frame))]
    return frame


# Each entry is a history and the name the shared reader gives for refusing it. The names are
# asserted rather than only the refusal, because a surface that refuses everything for one
# reason tells a reader nothing about which of these they are holding.
REFUSED = {
    "every session printed twice": (doubled, "history_repeats_a_session"),
    "two intraday stamps per date": (intraday_pairs, "history_repeats_a_session"),
    "half the closes are holes": (holed, "history_contains_non_numeric_values"),
    "a close below zero": (negative_close, "history_contains_non_positive_values"),
    "a bar whose high is under its low": (inverted_bar, "history_contains_invalid_bar_ranges"),
    "closes that are booleans": (booleans, "history_contains_non_numeric_values"),
    "closes that are complex numbers": (complex_closes, "history_contains_non_numeric_values"),
    "closes that are timestamps": (timestamps_as_prices, "history_contains_non_numeric_values"),
    "a positional index that never held dates": (positional_index, "history_index_is_not_dates"),
    "an index of strings": (labelled_index, "history_index_is_not_dates"),
    # These two left as a raised exception rather than as a verdict at all. An internal failure
    # is the one thing worse than a wrong answer here: the envelope is the contract, and a
    # traceback is not a status a caller can read a gap out of.
    "one column label printed twice": (repeated_column, "history_repeats_a_column"),
    "a frame with no rows": (no_bars_at_all, "history_has_no_completed_bars"),
}


class TheGateRefusesWhatItCannotRead(unittest.TestCase):
    def test_the_clean_history_still_qualifies(self) -> None:
        """The route that was always earned, so every refusal below is the history and not the fix."""

        payload = qualify(rising())

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["data"]["eligibility_state"], "eligible")
        self.assertEqual(payload["data"]["completed_session_count"], 300)

    def test_a_history_the_shared_reader_refuses_is_not_measured_here_either(self) -> None:
        for description, (build, reason) in REFUSED.items():
            history = build()
            with self.subTest(history=description):
                # The premise: this really is a history the owner refuses, and for this reason.
                self.assertEqual(read_bars(history)[1], reason)

                payload = qualify(history)

                self.assertEqual(payload["status"], "unavailable")
                self.assertEqual(payload["data"]["eligibility_state"], "incomplete")
                self.assertEqual([item["reason"] for item in payload["missing"]], [reason])

    def test_a_history_with_holes_does_not_become_a_young_stock(self) -> None:
        """The recent-IPO route is an exception for a stock with no long history, not for a gap.

        Dropping the unreadable closes leaves 150 rows, and 150 rows is below the 200 the
        standard route needs -- so the capability took the route reserved for a stock that has
        not existed long enough to have those sessions. This history has 300 sessions and the
        harness could not read half of them, which is a different fact entirely.
        """

        payload = qualify(holed())

        self.assertNotEqual(payload["data"].get("route"), "recent_ipo_primary_base")

    def test_a_doubled_history_does_not_publish_a_session_count_it_did_not_measure(self) -> None:
        """600 rows over 300 sessions, and the 200-session average would span 100 trading days."""

        payload = qualify(doubled())

        self.assertNotEqual(payload["data"].get("completed_session_count"), 600)

    def test_the_published_session_date_is_a_session_date(self) -> None:
        """`price_as_of` is the row label stringified, so a positional index publishes "299"."""

        published = qualify(positional_index())["data"].get("price_as_of")

        self.assertNotEqual(published, "299")


if __name__ == "__main__":
    unittest.main()
