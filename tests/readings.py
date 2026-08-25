"""The readings a fully-read setup carries, in one place.

Six required conditions, three of them readings a person supplies and one of those only an
independent segmentation can. Spreading that bundle across every test meant each new reading
broke every file at once; collecting it here means a test names only the reading it is about.
"""

from __future__ import annotations

from contextlib import contextmanager

from collections.abc import Sequence

import pandas as pd

from scripts.minervini.setup_structure import bars_fingerprint
from scripts.minervini.swings import canonical_chain


def detected(frame: pd.DataFrame) -> list[str]:
    """The chain the harness's own detector produces for these bars.

    The intended flow: ask for the segmentation, look at the chart, declare what you approved.
    A test that modifies the bars has to re-ask, because the segmentation is of the bars.
    """

    return [anchor["date"] for anchor in canonical_chain(frame)["anchors"]]


def full(frame: pd.DataFrame, chain: Sequence[str], **overrides):
    """Every reading satisfied, with an entry at the pivot and a chain the detector agrees with."""

    pivot = float(frame.loc[chain[-1], "High"]) if len(chain) else None
    readings = {
        "right_side_development": "constructive",
        "chain_completeness": "complete",
        # A reading is of one picture, so it names the bars it was read from. A test that
        # modifies the frame has to re-read here, exactly as an analyst has to re-read a chart.
        "approved_bars": bars_fingerprint(frame),
        "entry_proximity": "at_pivot",
        "entry_price": pivot * 1.001 if pivot else None,
    }
    readings.update(overrides)
    return readings


def power_play_answers(history, chart_readings):
    """The arguments an answered Power Play reading now takes.

    The digest travels with every answer, so a test that skips it is testing a call the request
    boundary refuses. Kept in one place because five modules make the same call.
    """
    from scripts.minervini.setup_structure import bars_fingerprint, read_bars

    return {"chart_readings": chart_readings, "drawn_bars": bars_fingerprint(read_bars(history)[0])}


@contextmanager
def reregistered(claim_id, field, name, value):
    """Move one registered value for the duration of a reading, then put it back.

    Tests that couple a measurement to the registry have to move the registry, not the function
    that reads it: a patched-out lookup passes just as happily against a value hardcoded in the
    module under test.
    """
    from scripts.minervini import doctrine

    record = next(claim for claim in doctrine._load_registry()["claims"] if claim["id"] == claim_id)
    slot = record[field][name]
    before = slot["value"]
    slot["value"] = value
    try:
        yield
    finally:
        slot["value"] = before


@contextmanager
def restated(claim_id, field, value):
    """Replace one whole field of a registered claim for the duration of a reading.

    `reregistered` moves a number inside a thresholds or parameters table. This moves what the
    claim *says* -- its rule, what its failure means, what its absence means -- which is the half
    a digest of numbers alone cannot see change.
    """
    from scripts.minervini import doctrine

    record = next(claim for claim in doctrine._load_registry()["claims"] if claim["id"] == claim_id)
    before = record[field]
    record[field] = value
    try:
        yield
    finally:
        record[field] = before
