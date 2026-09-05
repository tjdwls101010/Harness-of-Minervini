"""Measured anchors, bands and labels drawn on chart panels."""

from __future__ import annotations

from typing import Any
import pandas as pd


# Timeframes whose bars are sessions. The Power Play panel is a daily chart of one span, so
# everything that turns on "is a bar one session" answers the same for both.
_BY_SESSION = ("daily", "power_play")
# Enough room before the quiet window that its left edge is visible as an edge.
_SPAN_CONTEXT_SESSIONS = 5


def _span_window(daily: pd.DataFrame, spans: list[dict[str, Any]]) -> pd.DataFrame | None:
    """The sessions the questions are about, from the quiet window through the last bar.

    Back to the earliest baseline or advance start across every span, because the ratio is a
    comparison with that window and a panel that cuts it off asks the reader to take the
    denominator on faith. A little context before it, so the advance begins somewhere on the
    picture rather than at its left edge.
    """

    starts = [
        pd.Timestamp(span[field])
        for span in spans
        for field in ("baseline_first_session", "advance_anchor_date")
        if span.get(field) is not None
    ]
    if not starts:
        return None
    position = int(daily.index.searchsorted(min(starts)))
    # A start past the last bar is a span this frame does not hold, and slicing from it would
    # hand back the final few sessions as though they were the structure.
    if position >= len(daily.index):
        return None
    window = daily.iloc[max(0, position - _SPAN_CONTEXT_SESSIONS):]
    return window if len(window) > 1 else None


def _price_overlays(close: pd.Series, timeframe: str) -> dict[str, pd.Series]:
    """The averages this panel draws, by the scale its bars are on.

    None at all on the Power Play panel. An average over one span is not the average the daily
    panel draws at the same dates, and two pictures printing different lines under one name is
    the quiet disagreement this overlay exists to stop. Worse, the weekly set is the fallback,
    so a lapse here labels numbers computed from single sessions `SMA 10W`. That panel is for
    the flag's shape and the volume comparison; the averages are read off the daily.
    """

    if timeframe == "power_play":
        return {}
    if timeframe == "daily":
        return {
            "EMA 10": close.ewm(span=10, adjust=False, min_periods=10).mean(),
            "EMA 21": close.ewm(span=21, adjust=False, min_periods=21).mean(),
            "SMA 50": close.rolling(50, min_periods=50).mean(),
        }
    return {
        "SMA 10W": close.rolling(10, min_periods=10).mean(),
        "SMA 30W": close.rolling(30, min_periods=30).mean(),
        "SMA 40W": close.rolling(40, min_periods=40).mean(),
    }


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


def _multiple(ratio: float) -> str:
    """The ratio at a decimal that cannot put it on the wrong side of one.

    One decimal is the right precision for judging whether volume expanded, and everywhere but
    one place it is harmless. That place is 1.0: a published 1.04 printed as `1.0x` says the
    advance's heaviest session merely matched its baseline, and exceeding the baseline is the
    exact condition that makes this question exist. Falling short of it reads the same way from
    the other side -- 0.999 printed as `1.00x` claims a session matched a baseline it did not.
    So the printed value takes as many digits as it needs to stay on the side of one the
    measurement is actually on, rather than a rounding that argues against the number it came
    from.
    """

    if ratio == 1.0:
        return "1.0"
    for places in range(1, 7):
        printed = f"{ratio:.{places}f}"
        if float(printed) != 1.0:
            return printed
    # Closer to one than six decimals can separate. Saying so is the honest reading; a seventh
    # digit would be arithmetic about a difference nobody can act on.
    return "about 1.0"


def _marks(
    spans: list[dict[str, Any]], bars: pd.DataFrame, timeframe: str, field: str
) -> list[tuple[pd.Timestamp, list[str], list[dict[str, Any]]]]:
    """The bars of this chart a landmark falls on, each with the readings that put it there.

    A chain read to three tops shares one advance, so its anchor is one bar and wants one legend
    entry. The peaks are what differ, and only then is a date after the label doing any work.

    Deduping those by the date alone and mapping onto a bar afterwards is what drew five stars
    at three positions on a weekly panel while the legend listed five. The key is not on the
    picture and never will be, so that legend is all a reader has to tell one mark from another
    -- and at that point it told them nothing. A bar is what a reader can point at, so a bar is
    what a mark and its entry are counted in.
    """
    marks: dict[Any, tuple[list[str], list[dict[str, Any]]]] = {}
    for span in spans:
        value = span.get(field)
        if value is None:
            continue
        day = str(value)
        stamp = _containing_bar(bars.index, day, timeframe)
        if stamp is None:
            continue
        days, readings = marks.setdefault(stamp, ([], []))
        if day not in days:
            days.append(day)
        readings.append(span)
    return [(stamp, days, readings) for stamp, (days, readings) in marks.items()]


