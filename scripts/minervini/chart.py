"""Render auditable chart artifacts from completed provider OHLCV data only."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import date
from pathlib import Path
from collections.abc import Mapping, Sequence
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np
import pandas as pd

from .setup_structure import bars_fingerprint, read_bars
from .power_play_evidence import build_power_play_evidence, power_play_fingerprint
from .swings import canonical_chain


# 1.1.0 draws the detector's turning points and pivot, and records per timeframe which
# of them the picture actually contains.
class UnusableOutputDirectory(ValueError):
    """The requested destination cannot hold artifacts, for a reason the caller can change."""


_UNUSABLE = (
    "{directory} cannot hold this render's files: {error}. Give --output-dir a directory whose "
    "contents this process may write, or clear what is in the way."
)


class ArtifactNameTaken(ValueError):
    """This directory already holds a different render under the name this one would use.

    Its own type for the reason UnrenderableHistory has one: a caller told only that a
    ValueError escaped cannot tell a name they can move from a defect they cannot.
    """


class UnrenderableHistory(ValueError):
    """Price history this boundary will not draw, named so a caller can tell it from a bug.

    The renderer refuses bad data and bad requests with the same exception type, and a handler
    that caught every ValueError reported a malformed ticker -- and any genuine defect in the
    plotting stack -- as though the provider had returned unusable bars.
    """


RENDERER_VERSION = "1.2.0"
_REQUIRED_COLUMNS = ("Open", "High", "Low", "Close", "Volume")
_TICKER_PATTERN = re.compile(r"[A-Z][A-Z0-9.-]{0,9}")


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
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        # A path that is a file, or under one. Both are the caller's to change, and an unhandled
        # OSError became an internal_error naming `[Errno 17] File exists`, which reads as a
        # defect in the renderer.
        raise UnusableOutputDirectory(f"{directory} cannot hold chart artifacts: {error}") from error
    # And one that exists but this process cannot write. `mkdir(exist_ok=True)` is happy with it
    # and the first write is several steps later, so the caller got the same internal_error for
    # a directory they could have chosen differently.
    if not os.access(directory, os.W_OK):
        raise UnusableOutputDirectory(f"{directory} cannot hold chart artifacts: not writable")

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
    power_play = _power_play_spans(daily, input_sha256)
    # And the overlay's own input joins the name, for the reason the price digest is in it.
    # `input_sha256` cannot see a split, so two vintages differing only there wrote the same
    # PNGs and the same manifest over each other: the second render's picture sitting under the
    # first render's digests, which is the mismatched approval the stamp exists to prevent. No
    # suffix where the overlay has no digest -- a history that never said whether a split
    # occurred issues no question, so the only overlay it can carry is the empty one.
    if power_play["measured_bars"] is not None:
        stamp = f"{stamp}-{power_play['measured_bars'][:8]}"
    # And the renderer, because the digests name the input and this name is claimed for the
    # output. Two renders of identical bars under different versions of this module draw
    # different pictures, and with only the input in the name the second wrote its PNGs under
    # the first's manifest -- a bundle whose manifest says 1.2.0 beside a picture stamped
    # 9.9.9. In the name rather than refused, so a version bump writes a new bundle instead of
    # making every directory holding an older one permanently unusable.
    stamp = f"{stamp}-r{RENDERER_VERSION.replace('.', '-')}"
    manifest_path = directory / f"{symbol}_{as_of_date.isoformat()}_{stamp}_manifest.json"
    # Both halves of that stamp are truncated, and a truncated digest is a name two inputs can
    # share. Thirty-two bits of the overlay half were reached in under four seconds by varying
    # split multiples until two histories agreed -- one with a span, one without -- and the
    # second render replaced the first's pictures under the first's manifest. Widening the name
    # only moves the number; what makes it exact is asking the directory.
    #
    # Two claims, because the name is taken over two different spans of time. The finished
    # manifest is the durable one: it says in full what the truncated name only gestures at,
    # and it outlives the render. The other covers the render itself -- three files written one
    # at a time, and asking once at the start leaves a window wide enough that two colliding
    # renders both passed the check, interleaved, and left a manifest naming a span beside
    # pictures that had none, a mismatch answered as `qualified`.
    #
    # That in-flight claim is a file of its own rather than a stub under the manifest's name.
    # Written there it was a manifest with no `artifacts` key for the length of every render,
    # which anything watching the directory reads and fails on -- and worse, a render that
    # failed after another had finished took the *finished* manifest away with it, because the
    # name it thought it owned was the same name. Nothing here ever deletes a manifest.
    #
    # One claim per name, and taken exclusively, so at most one render is ever inside a name.
    # Letting two of the same input draw at once was the more generous rule and it is what made
    # cleanup unanswerable: a render that failed had to decide which of the files under the name
    # were its own, and every rule tried for that -- inode ownership, preexistence, deferring to
    # a live claim -- fell to some interleaving, because a half-written picture and a finished
    # one look alike on disk. Refusing the second render costs its caller a retry and buys the
    # only cleanup rule that needs no such decision: with no claim standing and no manifest
    # written, nothing under this name was ever finished, so the pictures go.
    _refuse_a_taken_name(manifest_path, input_sha256, power_play["measured_bars"])
    try:
        reserved = _reserve_the_name(
            manifest_path.parent / f"{manifest_path.name}.reserving",
            input_sha256,
            power_play["measured_bars"],
        )
    except OSError as error:
        # Taking the claim is already writing to the destination, so the same reasons the
        # drawing can fail apply here -- a filesystem that takes ordinary files but not hard
        # links, a directory that stopped being writable between the check and this line. Both
        # are answered by handing this capability a different one.
        raise UnusableOutputDirectory(_UNUSABLE.format(directory=directory, error=error)) from error
    # And again, now that the reservation is held. The first ask happens before anything is
    # claimed, so a render already drawing can finish in the gap between them: it leaves a
    # manifest this one never saw, and having found no in-flight claim either, this one goes on
    # to write its own bundle over the finished one under the same name. The second ask closes
    # that gap -- after this point no other render can complete without first taking a claim
    # this one would have refused.
    try:
        _refuse_a_taken_name(manifest_path, input_sha256, power_play["measured_bars"])
    except ArtifactNameTaken:
        _release(reserved)
        raise
    try:
        return _draw_the_bundle(
            manifest_path, directory, symbol, stamp, as_of_date,
            daily, weekly, input_sha256, segmentation, power_play,
        )
    except OSError as error:
        # A destination that cannot take the files is the caller's to fix, and it stays that
        # way once the writing starts. A directory sitting where a PNG belongs passed every
        # check above -- the parent was writable and the manifest name was free -- and came
        # back as `internal_error`, which tells a reader the harness is broken when what is
        # broken is the path they handed it.
        _take_back(manifest_path)
        raise UnusableOutputDirectory(_UNUSABLE.format(directory=directory, error=error)) from error
    except BaseException:
        _take_back(manifest_path)
        raise
    finally:
        _release(reserved)


def _draw_the_bundle(
    manifest_path: Path,
    directory: Path,
    symbol: str,
    stamp: str,
    as_of_date: date,
    daily: pd.DataFrame,
    weekly: pd.DataFrame,
    input_sha256: str,
    segmentation: dict[str, Any] | None,
    power_play: dict[str, Any],
) -> dict[str, Any]:
    """Draw both pictures and write the manifest over the claim that reserved its name."""

    # And, where there is a span to look at, the span. A stock with three years of history draws
    # seven hundred sessions into twelve inches, and a four-session flag is a handful of pixels
    # under a marker wider than the flag is -- so the reader was asked whether that flag was
    # tight while looking at something they could not measure. The two whole-history pictures
    # are what a base is read from and are left exactly as they were; this one is the span.
    artifact_specs = [("weekly", weekly), ("daily", daily)]
    span_bars = _span_window(daily, power_play["spans"])
    if span_bars is not None:
        artifact_specs.append(("power_play", span_bars))
    artifacts: list[dict[str, Any]] = []
    for timeframe, bars in artifact_specs:
        path = directory / f"{symbol}_{as_of_date.isoformat()}_{stamp}_{timeframe}.png"
        drawn, pivot_drawn, span_drawn = _render_png(
            bars, path, symbol, timeframe, as_of_date, segmentation, power_play
        )
        # What the picture contains, rather than what was available to put in it. A reader
        # asked to approve a chain off this chart needs to know which anchors it actually shows.
        #
        # Per landmark for the Power Play, because a flat list of sessions cannot say which of
        # them is missing. A question does not always carry every landmark -- a history ending
        # on the peak has no flag low, one that starts inside the advance has no baseline -- and
        # reported as a list of what was drawn, an absent flag low is indistinguishable from a
        # session this timeframe does not reach. The reader is then looking for a cross that was
        # never drawn with nothing telling them so.
        artifacts.append({
            "timeframe": timeframe, "path": str(path), "bars": len(bars),
            "anchors_drawn": drawn, "pivot_drawn": pivot_drawn,
            "power_play_drawn": span_drawn,
            # A week read before it ends aggregates the sessions it has. Its volume bar is
            # short for that reason and not because the stock went quiet, which is exactly the
            # thing a reader is looking for on this picture.
            "last_bar_partial": timeframe == "weekly" and _week_in_progress(daily, as_of_date),
        })

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


def _inside(box: Any, page: Any) -> bool:
    """Whether every edge of the legend is still on the page."""

    return box.x0 >= page.x0 and box.x1 <= page.x1 and box.y0 >= page.y0 and box.y1 <= page.y1


def _release(reserved: Path) -> None:
    """Give up this render's claim, and never let giving it up be what fails the render.

    Unguarded, a destination that stopped taking changes between the last write and this line
    turned a finished bundle into an exception: every disclosed artifact was on disk and the
    caller got no result naming them. The claim left behind costs a colliding vintage a refusal
    it can clear by hand, which is the cheaper of the two.
    """

    try:
        reserved.unlink(missing_ok=True)
    except OSError:
        pass


def _take_back(manifest_path: Path) -> None:
    """Clear this name of pictures, unless a finished bundle stands under it.

    Clearing at all is worth doing because a bundle that stopped half-way leaves a picture under
    a digest-stamped name beside an envelope reporting nothing written.

    Called with this render's claim held, and the claim is exclusive, so no other render is
    inside this name and none can enter until the claim is given up. That is what makes the
    sweep safe and what four earlier rules were trying to reason around while renders were
    allowed to overlap. A finished manifest is the one thing left to check: this render never
    reached its own, so one standing here belongs to a bundle somebody may already be holding
    paths from.
    """

    try:
        if manifest_path.exists():
            return
        stem = manifest_path.name.removesuffix("_manifest.json")
        abandoned = sorted(manifest_path.parent.glob(f"{stem}_*.png"))
    except OSError:
        return

    for path in abandoned:
        try:
            path.unlink()
        except OSError:
            # The destination is already refusing this render; failing again while tidying up
            # would replace the reason the caller needs with the second one.
            pass


def _reserve_the_name(reserving: Path, input_sha256: str, measured_bars: str | None) -> Path:
    """Take this name for one render at a time, and refuse while anyone else holds it.

    One claim per name, created with `O_EXCL`, so the filesystem decides who gets it and only
    one render is ever inside a name. Two renders of the same input used to be allowed to draw
    at once -- the digests and the renderer all agree, so nothing they wrote could disagree --
    and every rule that tried to make cleanup safe under that permission failed against some
    interleaving of the two. Ownership, preexistence, deferring to a live claim, sweeping the
    whole name: each closed the case the last one missed and left the next. They were all
    trying to reason about a window that need not exist.

    Refusing the second render costs a caller a retry, and buys the one thing the previous four
    rules could not: while this render is drawing, no other render can be. So a directory
    holding no claim and no finished manifest holds no bundle anybody is relying on, which is
    what cleanup needs to be true and could not previously establish.

    A claim outliving its render blocks the name until it is deleted, which is safe to do by
    hand once nothing is running -- and it is a claim on this name only, so any other ticker,
    date, input, or renderer is unaffected.

    Which is also all the refusal can promise. The render being waited on may be this same
    input, and then its manifest is the one the caller wanted; it may be a colliding vintage,
    and then the caller is refused again and wants another directory; and it may fail, and then
    nothing appears under the name at all. "Wait and read its manifest" was true in only the
    first of the three and left the other two waiting for a file nobody was going to write.
    """

    claim = json.dumps(
        {
            "input_sha256": input_sha256,
            "renderer_version": RENDERER_VERSION,
            "power_play": {"measured_bars": measured_bars},
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    try:
        handle = os.open(reserving, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError as clash:
        raise ArtifactNameTaken(
            f"{reserving.name} says another render holds {reserving.name.removesuffix('.reserving')} "
            "right now, and nothing under that name is finished yet. Retry once it ends: it "
            "leaves a manifest there if it succeeded -- this render's own if it was drawn from "
            "the same bars, overlay and renderer, and otherwise a refusal naming whose it is, "
            "which another --output-dir settles -- and nothing at all if it failed. Delete this "
            "claim only when no render is running, which is a killed one having left it behind."
        ) from clash
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        stream.write(claim)
    return reserving


def _refuse_a_taken_name(held_by: Path, input_sha256: str, measured_bars: str | None) -> None:
    """Stop unless the file already at this name was written from this same input by this renderer.

    Reading it back rather than trusting the name is what makes the check exact: the file says
    in full what its truncated name only gestures at. A manifest written before the overlay had
    a digest carries none, and can only share a name with a render whose overlay has none
    either -- so the two agree and the newer picture, drawn from the same bars, replaces it.

    The renderer's own version is part of that identity. The digests name what went in, and
    this name is claimed for what comes out: the same bars through two versions of this module
    are two different pictures, and one replacing the other left a manifest reporting a version
    the picture beside it was not drawn by.

    Nothing at the name is nothing to refuse. Anything else that cannot be read as those three
    is refused, because a name whose holder cannot be identified is a name this render cannot
    prove is its own.
    """

    # `lexists`, because a symlink pointing at nothing is a name this render does not hold and
    # `exists` calls it absent -- so the claim read as free, the render went ahead, and the
    # write followed the link. Anything that is there and cannot be read as these two digests
    # is refused below.
    if not os.path.lexists(held_by):
        return
    manifest_path = held_by
    try:
        taken = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        taken = None
    # Valid JSON that is not an object is still not a manifest, and reaching into it for a
    # digest raised an AttributeError a caller could do nothing with.
    overlay = taken.get("power_play") if isinstance(taken, Mapping) else None
    held = (
        (
            taken.get("input_sha256"),
            overlay.get("measured_bars") if isinstance(overlay, Mapping) else None,
            taken.get("renderer_version"),
        )
        if isinstance(taken, Mapping)
        else (None, None, None)
    )
    if held == (input_sha256, measured_bars, RENDERER_VERSION):
        return
    raise ArtifactNameTaken(
        f"{manifest_path.name} already names bars {held[0]}, an overlay from {held[1]} and "
        f"renderer {held[2]}; this render is {input_sha256}, {measured_bars} and "
        f"{RENDERER_VERSION}. Two inputs reached one name, and "
        "writing would leave the older manifest's digests beside a picture they never named. "
        "Render to another directory. Nothing under this name is this render's to clear: a "
        "claim is the .reserving file beside it, so what stands here is a finished bundle's "
        "manifest, or something else that took the name, and taking it away would strip the "
        "pictures under those digests of the only record of what drew them."
    )


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


# The dated landmarks, in the order a reader meets them on the picture. The manifest reports
# what was drawn under these names, one list each.
_SPAN_LANDMARK_DATES = (
    "advance_anchor_date",
    "peak_date",
    "flag_low_date",
    "advance_peak_volume_date",
    "baseline_first_session",
    "baseline_last_session",
)
_SPAN_LANDMARKS = _SPAN_LANDMARK_DATES + (
    "peak_high",
    "flag_low",
    "advance_peak_volume_ratio",
    "baseline_volume",
)


def _power_play_spans(daily: pd.DataFrame, input_sha256: str) -> dict[str, Any]:
    """The spans the capability is currently asking a person about, and no others.

    An earlier version measured the structure here and decided for itself whether it was worth
    drawing, and both halves of that were wrong. It measured only the highest top while the
    capability walks a chain of candidates and can be asking about a lower one -- so the reader
    got a picture of a top nobody had asked about, carrying the same digest, which meant their
    answer to the wrong question was accepted. And the gate it decided on read the advance from
    low to high where the capability reads it close to close, so a single wick was the
    difference between drawing and not.

    Both disappear if the chart stops having an opinion. The questions already name the top
    they are about, and now the whole span with it, so what is drawn is what is being asked --
    by construction rather than by two measurements agreeing.
    """
    # Built with no readings, which is what makes every question here an open one: answers live
    # in a request and this capability is not in it.
    evidence = build_power_play_evidence(daily)
    spans: list[dict[str, Any]] = []
    seen: set[Any] = set()
    for question in evidence.get("chart_questions") or []:
        # One top can be asked two things -- the volume clause and the flag's tightness -- and
        # they are the same picture. Drawing it twice would stack the markers and double the
        # legend without adding a landmark.
        if question["reading"] in seen:
            continue
        seen.add(question["reading"])
        # Subscripted rather than `.get`: a landmark the question stopped carrying would
        # otherwise arrive as None and be quietly skipped at drawing time, which is a picture
        # missing a mark and a manifest that never says so.
        spans.append(
            {name: question[name] for name in _SPAN_LANDMARKS}
            | {"reading": question["reading"]}
        )
    return {
        "spans": spans,
        # Both digests the question carries, under the words the question uses, because a reader
        # holding two envelopes should be comparing fields of the same name.
        #
        # `drawn_bars` identifies the picture: the five price columns, the value the segmentation
        # carries and the whole page is named by. It cannot identify this overlay. A split inside
        # a span leaves the structure deciding nothing and a payout withholds the criteria it
        # decided, so two histories with identical prices and different events ask different
        # questions -- and on one reproduction asked two while the chart drew no span at all,
        # with `input_sha256` matching on both. Answered off that blank picture, the answer was
        # accepted. `measured_bars` is the input the overlay was actually computed from, and it
        # is null where the history never said whether a split occurred, which is the same
        # abstention the capability makes rather than digesting the absence as zeroes.
        "drawn_bars": input_sha256,
        "measured_bars": power_play_fingerprint(daily),
        "asked_about": [span["peak_date"] for span in spans],
    }


# Timeframes whose bars are sessions. The Power Play panel is a daily chart of one span, so
# everything that turns on "is a bar one session" answers the same for both.
_BY_SESSION = ("daily", "power_play")
# Enough room before the quiet window that its left edge is visible as an edge.
_SPAN_CONTEXT_SESSIONS = 5
_PANEL_TITLES = {"weekly": "Weekly", "daily": "Daily", "power_play": "Power Play"}


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
        width = 0.65 if timeframe in _BY_SESSION else 3.25
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
) -> dict[str, list[str]]:
    """Put the spans being asked about on the picture the volume clause is judged from.

    Three things each question needs and the chart did not have. The advance: where it started
    and the peak it ended on, because "commences" is a claim about a place in a move. The
    baseline: the quiet window the ratio was divided by, shaded under the volume bars so the
    comparison is one a person can make with their eyes instead of taking on faith. And the
    heaviest session of the advance, marked on the volume panel rather than the price one --
    the clause is about that bar's volume, and the price panel is not where anybody judges it.

    Every span the capability has an open question about is drawn, because a chain of tops is
    asked about one at a time and a reader answering the third one needs to see the third one.
    Drawn by landmark rather than by span, though: a chain is usually one advance read to
    several tops, so the anchor, the baseline and the heaviest session are the same bar in
    every reading. Per span, the picture stacked identical marks on identical pixels and the
    legend said the same sentence twice with a different date after it.
    """
    spans = (power_play or {}).get("spans") or []
    # One list per landmark, so a landmark the question never carried is an empty list rather
    # than an absence a reader has to guess the cause of.
    drawn: dict[str, list[str]] = {name: [] for name in _SPAN_LANDMARK_DATES}
    if not spans:
        return drawn

    drawn.update(_shade_baselines(volume_axis, bars, spans, timeframe))

    # A landmark earns a date in its label only when the readings disagree about where it is.
    marks = _marks(spans, bars, timeframe, "advance_anchor_date")
    for stamp, days, _readings in marks:
        # Where the advance began is a date, not a price, and a marker sitting at that bar's
        # low is a tick lost among three years of candles -- on a real chart it was invisible,
        # which is the one landmark "commences on huge volume" is a claim about. A rule down
        # the whole panel reads at any scale, and with the star at the other end the move is
        # bracketed rather than dotted.
        #
        # Named for what the anchor is rather than for what the rule looks like it means. The
        # measurement reads the advance from the session *after* this one -- the anchor is by
        # construction the last quiet bar -- so a rule labelled "advance begins" put the start
        # of the move one session early, on exactly the judgment the reader is here to make.
        price_axis.axvline(stamp, color="#7a5af5", linewidth=1.1, linestyle="--", alpha=0.8, label=f"advance begins after this session{_names(marks, days)}")
        drawn["advance_anchor_date"].extend(days)

    # Hollow, and behind the swing anchors rather than on top of them. A Power Play peak often
    # is a detected swing high -- on MRNA the two were the same bar at the same price -- and a
    # filled marker drawn afterwards covered the blue one completely while the manifest went on
    # reporting that the anchor had been drawn.
    for date_field, price_field, marker, label, edge in (
        ("peak_date", "peak_high", "*", "advance peak", max),
        ("flag_low_date", "flag_low", "x", "flag low", min),
    ):
        marks = _marks(spans, bars, timeframe, date_field)
        for stamp, days, readings in marks:
            # One mark for the bar, so it goes where that bar's readings reached: the highest of
            # the tops merged into it, the lowest of the flag lows. Any other choice draws a
            # star under a candle whose high is one of the very readings it stands for.
            levels = [float(span[price_field]) for span in readings if span.get(price_field) is not None]
            level = edge(levels) if levels else float(bars.loc[stamp, "Low"])
            price_axis.plot(
                [stamp], [level], marker=marker, color="#7a5af5", markersize=13, linestyle="none",
                markerfacecolor="none", markeredgewidth=1.6, zorder=1.5,
                label=f"{label}{_names(marks, days)}",
            )
            drawn[date_field].extend(days)

    marks = _marks(spans, bars, timeframe, "advance_peak_volume_date")
    for stamp, days, readings in marks:
        # The ratio and the window it was divided by, together. The multiple is a claim about a
        # division, so agreeing on the answer is not enough: two readings that used different
        # quiet windows can land on the same number, and printing it beside a mark that stands
        # for both puts two shades under one arithmetic the reader is invited to check.
        divisions = {
            (
                span["advance_peak_volume_ratio"],
                span.get("baseline_first_session"),
                span.get("baseline_last_session"),
            )
            for span in readings
            if span.get("advance_peak_volume_ratio") is not None
        }
        # The ratio belongs on the daily picture and only there. It divides one session's
        # volume by a session baseline, and a weekly bar is a sum of five -- printing "6.0x"
        # beside a weekly bar that towers over the ones after it invites the reader to check
        # the arithmetic against bars it was never computed from. The week is still marked,
        # because the weekly is read first and knowing which week holds the event is what sends
        # a reader to the right place on the daily. And readings that divided by different
        # baselines print no ratio either: one number beside a mark that stands for two of them
        # names neither.
        if timeframe in _BY_SESSION and len(divisions) == 1:
            # "x baseline" reads as the shade, and the shade is not what it divided by. The
            # median is, and it is now drawn, so the label names the line rather than the window.
            label = f"heaviest advance session ({_multiple(divisions.pop()[0])}x baseline median)"
        else:
            label = "week of the heaviest advance session" if timeframe == "weekly" else "heaviest advance session"
        volume_axis.plot(
            [stamp], [float(bars.loc[stamp, "Volume"])], marker="v", color="#7a5af5",
            markersize=9, linestyle="none", label=f"{label}{_names(marks, days)}",
        )
        drawn["advance_peak_volume_date"].extend(days)
    return drawn


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
    for (start, end), held in windows.items():
        suffix = f" ({held[0][1]})" if len(windows) > 1 else ""
        volume_axis.axvspan(start, end, color="#7a5af5", alpha=0.12, label=f"baseline volume{suffix}")
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
                levels.pop(), start, end, color="#7a5af5", linewidth=1.4, linestyle=":",
                zorder=2.5, label=f"baseline median{suffix}",
            )
        for name, day in held:
            drawn[name].append(day)
    return drawn


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
