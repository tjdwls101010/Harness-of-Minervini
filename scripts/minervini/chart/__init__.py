"""Render auditable chart artifacts from completed provider OHLCV data only."""

from __future__ import annotations

# Keep orchestration lookups here so existing module-level overrides still apply.

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
from ..dates import parse_iso
from ..setup_structure import bars_fingerprint, read_bars
from ..power_play_evidence import build_power_play_evidence, power_play_fingerprint
from ..swings import canonical_chain


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
            daily, weekly, input_sha256, segmentation, power_play, reserved,
        )
    except OSError as error:
        # A destination that cannot take the files is the caller's to fix, and it stays that
        # way once the writing starts. A directory sitting where a PNG belongs passed every
        # check above -- the parent was writable and the manifest name was free -- and came
        # back as `internal_error`, which tells a reader the harness is broken when what is
        # broken is the path they handed it.
        _take_back(manifest_path, reserved)
        raise UnusableOutputDirectory(_UNUSABLE.format(directory=directory, error=error)) from error
    except BaseException:
        _take_back(manifest_path, reserved)
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
    reserved: tuple[Path, int],
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
    _leave_only_this_render_under_the_name(manifest_path, artifacts, reserved)
    _atomic_json(manifest_path, manifest)
    return {**manifest, "manifest_path": str(manifest_path)}


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


from .manifest import ArtifactNameTaken, RENDERER_VERSION, UnrenderableHistory, UnusableOutputDirectory, _PANEL_TITLES, _UNUSABLE, _atomic_json, _inside, _leave_only_this_render_under_the_name, _refuse_a_taken_name, _release, _reserve_the_name, _still_holding, _take_back
from .overlay import _BY_SESSION, _SPAN_CONTEXT_SESSIONS, _bar_width, _containing_bar, _draw_anchors, _draw_power_play, _marks, _multiple, _names, _price_overlays, _shade_baselines, _span_window
from .render import _LEGEND_CORNERS, _REQUIRED_COLUMNS, _TICKER_PATTERN, _as_of_date, _atomic_figure, _completed_daily, _place_clear_of_the_marks, _render_png, _the_volume_being_judged, _ticker, _week_in_progress, _weekly_bars


__all__ = ["RENDERER_VERSION", "UnrenderableHistory", "render_chart_artifacts"]
