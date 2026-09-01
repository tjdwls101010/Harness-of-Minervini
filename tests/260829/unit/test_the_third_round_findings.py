"""What the regression-only round found in the code the second round produced.

The second round stopped measuring a session's low against its own high, because a daily bar
never records whether its high or its low printed first. But a completed bar does record one
ordering the second round threw away with the rest: the open prints before both. When the open
is itself a new peak, the decline from that open to the same bar's low is a sequence the source's
"peak to low" fully supports -- and the second round's fix reported it as if it never happened.
"""

from __future__ import annotations

from datetime import date
import unittest

import pandas as pd

from scripts.minervini import doctrine
from scripts.minervini.market_evidence import build_market_evidence


# Enough completed sessions for the window to span the 52 weeks it names. A business-day
# range skips weekends and no holidays, so 52 x the trading week reaches back only 361
# calendar days -- three short of the year the window is bounded by.
SESSIONS = 270
_FIRST_SESSION = pd.Timestamp("2025-01-02")


def _session(index: int) -> str:
    """The index-th business day of a run ending on a fixed session.

    Ordering tokens were enough while the window was a bar count. It is bounded by date now,
    so a fixture has to state sessions a calendar can measure a year across.
    """

    return (_FIRST_SESSION + pd.tseries.offsets.BDay(index)).date().isoformat()


def _bars(rows: list[tuple[float, float, float, float | None]]) -> list[dict[str, object]]:
    """Rows of (high, low, close, open); open is omitted from the bar when it is None."""

    bars: list[dict[str, object]] = []
    for index, (high, low, close, opened) in enumerate(rows):
        bar: dict[str, object] = {"date": _session(index), "high": high, "low": low, "close": close, "completed": True}
        if opened is not None:
            bar["open"] = opened
        bars.append(bar)
    return bars



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

def _lead(rows: list[tuple[float, float, float, float | None]]) -> dict[str, object]:
    evidence = build_market_evidence(
        qqq_daily_ohlcv=None,
        finviz_html=None,
        sector_rows=None,
        industry_rows=None,
        leader_rows=[{"ticker": "LEAD"}],
        trade_traction={"state": "supports"},
        leader_history={"LEAD": _bars(rows)},
        leader_groups=None,
        as_of=_reading_date({"LEAD": _bars(rows)}),
    )
    return evidence["leaders"][0]


class OpenConfirmsAnIntrabarDecline(unittest.TestCase):
    """The same last bar -- high 100, low 40, close 95 -- reads two ways, and the open is the
    only thing that changes between them. Reported, the open is a new peak known to precede the
    low, so 100 to 40 is a 60% decline the source's ceiling refuses. Withheld, the high and low
    are unordered again and the low is measured only from the 70 the prior sessions established,
    a 42.9% the ceiling passes. The second round read every such bar the withheld way."""

    def test_an_open_that_makes_a_new_peak_measures_its_own_low_against_that_open(self) -> None:
        rows = [(70.0, 69.0, 69.5, None)] * (SESSIONS - 1) + [(100.0, 40.0, 95.0, 100.0)]
        leader = _lead(rows)

        self.assertAlmostEqual(leader["correction_depth"]["measured"], 60.0, places=6)
        self.assertEqual(leader["correction_gate"]["state"], "fail")

    def test_the_same_bar_with_no_open_reported_measures_only_from_the_prior_peak(self) -> None:
        rows = [(70.0, 69.0, 69.5, None)] * (SESSIONS - 1) + [(100.0, 40.0, 95.0, None)]
        leader = _lead(rows)

        self.assertAlmostEqual(leader["correction_depth"]["measured"], 42.8571428571, places=6)
        self.assertEqual(leader["correction_gate"]["state"], "pass")


if __name__ == "__main__":
    unittest.main()
