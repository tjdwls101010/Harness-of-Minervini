"""Two readers of one price frame, and the exact list of what they are allowed to disagree about.

`read_bars` is what a measurement that reads a whole window needs: a history with a hole in it
would report a 52-week high the ticker never printed, so a hole voids it. The stop audit reads
one column across one window and can answer better than that -- it names the bar it could not
read and reports the prefix it had already cleared -- so it keeps its holes and gets
`read_price_kinds` instead.

Two readers is how the last slice's defects happened, so the difference between them is written
down here rather than left to be discovered. Four rules belong to `read_bars` alone, and every
other refusal has to be the same refusal under the same name. A frame the whole-window reader
accepts is a frame the narrower one accepts, always -- if that ever fails, one of them has a
rule the other does not know about, which is the shape this file exists to catch.
"""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from scripts.minervini.setup_structure import read_bars, read_price_kinds


PRICES = ("Open", "High", "Low", "Close")


def clean(sessions: int = 20) -> pd.DataFrame:
    index = pd.bdate_range(end="2025-12-31", periods=sessions)
    close = pd.Series(np.linspace(100.0, 120.0, sessions), index=index, dtype=float)
    return pd.DataFrame(
        {"Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close, "Volume": np.full(sessions, 1_000_000.0)},
        index=index,
    )


def with_column(name: str, value) -> pd.DataFrame:
    frame = clean()
    frame[name] = value
    return frame


def with_event(name: str, value) -> pd.DataFrame:
    """An event column that is zero on every session but one."""

    frame = clean()
    frame[name] = 0.0 if not isinstance(value, bool) else False
    frame[name] = frame[name].astype(object)
    frame.iloc[10, frame.columns.get_loc(name)] = value
    return frame


def with_cell(name: str, position: int, value) -> pd.DataFrame:
    frame = clean()
    frame[name] = frame[name].astype(object)
    frame.iloc[position, frame.columns.get_loc(name)] = value
    return frame


# Every frame, and what each reader says about it. The verdicts are fixed one at a time so a
# pair that agrees wrongly cannot pass as a pair that agrees.
FRAMES = {
    "a clean history": (clean(), None, None),
    "a boolean column": (with_column("Close", True), "history_contains_non_numeric_values", "history_contains_non_numeric_values"),
    "a complex column": (with_column("Close", clean()["Close"].astype(complex) + 1j), "history_contains_non_numeric_values", "history_contains_non_numeric_values"),
    "a timestamp column": (with_column("Close", pd.to_datetime("2020-01-01")), "history_contains_non_numeric_values", "history_contains_non_numeric_values"),
    "one boolean cell": (with_cell("Low", 3, True), "history_contains_non_numeric_values", "history_contains_non_numeric_values"),
    "one word where a price goes": (with_cell("Low", 3, "closed"), "history_contains_non_numeric_values", "history_contains_non_numeric_values"),
    "one infinite price": (with_cell("Close", 3, np.inf), "history_contains_non_numeric_values", "history_contains_non_numeric_values"),
    "one price at zero": (with_cell("Low", 3, 0.0), "history_contains_non_positive_values", "history_contains_non_positive_values"),
    "a repeated column label": (pd.concat([clean(), clean()["Close"]], axis=1), "history_repeats_a_column", "history_repeats_a_column"),
    # The corporate-action column is an event rather than a price -- zero on every ordinary
    # session -- so it lives under its own rule, and both readers have to hold it to that rule.
    # Carried unchecked, `True` became 1, and 1 reads as "no split": a halving on the tape was
    # then a stop breach on a position nobody stopped out of.
    "split flags written as booleans": (with_event("Stock Splits", True), "history_contains_non_numeric_values", "history_contains_non_numeric_values"),
    "a negative split ratio": (with_event("Stock Splits", -2.0), "history_contains_non_positive_values", "history_contains_non_positive_values"),
    "a distribution column of timestamps": (with_column("Dividends", pd.to_datetime("2020-01-01")), "history_contains_non_numeric_values", "history_contains_non_numeric_values"),
    "no rows": (clean().iloc[0:0], "history_has_no_completed_bars", "history_has_no_completed_bars"),
    "a positional index": (clean().reset_index(drop=True), "history_index_is_not_dates", "history_index_is_not_dates"),
    "an index of strings": (clean().set_index(pd.Index([str(position) for position in range(20)])), "history_index_is_not_dates", "history_index_is_not_dates"),
    "not a frame at all": ([{"Close": 100.0}], "history_missing_required_columns", "history_missing_required_columns"),
}

# The four rules that belong to the whole-window reader alone, named one by one so that adding
# a fifth is a decision somebody makes rather than a test that quietly widens.
ONLY_READ_BARS = {
    "a hole where a price goes": (with_cell("Low", 3, np.nan), "history_contains_non_numeric_values"),
    # The same hole, written the other way a provider writes one. Which sentinel arrives is not
    # a fact about the market, and the two readers disagreeing on it made an established stop
    # breach reappear as INCOMPLETE the moment a later bar came back `None` instead of `nan`.
    "a hole written as None": (with_cell("Low", 3, None), "history_contains_non_numeric_values"),
    "a hole written as pandas NA": (with_cell("Low", 3, pd.NA), "history_contains_non_numeric_values"),
    # A word in the event column cannot coerce, so the split audit downstream notices it and
    # withholds itself by name -- which says more than refusing the history does.
    "a split column of words": (with_event("Stock Splits", "garbage"), "history_contains_non_numeric_values"),
    "a session printed twice": (pd.concat([clean(), clean()]).sort_index(), "history_repeats_a_session"),
    "a high under its own low": (with_cell("High", 3, 1.0), "history_contains_invalid_bar_ranges"),
    "no volume column": (clean().drop(columns=["Volume"]), "history_missing_required_columns"),
    # Not a rule the narrower reader lacks -- a column the caller did not ask it to read. The
    # test below reads it and gets the same refusal.
    "one negative volume": (with_cell("Volume", 3, -1.0), "history_contains_non_positive_values"),
}


class TheTwoReadersUseOneVocabulary(unittest.TestCase):
    def test_each_frame_gets_the_verdict_it_was_given(self) -> None:
        for description, (frame, by_bars, by_kinds) in FRAMES.items():
            with self.subTest(frame=description):
                self.assertEqual(read_bars(frame)[1], by_bars)
                self.assertEqual(read_price_kinds(frame, columns=PRICES)[1], by_kinds)

    def test_the_four_rules_the_narrower_reader_does_not_have(self) -> None:
        for description, (frame, by_bars) in ONLY_READ_BARS.items():
            with self.subTest(frame=description):
                self.assertEqual(read_bars(frame)[1], by_bars)
                self.assertIsNone(read_price_kinds(frame, columns=PRICES)[1])

    def test_a_column_it_is_asked_to_read_is_held_to_the_same_rule(self) -> None:
        negative = with_cell("Volume", 3, -1.0)

        self.assertEqual(read_price_kinds(negative, columns=(*PRICES, "Volume"))[1], "history_contains_non_positive_values")

    def test_nothing_the_whole_window_reader_accepts_is_refused_by_the_narrower_one(self) -> None:
        """The invariant, over every frame above. A refusal here is a rule one of them hides."""

        for description, (frame, _, _) in FRAMES.items():
            with self.subTest(frame=description):
                if read_bars(frame)[1] is None:
                    self.assertIsNone(read_price_kinds(frame, columns=PRICES)[1])

    def test_the_narrower_reader_keeps_the_clock_time_the_other_normalises_away(self) -> None:
        """The fifth difference, and the one that is not about refusing anything.

        `read_bars` refuses a repeated session, so a bar's time of day carries nothing for it and
        it normalises to the session date. The stop audit keeps the repeat and resolves it by
        taking the print that came later in the day, so dropping the time first would hand that
        choice to whatever order the provider happened to send the rows in.
        """

        frame = clean(4)
        stamps = list(frame.index)
        frame.index = pd.DatetimeIndex([*stamps[:-1], stamps[-1] + pd.Timedelta(hours=16)])

        kept = read_price_kinds(frame, columns=PRICES)[0]

        self.assertEqual(kept.index[-1], stamps[-1] + pd.Timedelta(hours=16))
        self.assertEqual(read_bars(frame)[0].index[-1], stamps[-1])

    def test_the_two_readers_return_the_same_sessions_for_a_frame_both_accept(self) -> None:
        """Same dates, same order, same prices -- a tz-aware and out-of-order frame included.

        The session date is where these last diverged: one reader dropped the zone and kept the
        wall clock while another converted to New York, and one frame became two calendars.
        """

        frame = clean().iloc[::-1]
        frame.index = frame.index.tz_localize("UTC")

        bars = read_bars(frame)[0]
        kinds = read_price_kinds(frame, columns=PRICES)[0]

        self.assertIsNotNone(bars)
        self.assertEqual(list(bars.index), list(kinds.index))
        pd.testing.assert_frame_equal(bars[list(PRICES)], kinds[list(PRICES)])


if __name__ == "__main__":
    unittest.main()
