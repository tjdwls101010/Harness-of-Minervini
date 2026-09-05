"""Chart panel rendering and timeframe preparation."""

from __future__ import annotations

import os
import re
import tempfile
from datetime import date
from pathlib import Path
from collections.abc import Sequence
from typing import Any
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np
import pandas as pd
from ..dates import parse_iso
from ..setup_structure import read_bars

from .manifest import RENDERER_VERSION, UnrenderableHistory, _PANEL_TITLES, _inside
from .overlay import _bar_width, _draw_anchors, _draw_power_play, _price_overlays


_REQUIRED_COLUMNS = ("Open", "High", "Low", "Close", "Volume")
_TICKER_PATTERN = re.compile(r"[A-Z][A-Z0-9.-]{0,9}")


# Where a legend may go, in the order they are tried. Matplotlib's own "best" is not on the
# list: it minimises overlap with the *data*, which is a different question from the one that
# matters here, and on a real name it chose a corner that covered all but the tip of the mark
# it was explaining.
_LEGEND_CORNERS = ("upper left", "upper right", "lower left", "lower right", "center right", "center left")


def _place_clear_of_the_marks(axis: Any, *, also: Sequence[Any] = ()) -> None:
    """Put the legend somewhere it does not cover the landmarks it names.

    A legend is the only thing carrying a mark back to the question it belongs to, so one
    sitting on the mark costs the reader both. Ordinary bars and candles are a different matter:
    seven hundred of them fill the panel and a legend sits over some wherever it goes. `also` is
    for the ones that are not marks and still may not be covered -- the tallest bar of the
    volume panel, which is what the eye reaches for when checking a multiple.

    Tried rather than computed, because where a legend fits depends on how large it is, and it
    is not measurable until it has been drawn somewhere. Falling through every corner it goes
    above the panel, which is clear of the marks by construction -- and is measured too, because
    a legend wider than the panel runs off the side of the page there, taking its own last entry
    and the axis labels with it. A picture that cannot be read at the edge is no better than one
    whose mark is covered, so the last resort is back inside, in the corner it fits in.
    """

    marks = [line for line in axis.lines if line.get_marker() not in (None, "None", "none", "")]
    marks.extend(also)
    figure = axis.get_figure()
    for corner in _LEGEND_CORNERS:
        legend = axis.legend(loc=corner, fontsize=8, framealpha=0.85)
        figure.canvas.draw()
        box = legend.get_window_extent()
        if not any(box.overlaps(mark.get_window_extent()) for mark in marks):
            return
    # Anchored from the right, because the left is where the axis writes its own scale -- the
    # `1e7` above a volume panel -- and a legend starting there covers the exponent that says
    # what every bar under it is worth.
    for columns, size in ((2, 8), (1, 8), (1, 7)):
        legend = axis.legend(
            loc="lower right", bbox_to_anchor=(1, 1.01), fontsize=size,
            framealpha=0.85, ncol=columns,
        )
        figure.canvas.draw()
        scale = axis.get_yaxis().get_offset_text()
        clear_of_the_scale = not (
            scale.get_text() and legend.get_window_extent().overlaps(scale.get_window_extent())
        )
        if _inside(legend.get_window_extent(), figure.bbox) and clear_of_the_scale:
            return
    # Nothing fits and something has to be drawn: a legend the reader must scroll past is worse
    # than one they must look around, so the last resort is back inside at the smallest size.
    axis.legend(loc="upper left", fontsize=7, framealpha=0.85)


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


def _render_png(bars: pd.DataFrame, path: Path, ticker: str, timeframe: str, as_of: date, segmentation: dict[str, Any] | None = None, power_play: dict[str, Any] | None = None) -> tuple[list[str], bool, dict[str, list[str]]]:
    figure, (price_axis, volume_axis) = plt.subplots(
        2,
        1,
        figsize=(12, 7),
        sharex=True,
        gridspec_kw={"height_ratios": (3, 1)},
        layout="constrained",
    )
    try:
        dates = mdates.date2num(bars.index.to_pydatetime())
        width = _bar_width(timeframe)
        colors = np.where(bars["Close"].to_numpy() >= bars["Open"].to_numpy(), "#18794e", "#b42318")
        for position, (_, row), color in zip(dates, bars.iterrows(), colors, strict=True):
            price_axis.vlines(position, row["Low"], row["High"], color=color, linewidth=0.8)
            body_low = min(row["Open"], row["Close"])
            # A floor in dollars is a floor at a different size on every stock. On a five-cent
            # name it drew a body a fifth taller than the session's whole range, and the axis
            # stretched to fit a candle that never traded -- on the picture a person approves a
            # base's tightness from. The floor is a fraction of the bar's own range instead, so
            # a doji stays a doji at any price.
            body_height = max(abs(row["Close"] - row["Open"]), (row["High"] - row["Low"]) * 0.03)
            # And kept inside the session it belongs to. A doji whose open and close sit at the
            # high got its minimum body drawn upward from there, three percent of the range
            # above a price the stock never traded -- on the picture a person approves a base's
            # tightness from, where the highs are exactly what they are reading.
            body_low = min(body_low, row["High"] - body_height)
            price_axis.add_patch(Rectangle((position - width / 2, body_low), width, body_height, facecolor=color, edgecolor=color, linewidth=0.6))
        for label, values in _price_overlays(bars["Close"], timeframe).items():
            if values.notna().any():
                price_axis.plot(bars.index, values, linewidth=0.9, label=label)
        drawn, pivot_drawn = _draw_anchors(price_axis, bars, segmentation, timeframe)
        volume_axis.bar(bars.index, bars["Volume"], width=width, color=colors, alpha=0.8)
        span_drawn = _draw_power_play(price_axis, volume_axis, bars, power_play, timeframe)
        price_axis.set_title(f"{ticker} {_PANEL_TITLES[timeframe]} — as of {as_of.isoformat()}")
        price_axis.set_ylabel("Price")
        volume_axis.set_ylabel("Volume")
        # Headroom above the tallest bar, because the mark for the heaviest advance session
        # sits on top of it. Left to autoscale, the axis stops at that bar and the triangle is
        # cut in half by the border -- and it is cut on exactly the session the panel is asking
        # about, since the heaviest session is the tallest bar whenever the baseline is quiet.
        top = float(bars["Volume"].max()) if len(bars) else 0.0
        if top > 0:
            volume_axis.set_ylim(0, top * 1.12)
        price_axis.grid(axis="y", alpha=0.25)
        volume_axis.grid(axis="y", alpha=0.25)
        # Both legends here rather than where their marks are drawn, because placing one means
        # measuring it against a figure that exists, and only this function has one.
        for axis, also in (
            (price_axis, ()),
            (volume_axis, _the_volume_being_judged(volume_axis, bars, power_play["spans"])),
        ):
            if axis.get_legend_handles_labels()[0]:
                _place_clear_of_the_marks(axis, also=also)
        volume_axis.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
        figure.autofmt_xdate(rotation=30, ha="right")
        _atomic_figure(figure, path)
        return drawn, pivot_drawn, span_drawn
    finally:
        plt.close(figure)


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
