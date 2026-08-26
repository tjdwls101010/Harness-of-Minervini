"""Render auditable chart artifacts from completed provider OHLCV data only."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import date
from pathlib import Path
from collections.abc import Mapping
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np
import pandas as pd

from .setup_structure import bars_fingerprint, read_bars
from . import doctrine
from .power_play import measure_power_play
from .power_play_evidence import compile_power_play_spec
from .swings import canonical_chain


# 1.1.0 draws the detector's turning points and pivot, and records per timeframe which
# of them the picture actually contains.
class UnrenderableHistory(ValueError):
    """Price history this boundary will not draw, named so a caller can tell it from a bug.

    The renderer refuses bad data and bad requests with the same exception type, and a handler
    that caught every ValueError reported a malformed ticker -- and any genuine defect in the
    plotting stack -- as though the provider had returned unusable bars.
    """


RENDERER_VERSION = "1.1.0"
_REQUIRED_COLUMNS = ("Open", "High", "Low", "Close", "Volume")
_TICKER_PATTERN = re.compile(r"[A-Z][A-Z0-9.-]{0,9}")
_CLAIM = "fundamentals.power_play_exception"


def render_chart_artifacts(
    daily_ohlcv: pd.DataFrame,
    *,
    ticker: str,
    as_of: str | date,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Render weekly then daily PNGs and a colocated provenance manifest.

    ``daily_ohlcv`` is already-completed provider data. This boundary performs no
    provider lookup and rejects data outside the explicit ``as_of`` session.
    """
    symbol = _ticker(ticker)
    as_of_date = _as_of_date(as_of)
    daily = _completed_daily(daily_ohlcv, as_of_date)
    directory = Path(output_dir).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)

    # The same digest the segmentation carries, so an approval can be traced to its picture.
    input_sha256 = bars_fingerprint(daily)
    # The bars a set of artifacts came from are part of where they are written. Keyed only by
    # ticker and session, two renders of different history into one directory interleave: each
    # file replaces atomically but the set does not, so a manifest could name one digest while
    # the picture beside it came from another. That digest is what a setup approval cites, so a
    # collision is a person approving a chart they never saw.
    stamp = input_sha256[:12]
    weekly = _weekly_bars(daily, as_of_date)
    # The chart is where a person turns the detector's proposal into an approval, so it draws
    # what they are being asked to approve. A chart without the anchors makes that approval a
    # formality: agreeing to a list of dates while looking at a picture that never names them.
    segmentation = canonical_chain(daily)
    # The other structure a person is asked to look at. `ticker power-play` cannot settle the
    # volume clause on its own -- the source says "commences on huge volume" and names no
    # number -- so it hands back a question and waits. Sending that reader to a picture with
    # none of the span on it asks them about a session the chart never identifies.
    power_play = _power_play_span(daily, input_sha256)
    artifact_specs = (("weekly", weekly), ("daily", daily))
    artifacts: list[dict[str, Any]] = []
    for timeframe, bars in artifact_specs:
        path = directory / f"{symbol}_{as_of_date.isoformat()}_{stamp}_{timeframe}.png"
        drawn, pivot_drawn, span_drawn, volume_marked = _render_png(
            bars, path, symbol, timeframe, as_of_date, segmentation, power_play
        )
        # What the picture contains, rather than what was available to put in it. A reader
        # asked to approve a chain off this chart needs to know which anchors it actually shows.
        artifacts.append({
            "timeframe": timeframe, "path": str(path), "bars": len(bars),
            "anchors_drawn": drawn, "pivot_drawn": pivot_drawn,
            "power_play_drawn": span_drawn, "heaviest_advance_session_drawn": volume_marked,
            # A week read before it ends aggregates the sessions it has. Its volume bar is
            # short for that reason and not because the stock went quiet, which is exactly the
            # thing a reader is looking for on this picture.
            "last_bar_partial": timeframe == "weekly" and _week_in_progress(daily, as_of_date),
        })

    manifest_path = directory / f"{symbol}_{as_of_date.isoformat()}_{stamp}_manifest.json"
    manifest = {
        "renderer_version": RENDERER_VERSION,
        "ticker": symbol,
        "as_of": as_of_date.isoformat(),
        "input_sha256": input_sha256,
        "paths": {artifact["timeframe"]: artifact["path"] for artifact in artifacts},
        "segmentation": segmentation,
        "power_play": power_play,
        "artifacts": artifacts,
    }
    _atomic_json(manifest_path, manifest)
    return {**manifest, "manifest_path": str(manifest_path)}


