"""The sell decision is audited against values that are not prices.

`ticker.risk` is the only capability that says SELL. It reads the provider frame three separate
ways -- the stop audit, the management evidence, and the current close when no numeric level
ran an audit -- and each normalises it differently.

What it deliberately keeps is its tolerance for absence: a hole in the Lows names the bar and
reports the prefix already cleared, which tells a holder more than refusing them a verdict. What
it never had is the other half. `float()` turns a boolean into 1.0, a complex number into its
real part and a timestamp into epoch nanoseconds, and each of those is a fabricated price rather
than an absent one -- the audit sold positions on all three. An index that never carried dates
becomes nanoseconds after 1970, and the stop window lands in a year the position did not exist
in. An infinity leaves the CLI unable to serialise the envelope at all.

The session date is the third: the audit converted a tz-aware index to New York where the rest
of the harness drops the zone and keeps the wall clock, so a UTC-stamped history had every
session renamed to the day before and a breach was recorded against a session nothing else
agrees exists.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import unittest

import numpy as np
import pandas as pd

from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot, SnapshotMeta
from scripts.minervini.setup_structure import read_price_kinds


AS_OF = "2025-12-31"
ENTRY = "2025-10-01"


def held(sessions: int = 120) -> pd.DataFrame:
    """A position entered at 100 whose bars never come near the stop."""

    index = pd.bdate_range(end=AS_OF, periods=sessions)
    close = pd.Series(np.linspace(100.0, 130.0, sessions), index=index, dtype=float)
    return pd.DataFrame(
        {"Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close, "Volume": np.full(sessions, 1_000_000.0)},
        index=index,
    )


def snapshot(frame: pd.DataFrame, *, as_of: str = AS_OF) -> ProviderSnapshot[pd.DataFrame]:
    return ProviderSnapshot(
        frame,
        SnapshotMeta(provider="fixture-prices", retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc), as_of=date.fromisoformat(as_of), coverage={"completed_only": True}),
    )


def risk(frame: pd.DataFrame, **overrides) -> dict:
    request = {"ticker": "TEST", "mode": "active", "as_of": AS_OF, "entry_price": 100.0, "entry_date": ENTRY, "stop_price": 94.0}
    request.update(overrides)
    return execute("ticker.risk", request, runtime=Runtime(price_history=lambda ticker, as_of: snapshot(frame)))


def boolean_lows() -> pd.DataFrame:
    frame = held()
    frame["Low"] = frame["Low"].astype(object)
    frame.iloc[list(frame.index).index(pd.Timestamp(ENTRY)) + 10, frame.columns.get_loc("Low")] = True
    return frame


def complex_prices() -> pd.DataFrame:
    frame = held()
    for column in ("Open", "High", "Low", "Close"):
        frame[column] = frame[column].astype(complex) + 1j
    return frame


def epoch_index() -> pd.DataFrame:
    frame = held()
    frame.index = pd.Index([stamp.value for stamp in frame.index])
    return frame


def timestamps_as_prices() -> pd.DataFrame:
    frame = held()
    for column in ("Open", "High", "Low", "Close"):
        frame[column] = pd.to_datetime("2020-01-01")
    return frame


def repeated_column() -> pd.DataFrame:
    frame = held()
    return pd.concat([frame, frame["Close"]], axis=1)


def an_infinite_close() -> pd.DataFrame:
    frame = held()
    frame.iloc[-1, frame.columns.get_loc("Close")] = np.inf
    return frame


REFUSED = {
    "one boolean low": (boolean_lows, "history_contains_non_numeric_values"),
    "complex prices": (complex_prices, "history_contains_non_numeric_values"),
    "an index of epoch nanoseconds": (epoch_index, "history_index_is_not_dates"),
    "timestamps where the prices go": (timestamps_as_prices, "history_contains_non_numeric_values"),
    "one column label printed twice": (repeated_column, "history_repeats_a_column"),
    "an infinite close": (an_infinite_close, "history_contains_non_numeric_values"),
}


class TheSellDecisionIsNotAuditedAgainstUnreadableBars(unittest.TestCase):
    def test_a_readable_history_is_still_audited(self) -> None:
        """The route that was always earned, so every refusal below is the history."""

        payload = risk(held())

        self.assertEqual(payload["data"]["verdict"], "HOLD")
        self.assertEqual(payload["data"]["completed_price_path"]["state"], "clear")

    def test_a_history_the_shared_reader_refuses_audits_nothing(self) -> None:
        for description, (build, reason) in REFUSED.items():
            history = build()
            with self.subTest(history=description):
                self.assertEqual(read_price_kinds(history, columns=("Open", "High", "Low", "Close"))[1], reason)

                payload = risk(history)

                self.assertNotEqual(payload["data"]["verdict"], "HOLD")
                self.assertNotEqual(payload["data"]["verdict"], "SELL")
                named = [item for item in payload["missing"] if item["id"] == "usable_daily_bars"]
                self.assertEqual([item["reason"] for item in named], [reason])

    def test_a_hole_in_the_lows_still_reports_the_prefix_it_had_audited(self) -> None:
        """The tolerance this capability keeps, stated beside the ones it gives up.

        An absent price is not a wrong one. The audit names the bar it could not read and says
        how far it got, which is a finer answer than withholding the verdict entirely -- and it
        is the reason this surface reads its own rules rather than the whole-window reader's.
        """

        frame = held()
        # Ten sessions into the window the stop is audited over, so nine bars come through
        # clear before the reading stops.
        hole = list(frame.index).index(pd.Timestamp(ENTRY)) + 10
        frame.iloc[hole, frame.columns.get_loc("Low")] = np.nan

        path = risk(frame)["data"]["completed_price_path"]

        self.assertEqual(path["reason"], "invalid_low_in_stop_window")
        self.assertEqual(path["bars_checked"], 10)

    def test_a_later_hole_does_not_take_back_a_breach_the_bars_already_printed(self) -> None:
        """Whichever sentinel the provider wrote the hole with.

        A breach is irreversible -- a bar the harness cannot read afterwards says nothing about
        a session that already crossed the stop. The hole reached here as `None` rather than
        `nan` on one bar, and the reading refused the whole history, so a position the market
        had taken out came back as one nobody could rule on.
        """

        entry = list(held().index).index(pd.Timestamp(ENTRY))
        verdicts = {}
        for label, sentinel in (("nan", np.nan), ("None", None), ("pandas NA", pd.NA)):
            frame = held()
            frame.iloc[entry + 5, frame.columns.get_loc("Low")] = 90.0
            frame["Low"] = frame["Low"].astype(object)
            frame.iloc[entry + 20, frame.columns.get_loc("Low")] = sentinel
            verdicts[label] = risk(frame)["data"]["verdict"]

        self.assertEqual(verdicts, {"nan": "SELL", "None": "SELL", "pandas NA": "SELL"})

    def test_a_split_flag_that_is_not_a_ratio_is_not_read_as_no_split(self) -> None:
        """The event column is the one thing the raw tape cannot say, and it was carried unchecked.

        `True` coerces to 1 downstream and 1 means "no split", so a price that halved because
        the share did reads as a decline the position has to be stopped out of. A corporate
        action moves every printed price without moving anyone's money.
        """

        frame = held()
        halves = list(frame.index).index(pd.Timestamp(ENTRY)) + 10
        frame.iloc[halves:, :4] = frame.iloc[halves:, :4] / 2
        frame["Stock Splits"] = False
        frame["Stock Splits"] = frame["Stock Splits"].astype(object)
        frame.iloc[halves, frame.columns.get_loc("Stock Splits")] = True

        payload = risk(frame)

        self.assertNotEqual(payload["data"]["verdict"], "SELL")
        self.assertEqual([item["reason"] for item in payload["missing"] if item["id"] == "usable_daily_bars"], ["history_contains_non_numeric_values"])

    def test_the_session_a_breach_is_recorded_against_is_the_one_the_bar_names(self) -> None:
        """A UTC-stamped history is the same history, and the audit read it a day early."""

        frame = held()
        frame.iloc[list(frame.index).index(pd.Timestamp(ENTRY)) + 10, frame.columns.get_loc("Low")] = 90.0
        naive = risk(frame)
        utc = risk(frame.tz_localize("UTC"))

        self.assertEqual(naive["data"]["verdict"], "SELL")
        self.assertEqual(utc["data"]["verdict"], "SELL")
        self.assertEqual(utc["data"]["completed_price_path"]["breach_date"], naive["data"]["completed_price_path"]["breach_date"])

    def test_the_current_price_is_not_read_off_whichever_row_came_last(self) -> None:
        """With no numeric level to audit, the close was `iloc[-1]` of the raw frame.

        The provider's row order is not the session order, and the frame can reach past the
        session being analysed. Both were read straight through: an out-of-order frame reported
        an earlier session's close as current, and a frame carrying a later session reported a
        price from a session this analysis has not reached.
        """

        frame = held()
        out_of_order = pd.concat([frame.iloc[[-1]], frame.iloc[:-1]])
        later = frame.iloc[[-1]] * 2
        later.index = pd.DatetimeIndex([frame.index[-1] + pd.Timedelta(days=4)])
        reaches_ahead = pd.concat([frame, later])

        condition = {"condition": "closes below the 21-day average"}
        shuffled = risk(out_of_order, stop_price=None, invalidation=condition)
        ahead = risk(reaches_ahead, stop_price=None, invalidation=condition)

        self.assertEqual(shuffled["data"].get("current_price"), float(frame["Close"].iloc[-1]))
        self.assertEqual(ahead["data"].get("current_price"), float(frame["Close"].iloc[-1]))


if __name__ == "__main__":
    unittest.main()
