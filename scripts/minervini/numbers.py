"""Shared numeric readings; coercion and positivity remain separate contracts."""

from __future__ import annotations

import math
from typing import Any, Mapping

# Enough places to strip binary-float noise from a reported figure and far too many
# to soften any limit the registry states.
REPORTED_PRECISION = 10


def finite(value: Any) -> bool:
    """A number a comparison can be made against, which `inf` and `nan` are not.

    This is the layer that checks what the collector handed over, and it let an infinite
    three-month return through to be ranked first and then to break the envelope's own
    serialisation. A quantity that is not finite was not measured.
    """

    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        # An int too large to become a float. It is not finite in any sense this comparison
        # needs, and raising here would trade a wrong number for no envelope at all.
        return False


def finite_or_none(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def positive(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value > 0 and math.isfinite(value):
        return float(value)
    return None


def reported(value: float | None) -> float | None:
    """Round for the reader only; every comparison ran on the measurement itself.

    A figure that is not finite is not a measurement, whatever arithmetic produced it, and
    an infinity on the page is worse than the absence it stands for: it reads as a quantity.
    """

    if value is None or not math.isfinite(value):
        return None
    return round(value, REPORTED_PRECISION)


def reported_deep(value: Any) -> Any:
    """Round for the reader only; every comparison above ran on the measurement itself."""

    if isinstance(value, float):
        return round(value, REPORTED_PRECISION)
    if isinstance(value, list):
        return [reported_deep(item) for item in value]
    if isinstance(value, Mapping):
        return {key: reported_deep(item) for key, item in value.items()}
    return value