def _ticker(value: str) -> str:
    symbol = str(value).strip().upper()
    if not _TICKER_PATTERN.fullmatch(symbol):
        raise ValueError("ticker must be a US-listed symbol")
    return symbol


def _as_of_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise ValueError("as_of must be an ISO date") from error


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


_SPAN_LANDMARKS = (
    "advance_anchor_date",
    "peak_date",
    "flag_low_date",
    "advance_peak_volume_date",
    "baseline_first_session",
    "baseline_last_session",
)


def _power_play_span(daily: pd.DataFrame, input_sha256: str) -> dict[str, Any]:
    """The landmarks the Power Play numbers were read between, and nothing derived here.

    Every value is lifted from the measurement rather than recomputed, so the picture cannot
    disagree with the capability that asked the question. The digest travels with them for the
    same reason the segmentation's does: an approval cites it, and a span measured from other
    bars than the picture was cut from is an approval of something the reader never saw.
    """
    measured = measure_power_play(daily, compile_power_play_spec())
    span = {name: measured.get(name) for name in _SPAN_LANDMARKS}
    span["peak_high"] = measured.get("peak_high")
    span["flag_low"] = measured.get("flag_low")
    span["advance_peak_volume_ratio"] = measured.get("advance_peak_volume_ratio")
    span["rejection"] = measured.get("rejection")
    span["drawn_because"] = _why_draw(measured)
    span["bars_fingerprint"] = input_sha256
    return span


def _why_draw(measured: Mapping[str, Any]) -> str | None:
    """Whether this history holds an advance the volume clause could be asked about.

    The arithmetic succeeds on any history -- a placid base has a highest bar, a first bar of
    its rise and a quiet window before it, and reporting those as a Power Play span would put
    a claim on the picture that no measurement made. What separates the two is the pair of
    gates the source states about the advance itself, so they are read from the registry
    rather than restated here: the same numbers the capability decides on, asked here only as
    "is there an explosive move at all", which is the precondition for the question existing.

    This is not a verdict and cannot become one. Everything after the advance -- the flag, the
    volume clause, the market -- is the capability's to decide and a chart may not anticipate it.
    """
    if measured.get("rejection") is not None:
        return None
    advance_pct, advance_weeks = measured.get("advance_pct"), measured.get("advance_weeks")
    if advance_pct is None or advance_weeks is None:
        return None
    minimum = doctrine.evaluate_gate(_CLAIM, "advance_minimum_pct", float(advance_pct))
    maximum = doctrine.evaluate_gate(_CLAIM, "advance_maximum_weeks", float(advance_weeks))
    return "advance_gates_met" if {minimum["state"], maximum["state"]} == {"pass"} else None


