"""The readings a fully-read setup carries, in one place.

Six required conditions, three of them readings a person supplies and one of those only an
independent segmentation can. Spreading that bundle across every test meant each new reading
broke every file at once; collecting it here means a test names only the reading it is about.
"""

from __future__ import annotations

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
