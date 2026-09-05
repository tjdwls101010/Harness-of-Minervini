"""Artifact ownership, publication and cleanup."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from collections.abc import Mapping
from typing import Any




# 1.1.0 draws the detector's turning points and pivot, and records per timeframe which
# of them the picture actually contains.
class UnusableOutputDirectory(ValueError):
    """The requested destination cannot hold artifacts, for a reason the caller can change."""


_UNUSABLE = (
    "{directory} cannot hold this render's files: {error}. Give --output-dir a directory whose "
    "contents this process may write, or clear what is in the way."
)


class ArtifactNameTaken(ValueError):
    """Something else holds the name this render would use, so it did not draw.

    Two somethings, and the recovery differs. A finished bundle from a different input or
    renderer met this one on a shareable truncated name, and another --output-dir settles it
    for good. Or a render is inside the name right now -- which is refused whoever it is, this
    same input included, since the name holds one render at a time -- and a retry settles that
    one once it ends.

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


def _leave_only_this_render_under_the_name(
    manifest_path: Path, artifacts: list[dict[str, Any]], reserved: tuple[Path, int]
) -> None:
    """Clear strangers from the name, then refuse unless every picture the manifest names is there.

    A picture can outlive the render that drew it: killed before its manifest, and its claim
    deleted by hand the way the refusal says to. The name it leaves behind is shareable, so the
    render that next takes it can be one whose overlay draws a different set of panels -- and
    then two paths are published while a stranded third sits beside them under the same digests,
    reported by nothing. Clearing is safe here for the same reason rollback's sweep is: the
    claim is exclusive, so no other render is inside this name, and a finished manifest at it
    would have refused this render unless it named the same identity -- whose pictures carry
    exactly these names and are being replaced rather than swept.

    Then the paths are asked for, because a manifest is read by somebody who opens what it
    names. Every write here resolves the destination by name rather than by a handle held open,
    so a directory renamed mid-render leaves the earlier pictures in the old one and the later
    ones in whatever now answers to the path -- and the manifest, written last, named all three.
    An exclusive claim cannot prevent that; it is a claim on a name, not on an inode. What it
    can do is not publish the claim.
    """

    # Asked first, because everything below acts on the destination. If this path no longer
    # leads to the directory the claim was taken in, the sweep would be clearing somebody
    # else's name and the check would be reading somebody else's pictures -- and both would
    # pass, since the names are the ones this render expects to find.
    if not _still_holding(reserved):
        raise UnusableOutputDirectory(
            _UNUSABLE.format(
                directory=manifest_path.parent,
                error=(
                    "the claim this render took is no longer the file at its own path, so this "
                    "is not the directory the render started in"
                ),
            )
        )

    kept = {Path(artifact["path"]).name for artifact in artifacts}
    stem = manifest_path.name.removesuffix("_manifest.json")
    for timeframe in _PANEL_TITLES:
        path = manifest_path.parent / f"{stem}_{timeframe}.png"
        if path.name in kept or not path.exists():
            continue
        try:
            path.unlink()
        except OSError:
            # Publishing is the thing worth protecting, and it is protected below. A stranger
            # this render could not remove is one the check either tolerates or catches.
            pass

    # `is_file`, not `exists`. A directory standing where a PNG belongs satisfies "it is there"
    # and satisfies nothing a reader opening it wants.
    absent = [
        artifact["path"] for artifact in artifacts if not Path(artifact["path"]).is_file()
    ]
    if absent:
        raise UnusableOutputDirectory(
            _UNUSABLE.format(
                directory=manifest_path.parent,
                error=(
                    f"{', '.join(Path(path).name for path in absent)} is not a file this render "
                    "can be said to have written, which is the destination having moved or "
                    "been written into under it"
                ),
            )
        )


def _inside(box: Any, page: Any) -> bool:
    """Whether every edge of the legend is still on the page."""

    return box.x0 >= page.x0 and box.x1 <= page.x1 and box.y0 >= page.y0 and box.y1 <= page.y1