def _names(marks: list[tuple[Any, list[str], Any]], days: list[str]) -> str:
    """What to put after a label so the reader can tell this mark from the others like it."""

    if len({day for _stamp, held, _readings in marks for day in held}) < 2:
        return ""
    return f" ({', '.join(days)})"


def _shade_baselines(
    volume_axis: Any, bars: pd.DataFrame, spans: list[dict[str, Any]], timeframe: str
) -> dict[str, list[str]]:
    """The quiet windows the ratios were measured against, one shade per distinct window."""

    drawn: dict[str, list[str]] = {"baseline_first_session": [], "baseline_last_session": []}
    windows: dict[tuple[Any, Any], list[tuple[str, str]]] = {}
    divisors: dict[tuple[Any, Any], set[float]] = {}
    for span in spans:
        first, last = span.get("baseline_first_session"), span.get("baseline_last_session")
        if not (first and last):
            continue
        start = _containing_bar(bars.index, str(first), timeframe)
        end = _containing_bar(bars.index, str(last), timeframe)
        if start is None or end is None:
            continue
        if span.get("baseline_volume") is not None:
            divisors.setdefault((start, end), set()).add(float(span["baseline_volume"]))
        # Keyed by the shade rather than by the window, for the reason the markers are: two
        # windows a week apart are one rectangle here, and two entries behind one rectangle
        # say the panel is showing something it is not.
        held = windows.setdefault((start, end), [])
        for name, day in (("baseline_first_session", str(first)), ("baseline_last_session", str(last))):
            if (name, day) not in held:
                held.append((name, day))
    # A bar is drawn centred on its session, so a shade running centre to centre leaves half of
    # each boundary bar outside a window that counted the whole of it. The reader's question on
    # this panel is which bars the median was taken over, and they answer it by looking at what
    # the shade covers: on a real ABCL render the first and last sessions of the window were
    # half in and half out of the rectangle their own volume is inside of.
    edge = pd.Timedelta(days=_bar_width(timeframe) / 2)
    for (start, end), held in windows.items():
        suffix = f" ({held[0][1]})" if len(windows) > 1 else ""
        # The same on the weekly, and here the shade cannot even be made to fit: a boundary
        # session's week is one bar, so the rectangle covers every session in it including the
        # ones the window ended before. Naming the weeks rather than the window is what keeps
        # the picture from claiming those sessions were measured.
        # The span the rectangle actually covers, which is not the same as the dates behind it:
        # two windows a week apart are one rectangle here, and joining all four boundary dates
        # produced "the weeks holding 2026-01-29 to 2026-03-25 to 2026-01-30 to 2026-03-24".
        reached = (
            min(day for name, day in held if name == "baseline_first_session"),
            max(day for name, day in held if name == "baseline_last_session"),
        )
        volume_axis.axvspan(
            start - edge, end + edge, color="#7a5af5", alpha=0.12,
            label=(
                f"baseline volume{suffix}"
                if timeframe in _BY_SESSION
                else f"baseline volume -- the weeks holding {reached[0]} to {reached[1]}"
            ),
        )
        # The divisor drawn across the window it was taken over, because it is the one number on
        # this panel a reader cannot point at. Every ratio is a division by the window's median,
        # and the shade alone invites the comparison the eye actually makes -- against the
        # tallest bar inside it. On a quiet window holding one enormous day those are far apart:
        # a session marked "10.5x baseline" can be visibly shorter than a bar in the shade, and
        # a reader checking the arithmetic against what they can see reads the label as false.
        #
        # Session-scale panels only, for the reason the ratio itself is: a weekly bar is five
        # sessions added together, so a line at a session median sits near the floor of a panel
        # it was never measured on.
        levels = divisors.get((start, end), set())
        if timeframe in _BY_SESSION and len(levels) == 1:
            volume_axis.hlines(
                levels.pop(), start - edge, end + edge, color="#7a5af5", linewidth=1.4,
                linestyle=":",
                zorder=2.5, label=f"baseline median{suffix}",
            )
        for name, day in held:
            drawn[name].append(day)
    return drawn


def _bar_width(timeframe: str) -> float:
    """How wide a bar is drawn, in days -- the unit this figure's x axis is in."""

    return 0.65 if timeframe in _BY_SESSION else 3.25


def _containing_bar(index: pd.DatetimeIndex, day: str, timeframe: str) -> pd.Timestamp | None:
    """The bar a session belongs to, or nothing when this chart does not reach it."""

    stamp = pd.Timestamp(day)
    position = int(index.searchsorted(stamp))
    if position >= len(index):
        return None
    label = index[position]
    if timeframe in _BY_SESSION and label != stamp:
        return None
    return label