def _render_png(bars: pd.DataFrame, path: Path, ticker: str, timeframe: str, as_of: date, segmentation: dict[str, Any] | None = None, power_play: dict[str, Any] | None = None) -> tuple[list[str], bool, list[str], bool]:
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
        width = 0.65 if timeframe == "daily" else 3.25
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
            price_axis.add_patch(Rectangle((position - width / 2, body_low), width, body_height, facecolor=color, edgecolor=color, linewidth=0.6))
        close = bars["Close"]
        if timeframe == "daily":
            overlays = {"EMA 10": close.ewm(span=10, adjust=False, min_periods=10).mean(), "EMA 21": close.ewm(span=21, adjust=False, min_periods=21).mean(), "SMA 50": close.rolling(50, min_periods=50).mean()}
        else:
            overlays = {"SMA 10W": close.rolling(10, min_periods=10).mean(), "SMA 30W": close.rolling(30, min_periods=30).mean(), "SMA 40W": close.rolling(40, min_periods=40).mean()}
        for label, values in overlays.items():
            if values.notna().any():
                price_axis.plot(bars.index, values, linewidth=0.9, label=label)
        drawn, pivot_drawn = _draw_anchors(price_axis, bars, segmentation, timeframe)
        volume_axis.bar(bars.index, bars["Volume"], width=width, color=colors, alpha=0.8)
        span_drawn, volume_marked = _draw_power_play(price_axis, volume_axis, bars, power_play, timeframe)
        price_axis.set_title(f"{ticker} {timeframe.title()} — as of {as_of.isoformat()}")
        price_axis.set_ylabel("Price")
        volume_axis.set_ylabel("Volume")
        price_axis.grid(axis="y", alpha=0.25)
        volume_axis.grid(axis="y", alpha=0.25)
        if price_axis.get_legend_handles_labels()[0]:
            price_axis.legend(loc="upper left", fontsize=8, frameon=False)
        volume_axis.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
        figure.autofmt_xdate(rotation=30, ha="right")
        _atomic_figure(figure, path)
        return drawn, pivot_drawn, span_drawn, volume_marked
    finally:
        plt.close(figure)


def _draw_anchors(price_axis: Any, bars: pd.DataFrame, segmentation: dict[str, Any] | None, timeframe: str) -> tuple[list[str], bool]:
    """Mark the turning points the detector will corroborate a declared chain against.

    Each anchor goes on the bar that contains its session. On the daily chart that bar is the
    session itself; on the weekly chart it is the week the session fell in, whose label is that
    week's Friday. Requiring the anchor's own date to be a bar left almost every anchor off the
    weekly chart, because a swing lands on a Friday about one time in five.
    """
    anchors = (segmentation or {}).get("anchors") or []
    if not anchors:
        return [], False
    drawn: list[str] = []
    for anchor in anchors:
        stamp = _containing_bar(bars.index, str(anchor["date"]), timeframe)
        if stamp is None:
            continue
        price_axis.plot(
            [stamp], [float(anchor["price"])],
            marker="v" if anchor["kind"] == "high" else "^",
            color="#0b5cad", markersize=7, linestyle="none",
            label="detected swing" if not drawn else None,
        )
        drawn.append(str(anchor["date"]))
    # The pivot line follows the pivot, not the presence of any anchor at all. A mid-week as_of
    # drops the unfinished week, so a pivot that landed on that Monday has no weekly bar -- and
    # a level labelled `pivot` on a chart that does not reach it is a claim about nothing.
    pivot_drawn = anchors[-1]["date"] in drawn
    if pivot_drawn:
        price_axis.axhline(float(anchors[-1]["price"]), color="#0b5cad", linewidth=0.8, linestyle="--", alpha=0.7, label="pivot")
    return drawn, pivot_drawn