def _release(reserved: tuple[Path, int]) -> None:
    """Give up this render's claim, and never let giving it up be what fails the render.

    Unguarded, a destination that stopped taking changes between the last write and this line
    turned a finished bundle into an exception: every disclosed artifact was on disk and the
    caller got no result naming them. The claim left behind costs a colliding vintage a refusal
    it can clear by hand, which is the cheaper of the two.
    """

    path, held = reserved
    try:
        if path.stat().st_ino != held:
            # Somebody else's claim now answers to this path. Deleting it would take a live
            # render's reservation and let a third into a name two are already inside.
            return
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _still_holding(reserved: tuple[Path, int]) -> bool:
    """Whether the claim this render took is still the file at the path it took it under."""

    path, held = reserved
    try:
        return path.stat().st_ino == held
    except OSError:
        return False


def _take_back(manifest_path: Path, reserved: tuple[Path, int]) -> None:
    """Clear this name of pictures, unless a finished bundle stands under it.

    Clearing at all is worth doing because a bundle that stopped half-way leaves a picture under
    a digest-stamped name beside an envelope reporting nothing written.

    Safe only while this render's claim is held, which is what makes the name exclusive: no
    other render is inside it and none can enter until the claim is given up. That is what four
    earlier rules were trying to reason around while renders were allowed to overlap. So the
    claim is asked for first, by inode -- a destination renamed mid-render leaves this path
    leading to a directory another render is inside, holding its own claim and its own
    same-named panels, and sweeping there deletes a live render's work. Nothing there is this
    render's, and nothing is what it takes.

    A finished manifest is the other thing to check: this render never reached its own, so one
    standing here belongs to a bundle somebody may already be holding paths from.
    """

    if not _still_holding(reserved):
        return
    try:
        if manifest_path.exists():
            return
        stem = manifest_path.name.removesuffix("_manifest.json")
        # This renderer's own panel names and nothing else. `{stem}_*.png` also matches whatever
        # a caller put beside the bundle -- an annotated copy, a crop they were working from --
        # and none of that is this render's to take.
        abandoned = [
            path for path in (
                manifest_path.parent / f"{stem}_{timeframe}.png" for timeframe in _PANEL_TITLES
            )
            if path.exists()
        ]
    except OSError:
        return

    for path in abandoned:
        try:
            path.unlink()
        except OSError:
            # The destination is already refusing this render; failing again while tidying up
            # would replace the reason the caller needs with the second one.
            pass


def _reserve_the_name(
    reserving: Path, input_sha256: str, measured_bars: str | None
) -> tuple[Path, int]:
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
            "right now. Retry once it ends: a manifest stands there if it succeeded -- this "
            "render's own if it was drawn from the same bars, overlay and renderer, and "
            "otherwise a refusal naming whose it is, which another --output-dir settles -- and "
            "if it failed, whatever stood under the name before it is what is left. Delete this "
            ".reserving claim only when no render is running, which is a killed render having "
            "left it behind. The manifest beside it is never this render's to remove."
        ) from clash
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        stream.write(claim)
        held = os.fstat(stream.fileno()).st_ino
    # The pathname is not the claim; this file is. A directory renamed out from under a running
    # render leaves the same path answering to a different directory, and every later look at
    # that path -- to give the claim up, to check it is still held -- finds whatever the
    # replacement holds. Giving it up then deleted a *second* render's live claim and let a
    # third in behind it, which is the overlapping-render state this whole rule exists to
    # prevent. So the inode comes along, and both looks compare against it.
    return reserving, held


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
    if held == (None, None, None):
        # Unreadable, or readable and not a manifest. Naming digests here would report a
        # collision nothing established: every identity this render has of it is None.
        standing = (
            f"{manifest_path.name} is held by something this render cannot read as a manifest, "
            "so it cannot be shown to name the same bars, overlay and renderer as this one. A "
            "holder that cannot be identified is a name this render cannot prove is its own."
        )
    else:
        standing = (
            f"{manifest_path.name} already names bars {held[0]}, an overlay from {held[1]} and "
            f"renderer {held[2]}; this render is {input_sha256}, {measured_bars} and "
            f"{RENDERER_VERSION}. Two inputs reached one name, and writing would leave the "
            "older manifest's digests beside a picture they never named."
        )
    raise ArtifactNameTaken(
        standing + " Render to another directory. Nothing under this name is this render's to "
        "clear: a claim is the .reserving file beside it, so what stands here is a finished "
        "bundle's manifest, or something else that took the name, and taking it away would "
        "strip the pictures under those digests of the only record of what drew them."
    )
_PANEL_TITLES = {"weekly": "Weekly", "daily": "Daily", "power_play": "Power Play"}


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
