"""What "52-week" names, in one place, for every reader of it.

Two modules measure a trailing year and they disagreed. The eligibility stack bounds the
window by date; the market's leader reading counted `52 x convention.trading_week(5) = 260`
sessions. A bar count is the same span only for a name that traded every session, and no
name does: a real US year holds about 252 sessions, so 260 asks for thirteen months, while
a name whose sessions were thinned by a halt reaches 260 bars over years and publishes an
extreme from long before the year in question.

Wrong in both directions, and quietly -- the reader cannot tell a 3% measured over a year
from a 3% measured over a fortnight, and neither number carries how long it took.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta
from typing import Any


# Seven days a week is the calendar's, and not a convention this harness could have
# registered otherwise. `convention.trading_week` registers the other conversion -- five
# sessions -- and the two are not interchangeable: a week of a stock's own bars is what
# bounds a flag or a base, and a week of days is what separates two dates.
DAYS_IN_A_WEEK = 7
# The 52 is the sources' own word -- "52-week high", "the 52-week-low list". 52 weeks is
# 364 days, one short of a year, and that is the duration the phrase names.
DAYS_IN_THE_YEAR_THE_SOURCES_NAME = 52 * DAYS_IN_A_WEEK


def year_window_start(moments: Sequence[Any], end: int) -> int | None:
    """Index where the trailing 52 weeks ending at ``end`` opens, or nothing.

    Nothing, rather than what there is. A window shorter than the one being named does not
    make its extremes approximate; it makes them wrong in a fixed direction -- a truncated
    window has a higher low and a lower high, so every reading taken from it understates the
    distance to the year's high and overstates the rise from its low.

    The window is full when a bar sits at or before the earliest moment it admits. Without
    one the history simply starts partway into the year it is being asked about.

    Whatever the caller keeps its sessions as -- calendar dates, or timestamps carrying a
    time and a zone -- is what the span is measured in. Rounding a timestamp down to its date
    first would make two stamps 363 days and 17 hours apart read as a full year, and 52 weeks
    is a duration rather than a pair of dates.

    Ordered oldest to newest is the caller's guarantee; out of order, this returns nothing
    rather than a boundary that means nothing.
    """

    if end < 0 or end >= len(moments):
        return None
    if any(moments[index] > moments[index + 1] for index in range(end)):
        return None
    boundary = moments[end] - timedelta(days=DAYS_IN_THE_YEAR_THE_SOURCES_NAME)
    if moments[0] > boundary:
        return None
    for index in range(end + 1):
        if moments[index] >= boundary:
            return index
    return None


def session_at_or_before(moments: Sequence[Any], target: Any) -> int | None:
    """Index of the latest moment at or before ``target``, or nothing.

    What a name answers with when it is asked about a date. Several names read at one date
    is the only way their counts add up to anything: a window stated in weeks addresses a
    moment they share, and stepping each of them back a fixed number of its own bars walks
    them to different moments -- 28 days for a name that trades every session, 60 for one
    whose sessions were thinned.

    At or before, because a completed-bar harness cannot read a session that had not closed.
    A date the history does not reach is nothing rather than its earliest bar, for the same
    reason the year window refuses a short history: the reading would be taken somewhere
    other than where it says it was.

    Ordered oldest to newest is the caller's guarantee; out of order, this returns nothing.
    """

    if not moments:
        return None
    if any(moments[index] > moments[index + 1] for index in range(len(moments) - 1)):
        return None
    if moments[0] > target:
        return None
    for index in range(len(moments) - 1, -1, -1):
        if moments[index] <= target:
            return index
    return None
