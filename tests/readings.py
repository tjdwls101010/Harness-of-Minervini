"""The readings a fully-read setup carries, in one place.

Six required conditions, three of them readings a person supplies and one of those only an
independent segmentation can. Spreading that bundle across every test meant each new reading
broke every file at once; collecting it here means a test names only the reading it is about.
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd


def full(frame: pd.DataFrame, chain: Sequence[str], **overrides):
    """Every reading satisfied, with an entry at the pivot and a chain the detector agrees with."""

    pivot = float(frame.loc[chain[-1], "High"]) if len(chain) else None
    readings = {
        "right_side_development": "constructive",
        "chain_completeness": "complete",
        "detected_chain": list(chain),
        "entry_proximity": "at_pivot",
        "entry_price": pivot * 1.001 if pivot else None,
    }
    readings.update(overrides)
    return readings