def _draw_power_play(
    price_axis: Any,
    volume_axis: Any,
    bars: pd.DataFrame,
    power_play: dict[str, Any] | None,
    timeframe: str,
) -> tuple[list[str], bool]:
    """Put the Power Play span on the picture the volume clause is judged from.

    Three things the question needs and the chart did not have. The advance: where it started
    and the peak it ended on, because "commences" is a claim about a place in a move. The
    baseline: the quiet window the ratio was divided by, shaded under the volume bars so the
    comparison is one a person can make with their eyes instead of taking on faith. And the
    heaviest session of the advance, marked on the volume panel rather than the price one --
    the clause is about that bar's volume, and the price panel is not where anybody judges it.
    """
    span = power_play or {}
    if span.get("drawn_because") is None:
        return [], False
    drawn: list[str] = []

    baseline = _shade_baseline(volume_axis, bars, span, timeframe)
    if baseline:
        drawn.extend(baseline)

    # Each landmark says which one it is. A single shared legend entry leaves a reader
    # looking at a star and a cross with nothing telling them which is the top of the advance
    # and which is the bottom of the flag -- the picture would name the structure without
    # naming any part of it, which is the same silence this whole overlay exists to end.
    # Where the advance began is a date, not a price, and a marker sitting at that bar's low
    # is a tick lost among three years of candles -- on a real chart it was invisible, which is
    # the one landmark "commences on huge volume" is a claim about. A rule down the whole panel
    # reads at any scale, and with the star at the other end the move is bracketed rather than
    # dotted.
    start = span.get("advance_anchor_date")
    stamp = _containing_bar(bars.index, str(start), timeframe) if start else None
    if stamp is not None:
        price_axis.axvline(stamp, color="#7a5af5", linewidth=1.1, linestyle="--", alpha=0.8, label="advance begins")
        drawn.append(str(start))

    for name, price, marker, label in (
        ("peak_date", span.get("peak_high"), "*", "advance peak"),
        ("flag_low_date", span.get("flag_low"), "x", "flag low"),
    ):
        day = span.get(name)
        stamp = _containing_bar(bars.index, str(day), timeframe) if day else None
        if stamp is None:
            continue
        level = float(price) if price is not None else float(bars.loc[stamp, "Low"])
        price_axis.plot(
            [stamp], [level], marker=marker, color="#7a5af5", markersize=10, linestyle="none",
            label=label,
        )
        drawn.append(str(day))

    heaviest = span.get("advance_peak_volume_date")
    stamp = _containing_bar(bars.index, str(heaviest), timeframe) if heaviest else None
    if stamp is None:
        return drawn, False
    # The ratio belongs on the daily picture and only there. It divides one session's volume
    # by a session baseline, and a weekly bar is a sum of five -- printing "6.0x" beside a
    # weekly bar that towers over the ones after it invites the reader to check the arithmetic
    # against bars it was never computed from. The week is still marked, because the weekly is
    # read first and knowing which week holds the event is what sends a reader to the right
    # place on the daily.
    ratio = span.get("advance_peak_volume_ratio")
    if timeframe == "daily" and ratio is not None:
        label = f"heaviest advance session ({ratio:.1f}x baseline)"
    else:
        label = "week of the heaviest advance session" if timeframe == "weekly" else "heaviest advance session"
    volume_axis.plot(
        [stamp], [float(bars.loc[stamp, "Volume"])], marker="v", color="#7a5af5",
        markersize=9, linestyle="none", label=label,
    )
    volume_axis.legend(loc="upper left", fontsize=8, frameon=False)
    drawn.append(str(heaviest))
    return drawn, True


def _shade_baseline(volume_axis: Any, bars: pd.DataFrame, span: dict[str, Any], timeframe: str) -> list[str]:
    """The quiet window the ratio was measured against, or nothing when the chart misses it."""

    first, last = span.get("baseline_first_session"), span.get("baseline_last_session")
    if not first or not last:
        return []
    start = _containing_bar(bars.index, str(first), timeframe)
    end = _containing_bar(bars.index, str(last), timeframe)
    if start is None or end is None:
        return []
    volume_axis.axvspan(start, end, color="#7a5af5", alpha=0.12, label="baseline volume")
    return [str(first), str(last)]


def _containing_bar(index: pd.DatetimeIndex, day: str, timeframe: str) -> pd.Timestamp | None:
    """The bar a session belongs to, or nothing when this chart does not reach it."""

    stamp = pd.Timestamp(day)
    position = int(index.searchsorted(stamp))
    if position >= len(index):
        return None
    label = index[position]
    if timeframe == "daily" and label != stamp:
        return None
    return label


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


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix=f".{path.stem}-", suffix=".json", dir=path.parent, mode="w", encoding="utf-8", delete=False) as handle:
            temporary_path = Path(handle.name)
            json.dump(payload, handle, sort_keys=True, indent=2)
            handle.write("\n")
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


__all__ = ["RENDERER_VERSION", "UnrenderableHistory", "render_chart_artifacts"]
