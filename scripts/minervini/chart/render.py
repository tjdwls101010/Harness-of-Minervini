"""Timeframe and volume preparation for chart rendering."""

from __future__ import annotations

import os
import re
import tempfile
from datetime import date
from pathlib import Path
from typing import Any
import matplotlib.pyplot as plt
import pandas as pd
from ..dates import parse_iso
from ..setup_structure import read_bars

from .manifest import RENDERER_VERSION, UnrenderableHistory


_REQUIRED_COLUMNS = ("Open", "High", "Low", "Close", "Volume")
_TICKER_PATTERN = re.compile(r"[A-Z][A-Z0-9.-]{0,9}")


# Where a legend may go, in the order they are tried. Matplotlib's own "best" is not on the
# list: it minimises overlap with the *data*, which is a different question from the one that
# matters here, and on a real name it chose a corner that covered all but the tip of the mark
# it was explaining.
_LEGEND_CORNERS = ("upper left", "upper right", "lower left", "lower right", "center right", "center left")


def _the_volume_being_judged(
    volume_axis: Any, bars: pd.DataFrame, spans: list[dict[str, Any]]
) -> list[Any]:
    """The volume bars a covered legend would cost the reader an answer.

    Two regions, because two criteria are open on this picture. The multiple is a comparison
    against the quiet window, so that window's own tallest bar is where the eye goes to check
    it -- and the tallest bar of the whole panel is a different bar, usually inside the advance,
    so protecting that one left the baseline's under the legend whenever the advance ran
    heavier, which is nearly always. The flag is the other: whether volume dried up across it
    is half of what the tightness criterion asks, and on a real name the legend sat over every
    session of both flags at once.
    """

    protected: list[Any] = []
    for span in spans:
        windows = [
            (span.get("baseline_first_session"), span.get("baseline_last_session")),
        ]
        for first, last in windows:
            if not (first and last):
                continue
            window = bars.loc[str(first):str(last)]
            if window.empty:
                continue
            reached = float(window["Volume"].max())
            protected.extend(
                patch for patch in volume_axis.patches
                if patch.get_height() and abs(patch.get_height() - reached) < 1e-9
            )
        # The flag runs from the peak to the end of what is drawn, and every session of it is
        # evidence rather than only its tallest: a dry-up is read across the run.
        peak = span.get("peak_date")
        if peak is None:
            continue
        flag = bars.loc[str(peak):]
        for reached in {float(value) for value in flag["Volume"] if value}:
            protected.extend(
                patch for patch in volume_axis.patches
                if patch.get_height() and abs(patch.get_height() - reached) < 1e-9
            )
    return protected


def _ticker(value: str) -> str:
    symbol = str(value).strip().upper()
    if not _TICKER_PATTERN.fullmatch(symbol):
        raise ValueError("ticker must be a US-listed symbol")
    return symbol


def _as_of_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    result = parse_iso(value)
    if result is None:
        raise ValueError("as_of must be an ISO date")
    return result


def _completed_daily(daily_ohlcv: pd.DataFrame, as_of: date) -> pd.DataFrame:
    if not isinstance(daily_ohlcv, pd.DataFrame):
        raise UnrenderableHistory("daily_ohlcv must be a DataFrame")
    missing = [column for column in _REQUIRED_COLUMNS if column not in daily_ohlcv.columns]
    if missing:
        # The shared vocabulary, with the columns named after it: the contract says both surfaces
        # refuse in the same words, and one of them was using its own for this case.
        raise UnrenderableHistory(
            f"daily_ohlcv is not usable price history: history_missing_required_columns ({', '.join(missing)})"
        )
    if daily_ohlcv.empty:
        raise UnrenderableHistory("daily_ohlcv contains no completed bars")

    # The measuring boundary owns what a usable bar is and how its index is read, so the frame
    # this renders is the frame that gets measured. Normalising here as well is how the two came
    # to disagree about a tz-aware index: one kept the wall clock, the other converted to UTC,
    # and the same session landed on two different dates.
    bars, rejection = read_bars(daily_ohlcv)
    if rejection is not None:
        raise UnrenderableHistory(f"daily_ohlcv is not usable price history: {rejection}")
    if bars is None or bars.empty:
        raise UnrenderableHistory("daily_ohlcv contains no completed bars")
    if bars.index[-1].date() > as_of:
        raise UnrenderableHistory("daily_ohlcv contains a bar after as_of")
    return bars


def _weekly_bars(daily: pd.DataFrame, as_of: date) -> pd.DataFrame:
    weekly = daily.resample("W-FRI").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    ).dropna()
    # No filter on the label: every bucket here aggregates completed sessions only, because
    # the daily frame was already cut at as_of. Dropping buckets whose Friday label falls
    # after it deleted the most recent week whenever that Friday was a holiday -- Good Friday
    # takes the last completed week and its anchors off the chart, and on a short history it
    # raised instead.
    if weekly.empty:
        raise UnrenderableHistory("daily_ohlcv contains no completed weekly bars as_of")
    return weekly


def _week_in_progress(daily: pd.DataFrame, as_of: date) -> bool:
    """Whether the last weekly bucket is still collecting sessions."""

    last = daily.index[-1]
    friday = last + pd.Timedelta(days=(4 - last.weekday()) % 7)
    return bool(friday.date() > as_of)


def _atomic_figure(figure: plt.Figure, path: Path) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix=f".{path.stem}-", suffix=".png", dir=path.parent, delete=False) as handle:
            temporary_path = Path(handle.name)
        figure.savefig(temporary_path, format="png", dpi=150, metadata={"Software": f"minervini-chart/{RENDERER_VERSION}"})
        if temporary_path.stat().st_size == 0:
            raise ValueError("chart renderer produced an empty PNG")
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
