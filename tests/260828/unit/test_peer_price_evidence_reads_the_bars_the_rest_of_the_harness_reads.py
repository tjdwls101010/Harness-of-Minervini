"""A peer's leadership numbers are measured off values that are not prices.

`ticker.peers` compares same-industry names on a three-month return and a distance from the
52-week high, and it re-implements price normalisation to do it. Both measurements read a whole
window -- the year's highest close, the close nearest a cutoff three months back -- which is the
case the shared reader was written for: a history read partially reports a 52-week high the
ticker may never have printed.

What it did instead was coerce and drop. A `Close` column of booleans came back as a flat line
whose distance from its own 52-week high is 0.0%, which is the best value that axis can take, so
a column of `True` ranks as well as a name sitting on a new high. Timestamps became epoch
numbers and returned 2.0%; complex closes measured identically to their real parts. A history
with an unreadable row was measured on the rows around it, and the dropped one can be the peak.

The session date is the other half. This surface converted a tz-aware index to New York where
the rest of the harness drops the zone and keeps the wall clock, so a UTC-stamped history had
its last session renamed to the day before -- and a history whose last session is not the
analysis session is refused outright. The peer then measures as nothing at all.
"""

from __future__ import annotations

from datetime import date
import unittest

import numpy as np
import pandas as pd

from scripts.minervini.peer_collection import _price_evidence
from scripts.minervini.setup_structure import read_bars


AS_OF = date(2025, 12, 31)


def rising(sessions: int = 400) -> pd.DataFrame:
    index = pd.bdate_range(end=AS_OF.isoformat(), periods=sessions)
    close = pd.Series(np.linspace(50.0, 200.0, sessions), index=index, dtype=float)
    return pd.DataFrame(
        {"Open": close, "High": close, "Low": close, "Close": close, "Volume": np.full(sessions, 1_000_000.0)},
        index=index,
    )


def booleans() -> pd.DataFrame:
    frame = rising()
    frame["Close"] = True
    return frame


def timestamps_as_prices() -> pd.DataFrame:
    frame = rising()
    frame["Close"] = pd.to_datetime("2020-01-01")
    return frame


def complex_closes() -> pd.DataFrame:
    frame = rising()
    frame["Close"] = frame["Close"].astype(complex) + 1j
    return frame


def a_hole_in_the_closes() -> pd.DataFrame:
    frame = rising()
    frame.iloc[200, frame.columns.get_loc("Close")] = np.nan
    return frame


def every_session_twice() -> pd.DataFrame:
    frame = rising()
    return pd.concat([frame, frame]).sort_index()


def repeated_column() -> pd.DataFrame:
    frame = rising()
    return pd.concat([frame, frame["Close"]], axis=1)


REFUSED = {
    "closes that are booleans": (booleans, "history_contains_non_numeric_values"),
    "closes that are timestamps": (timestamps_as_prices, "history_contains_non_numeric_values"),
    "closes that are complex numbers": (complex_closes, "history_contains_non_numeric_values"),
    "one unreadable close": (a_hole_in_the_closes, "history_contains_non_numeric_values"),
    "every session printed twice": (every_session_twice, "history_repeats_a_session"),
    "one column label printed twice": (repeated_column, "history_repeats_a_column"),
}


class APeerIsMeasuredFromPricesOrFromNothing(unittest.TestCase):
    def test_a_readable_history_is_still_measured(self) -> None:
        """The route that was always earned, so every refusal below is the history."""

        evidence = _price_evidence(rising(), AS_OF)

        self.assertEqual(evidence["provider"], "yfinance")
        self.assertEqual(evidence["distance_from_52_week_high_pct"], 0.0)

    def test_a_history_the_shared_reader_refuses_measures_nothing(self) -> None:
        for description, (build, reason) in REFUSED.items():
            history = build()
            with self.subTest(history=description):
                self.assertEqual(read_bars(history)[1], reason)

                self.assertIsNone(_price_evidence(history, AS_OF))

    def test_a_utc_stamped_history_is_the_same_history(self) -> None:
        """It was converted to New York, which renamed every session to the day before.

        The last session then failed to match the analysis date and the peer measured as
        nothing -- and a peer that measures as nothing is dropped from the ranking, so a leader
        this harness could read perfectly well improved the target's published rank by being
        unreadable.
        """

        frame = rising()

        self.assertEqual(_price_evidence(frame.tz_localize("UTC"), AS_OF), _price_evidence(frame, AS_OF))

    def test_the_three_month_start_is_the_session_the_cutoff_names(self) -> None:
        """The cutoff is a midnight timestamp and the sessions carried a closing time.

        Comparing them excluded the cutoff session itself and reached one session further back,
        which on this history reports 140% where the answer is 20%.
        """

        index = pd.DatetimeIndex(["2025-09-29 16:00", "2025-09-30 16:00", "2025-12-31 16:00"])
        close = pd.Series([50.0, 100.0, 120.0], index=index, dtype=float)
        frame = pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close, "Volume": [1e6] * 3}, index=index)

        self.assertEqual(_price_evidence(frame, AS_OF)["return_3m_pct"], 20.0)


if __name__ == "__main__":
    unittest.main()
