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
from datetime import date, timedelta


# The 52 is the sources' own word -- "52-week high", "the 52-week-low list". Seven days a
# week is the calendar's, and not a convention this harness could have registered otherwise:
# 52 weeks is 364 days, one short of a year, and that is the duration the phrase names.
DAYS_IN_THE_YEAR_THE_SOURCES_NAME = 52 * 7


def year_window_start(dates: Sequence[date], end: int) -> int | None:
    """Index where the trailing 52 weeks ending at ``end`` opens, or nothing.

    Nothing, rather than what there is. A window shorter than the one being named does not
    make its extremes approximate; it makes them wrong in a fixed direction -- a truncated
    window has a higher low and a lower high, so every reading taken from it understates the
    distance to the year's high and overstates the rise from its low.

    The window is full when a bar sits at or before the earliest date it admits. Without one
    the history simply starts partway into the year it is being asked about.
    """

    if end < 0 or end >= len(dates):
        return None
    boundary = dates[end] - timedelta(days=DAYS_IN_THE_YEAR_THE_SOURCES_NAME)
    if dates[0] > boundary:
        return None
    # Dates are ordered oldest to newest by every caller's own reading, so the first bar
    # inside the boundary is where the window opens.
    for index in range(end + 1):
        if dates[index] >= boundary:
            return index
    return None
