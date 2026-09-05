"""Power Play series and their deliberately difficult variants."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .base import _leg


def power_play_series(
    *,
    dormant_price: float = 10.0,
    advance_pct: float = 110.0,
    advance_sessions: int = 25,
    dormancy_sessions: int = 60,
    flag_sessions: int = 20,
    flag_depth_pct: float = 12.0,
    advance_volume_multiple: float = 6.0,
    spike_above_peak_pct: float | None = None,
    tie_the_peak_at: int | None = None,
    ancient_equal_high: bool = False,
    split_inside_the_flag: bool = False,
    split_at: int | None = None,
    distribution_in_the_flag: float | None = None,
    distribution_after_the_flag_low: float | None = None,
    payout_that_reorders_the_tops: bool = False,
    later_high: float | None = None,
    volume_spike_before_the_launch: float | None = None,
    corporate_actions: bool = True,
    marginal_new_high_at: int | Sequence[int] | None = None,
    start: str = "2026-01-02",
) -> pd.DataFrame:
    """Dormancy, then an explosive advance, then a flag that ends on the last bar.

    Built so the numbers a Power Play test asserts are the numbers the builder was given: the
    peak bar's high is exactly the peak, the last dormant bar's low is exactly the launch price,
    and the flag's low bar is exactly the depth asked for. Everything else carries a wick
    narrower than the smallest leg step, so no neighbour's range can reach a pinned extreme.

    The flag runs to the end of the frame because that is the only shape the question is asked
    in: a Power Play is read forward from a peak toward the session being traded, and a flag
    with bars after it is a different structure that already resolved.
    """

    peak = dormant_price * (1 + advance_pct / 100)
    flag_low = peak * (1 - flag_depth_pct / 100)
    # Dormancy sits just above the launch price and its last bar undercuts it once. A flat floor
    # would tie every dormant session for the lowest low, and which one a tie resolves to is not
    # something a fixture should be teaching a measurement.
    closes = [dormant_price * 1.01] * dormancy_sessions
    launch = len(closes) - 1
    closes += _leg(dormant_price * 1.01, peak, advance_sessions)
    apex = len(closes) - 1
    # Down to the flag's low and back toward the peak without reaching it, so the peak stays the
    # last session that printed the maximum high.
    sink = max(1, flag_sessions // 2)
    closes += _leg(peak, flag_low, sink)
    trough = len(closes) - 1
    closes += _leg(flag_low, peak * 0.98, flag_sessions - sink)

    steps = [abs(later - earlier) for earlier, later in zip(closes, closes[1:])]
    wick = 0.15 * min(step for step in steps if step > 0)
    index = pd.bdate_range(start=start, periods=len(closes))
    frame = pd.DataFrame({"Open": closes, "Close": closes}, index=index)
    frame["High"] = frame["Close"] + wick
    frame["Low"] = frame["Close"] - wick
    frame.iloc[launch, frame.columns.get_loc("Low")] = dormant_price
    for position, column in ((apex, "High"), (trough, "Low")):
        frame.iloc[position, frame.columns.get_loc(column)] = closes[position]
    if ancient_equal_high:
        # One session at the very start of the loaded history that printed exactly the same high
        # this structure later reached, with an unrelated decline between them. Nothing connects
        # the two but the price being equal.
        frame.iloc[1, frame.columns.get_loc("High")] = peak
    if marginal_new_high_at is not None:
        # A hundredth of a percent above the peak, late in an otherwise ordinary flag. Nothing in
        # the source says how large a new high has to be before it means something, so the search
        # takes it and the flag before it becomes advance.
        #
        # Several of them, given a sequence: each ticks above the last, so a reading that steps
        # down one top at a time walks through the ticks and never reaches the structure. Each is
        # a hundredth of a percent above its predecessor, in the order given.
        positions = (
            [marginal_new_high_at]
            if isinstance(marginal_new_high_at, int)
            else list(marginal_new_high_at)
        )
        for step, position in enumerate(positions, start=1):
            frame.iloc[position, frame.columns.get_loc("High")] = peak * (1 + 0.0001 * step)
    if tie_the_peak_at is not None:
        # A later session that prints exactly the peak's high without exceeding it. Nothing
        # explosive happened there, so a rule that reads the flag from the last equal high
        # re-labels everything before it as advance.
        frame.iloc[tie_the_peak_at, frame.columns.get_loc("High")] = peak
    if spike_above_peak_pct is not None:
        # One session inside the advance that traded above the peak the flag hangs from. The
        # flag then sits under a high the structure already made, which is the shape a search
        # anchored at the last bar cannot see from the flag alone.
        position = launch + max(1, advance_sessions // 2)
        frame.iloc[position, frame.columns.get_loc("High")] = peak * (1 + spike_above_peak_pct / 100)
    # Dormancy is quiet, the advance "commences on huge volume", and the flag settles between
    # the two -- the volume shape the criterion describes rather than a flat series.
    volumes = (
        [400_000.0] * dormancy_sessions
        + [400_000.0 * advance_volume_multiple] * advance_sessions
        + [800_000.0] * flag_sessions
    )
    frame["Volume"] = volumes[: len(closes)]
    if volume_spike_before_the_launch is not None:
        # One heavy session a week ahead of the anchor. It is dormancy, not advance: a numerator
        # that reaches back past the anchor reports it as the expansion the move commenced on.
        frame.iloc[launch - 5, frame.columns.get_loc("Volume")] = (
            400_000.0 * volume_spike_before_the_launch
        )
    if not corporate_actions:
        # A history that cannot say whether a split happened. The provider supplies the column,
        # so this is the shape of an input from somewhere that does not.
        return frame[["Open", "High", "Low", "Close", "Volume"]]
    frame["Stock Splits"] = [0.0] * len(closes)
    if "Dividends" not in frame:
        frame["Dividends"] = [0.0] * len(closes)
    if later_high is not None:
        # One session late in the flag printing a caller-chosen high. Just inside the candidate
        # distance it is another reading of the same structure; a cent outside it, the structure
        # below leaves the chain entirely.
        frame.iloc[apex + 15, frame.columns.get_loc("High")] = later_high
    if payout_that_reorders_the_tops:
        # An earlier session two percent under the top, and a payout of three percent taken out of
        # every print from the top onward. On the tape the earlier session now prints the higher
        # high, so which bar the flag hangs from was decided by the dividend rather than by the
        # stock -- and the real top, being later, is never reached by a chain that walks backward.
        frame["Dividends"] = [0.0] * len(closes)
        payout = peak * 0.03
        frame.iloc[apex - 6, frame.columns.get_loc("High")] = peak * 0.98
        frame.iloc[apex, frame.columns.get_loc("Dividends")] = payout
        columns = [frame.columns.get_loc(name) for name in ("Open", "High", "Low", "Close")]
        frame.iloc[apex:, columns] -= payout
    if distribution_after_the_flag_low is not None:
        # Paid once the flag had already bottomed. It takes the later prints down without having
        # taken the low down, so the decline the criterion reads is the stock's own.
        frame["Dividends"] = [0.0] * len(closes)
        frame.iloc[trough + 2, frame.columns.get_loc("Dividends")] = distribution_after_the_flag_low
        paid = [frame.columns.get_loc(name) for name in ("Open", "High", "Low", "Close")]
        frame.iloc[trough + 2:, paid] -= distribution_after_the_flag_low
    if distribution_in_the_flag is not None:
        # A cash distribution paid partway through the flag, and taken out of every print from its
        # ex-date onward the way the tape takes it. The decline the flag measures is then partly
        # the payout -- and unlike a split the amount is known, which is what lets the reading say
        # whether it changed the answer.
        frame["Dividends"] = [0.0] * len(closes)
        frame.iloc[trough, frame.columns.get_loc("Dividends")] = distribution_in_the_flag
        paid = [frame.columns.get_loc(name) for name in ("Open", "High", "Low", "Close")]
        frame.iloc[trough:, paid] -= distribution_in_the_flag
    if split_at is not None:
        # A two-for-one forward split at a caller-chosen session, printed the way a raw feed
        # prints one: everything *before* it carries the pre-split price and share count, so the
        # sessions after it are untouched and the structure downstream still reads. The caller
        # picks the index because where the split falls relative to a measurement's span is the
        # whole question -- a volume baseline that begins earlier than the span checked for
        # actions takes its median from two different share counts and says nothing about it.
        frame.iloc[split_at, frame.columns.get_loc("Stock Splits")] = 2.0
        earlier = [frame.columns.get_loc(name) for name in ("Open", "High", "Low", "Close")]
        frame.iloc[:split_at, earlier] *= 2
        frame.iloc[:split_at, frame.columns.get_loc("Volume")] /= 2
    if split_inside_the_flag:
        # A two-for-one forward split partway through the flag: every printed price halves, so
        # the flag reads as a fifty percent correction that never happened.
        cut = trough + 1
        frame.iloc[cut, frame.columns.get_loc("Stock Splits")] = 2.0
        columns = ["Open", "High", "Low", "Close"]
        frame.iloc[cut:, [frame.columns.get_loc(name) for name in columns]] /= 2
    return frame[["Open", "High", "Low", "Close", "Volume", "Stock Splits", "Dividends"]]


def reverse_split_series(*, factor: float = 2.0, start: str = "2026-01-02") -> pd.DataFrame:
    """A flat stock through a 1-for-`factor` reverse split, carrying the split event.

    Nothing happens to the company or to anyone's money. The raw tape doubles overnight and
    then goes sideways, which is the shape of every number the first Power Play criterion
    reads: a hundred percent advance, inside a week, followed by a tight flag. The adjusted
    column is what says the advance was zero -- it back-scales the pre-split sessions by the
    same factor, so the two readings of the same move disagree by exactly the split.
    """

    before = [5.0] * 40
    after = [5.0 * factor] * 30
    closes = before + after
    index = pd.bdate_range(start=start, periods=len(closes))
    frame = pd.DataFrame({"Open": closes, "Close": closes}, index=index)
    frame["High"] = frame["Close"] * 1.004
    frame["Low"] = frame["Close"] * 0.996
    frame["Volume"] = [1_000_000.0] * len(closes)
    # One shakeout inside the flat stretch, so the advance has a single lowest session to start
    # from rather than forty tied ones.
    frame.iloc[len(before) - 5, frame.columns.get_loc("Low")] = 4.9
    # The event column the provider fills: zero on every ordinary session, the ratio on the day
    # it happened. A one-for-two reverse split is 0.5.
    frame["Stock Splits"] = [0.0] * len(closes)
    if "Dividends" not in frame:
        frame["Dividends"] = [0.0] * len(closes)
    frame.iloc[len(before), frame.columns.get_loc("Stock Splits")] = 1 / factor
    return frame[["Open", "High", "Low", "Close", "Volume", "Stock Splits", "Dividends"]]


def wide_launch_bar_series(*, start: str = "2026-01-02") -> pd.DataFrame:
    """A Power Play whose first advancing session is itself a very wide bar.

    The move begins where the source says it begins -- on huge volume, out of dormancy at 90 --
    and the launch session travels from 80 to 160 before closing at 150. Reading the advance
    from that session's close throws the whole first day away and reports thirty-three percent
    on a stock that went from 90 to 200 in two weeks.
    """

    # Long enough that the advance window has a full baseline in front of it; a partial one is
    # reported as no baseline at all.
    dormant = [90.0] * 90
    closes = dormant + [150.0] + _leg(150.0, 200.0, 9)
    index = pd.bdate_range(start=start, periods=len(closes) + 12)
    closes = closes + [198.0] * 12
    frame = pd.DataFrame({"Open": closes, "Close": closes}, index=index)
    frame["High"] = frame["Close"] * 1.002
    frame["Low"] = frame["Close"] * 0.998
    launch = len(dormant)
    frame.iloc[launch, frame.columns.get_loc("Open")] = 90.0
    frame.iloc[launch, frame.columns.get_loc("Low")] = 80.0
    frame.iloc[launch, frame.columns.get_loc("High")] = 160.0
    peak = launch + 9
    frame.iloc[peak, frame.columns.get_loc("High")] = 200.0
    frame["Volume"] = [1_000_000.0] * len(closes)
    frame.iloc[launch, frame.columns.get_loc("Volume")] = 10_000_000.0
    return frame[["Open", "High", "Low", "Close", "Volume"]]


def dormancy_low_before_the_launch_series(*, start: str = "2026-01-02") -> pd.DataFrame:
    """The lowest session of the eight weeks is not the session the move began on.

    A quiet undercut to 89 five weeks before the peak, then more dormancy around 90, then the
    real move: ten times the usual volume, ninety to two hundred in nine sessions. Read the
    volume clause off the lowest bar and this stock reports no expansion at all, because the
    lowest bar was a quiet one.
    """

    quiet = [90.0] * 90 + [90.0] * 20
    undercut = 45
    closes = quiet + _leg(90.0, 200.0, 9)
    peak = len(closes) - 1
    launch = len(quiet)
    closes = closes + [196.0] * 20
    index = pd.bdate_range(start=start, periods=len(closes))
    frame = pd.DataFrame({"Open": closes, "Close": closes}, index=index)
    frame["High"] = frame["Close"] * 1.002
    frame["Low"] = frame["Close"] * 0.998
    frame.iloc[undercut, frame.columns.get_loc("Low")] = 89.0
    frame.iloc[peak, frame.columns.get_loc("High")] = 200.0
    frame["Volume"] = [1_000_000.0] * len(closes)
    for position in range(launch, peak + 1):
        frame.iloc[position, frame.columns.get_loc("Volume")] = 10_000_000.0
    return frame[["Open", "High", "Low", "Close", "Volume"]]


def wick_after_the_launch_series(*, start: str = "2026-01-02") -> pd.DataFrame:
    """The lowest low of the eight weeks prints days after the move already began.

    Fifty for forty sessions, then the launch: ten times the volume, fifty to seventy-five in one
    session, and on to a hundred and ten. Three days later one bar wicks to forty-nine and never
    closes there. Anchoring the advance on the lowest low starts the reading after the launch --
    the price move measures from seventy-five instead of fifty, and the ten-times session falls
    outside the window the volume is looked for in.
    """

    closes = [50.0] * 90 + [75.0, 76.0, 80.0, 84.0, 88.0, 92.0, 97.0, 102.0, 106.0, 110.0]
    peak = len(closes) - 1
    closes = closes + [106.0] * 21
    index = pd.bdate_range(start=start, periods=len(closes))
    frame = pd.DataFrame({"Open": closes, "Close": closes}, index=index)
    frame["High"] = frame["Close"] * 1.002
    frame["Low"] = frame["Close"] * 0.998
    launch = 90
    frame.iloc[launch, frame.columns.get_loc("Low")] = 50.0
    frame.iloc[launch, frame.columns.get_loc("High")] = 80.0
    frame.iloc[launch + 1, frame.columns.get_loc("Low")] = 49.0
    frame.iloc[peak, frame.columns.get_loc("High")] = 110.0
    frame["Volume"] = [1_000_000.0] * len(closes)
    frame.iloc[launch, frame.columns.get_loc("Volume")] = 10_000_000.0
    frame["Stock Splits"] = [0.0] * len(closes)
    if "Dividends" not in frame:
        frame["Dividends"] = [0.0] * len(closes)
    return frame[["Open", "High", "Low", "Close", "Volume", "Stock Splits", "Dividends"]]


def stale_volume_regime_series(*, start: str = "2026-01-02") -> pd.DataFrame:
    """A quiet stretch immediately before the move, and a busier regime well behind it.

    Forty sessions at ten million, then thirty-one at one million, then a ten-session thrust at
    five million that carries fifty to a hundred and ten, then a flag. Against the volume the
    stock actually traded before the move began, the thrust is five times. Against a fixed window
    forty to eighty sessions ahead of the peak, it is half -- a launch that plainly expanded,
    removed as a known failure by a regime the stock left months earlier.
    """

    closes = [50.0] * 71 + _leg(50.0, 110.0, 10)
    peak = len(closes) - 1
    closes = closes + [106.0] * 20
    index = pd.bdate_range(start=start, periods=len(closes))
    frame = pd.DataFrame({"Open": closes, "Close": closes}, index=index)
    frame["High"] = frame["Close"] * 1.002
    frame["Low"] = frame["Close"] * 0.998
    frame.iloc[peak, frame.columns.get_loc("High")] = 110.0
    frame["Volume"] = (
        [10_000_000.0] * 40 + [1_000_000.0] * 31 + [5_000_000.0] * 10 + [1_000_000.0] * 20
    )
    frame["Stock Splits"] = [0.0] * len(closes)
    if "Dividends" not in frame:
        frame["Dividends"] = [0.0] * len(closes)
    return frame[["Open", "High", "Low", "Close", "Volume", "Stock Splits", "Dividends"]]


def anchor_moving_payout_series(*, start: str = "2026-01-02") -> pd.DataFrame:
    """A distribution that leaves the peak where it is and takes the anchor somewhere else.

    Fifty for sixty sessions, a run-up to sixty, then a ten-dollar payout and twenty sessions at
    what prints as forty-five, then the peak at a hundred and a flag. On the tape the lowest close
    of the eight weeks before the peak is the forty-five stretch; on one scale it is the fifty
    stretch, seven weeks earlier. Same peak, different advance, different baseline.
    """

    index = pd.bdate_range(start=start, periods=121)
    closes = [50.0] * 60 + [60.0] * 10 + [55.0] * 20 + [100.0] + [92.0] * 30
    frame = pd.DataFrame({"Open": closes, "Close": closes}, index=index)
    frame["High"] = frame["Close"] * 1.002
    frame["Low"] = frame["Close"] * 0.998
    frame.iloc[90, frame.columns.get_loc("High")] = 100.0
    frame["Volume"] = [400_000.0] * 90 + [2_400_000.0] + [800_000.0] * 30
    frame["Stock Splits"] = [0.0] * len(closes)
    if "Dividends" not in frame:
        frame["Dividends"] = [0.0] * len(closes)
    frame["Dividends"] = [0.0] * len(closes)
    frame.iloc[70, frame.columns.get_loc("Dividends")] = 10.0
    paid = [frame.columns.get_loc(name) for name in ("Open", "High", "Low", "Close")]
    frame.iloc[70:, paid] -= 10.0
    return frame[["Open", "High", "Low", "Close", "Volume", "Stock Splits", "Dividends"]]


def payout_that_only_moves_a_gate_series(
    *, payout: float = 0.30, start: str = "2026-01-02"
) -> pd.DataFrame:
    """Same structure on either scale, and the advance lands on opposite sides of the limit.

    Every boundary matches: same peak, same anchor, same flag low, same baseline, same tops in
    the same order. What differs is the number the gate is read against, because the payout came
    out of the prints between the anchor and the peak -- ninety-nine percent on the tape, a
    hundred and a half once every print is on one scale.

    Built so that nothing else can account for the withholding. The advance tops out twelve
    percent below the peak and reaches it in one session, so no candidate top other than the
    flag's own bars comes within the registered contesting distance, and those agree on every
    criterion. Read on the default fixture instead, the payout and the candidate tops fire
    together and the test cannot tell which one withheld the gate.
    """

    dormant, ramp_top, peak, flag = 50.0, 88.0, 99.9, 94.0
    closes = (
        [dormant] * 60
        + [dormant + (ramp_top - dormant) * (step + 1) / 25 for step in range(25)]
        + [peak]
        + [flag] * 30
    )
    index = pd.bdate_range(start=start, periods=len(closes))
    frame = pd.DataFrame({"Open": closes, "Close": closes}, index=index)
    frame["High"] = frame["Close"] * 1.001
    frame["Low"] = frame["Close"] * 0.999
    frame["Volume"] = [400_000.0] * 60 + [2_400_000.0] * 26 + [800_000.0] * 30
    frame["Stock Splits"] = [0.0] * len(closes)
    frame["Dividends"] = [0.0] * len(closes)
    frame.iloc[70, frame.columns.get_loc("Dividends")] = payout
    paid = [frame.columns.get_loc(name) for name in ("Open", "High", "Low", "Close")]
    frame.iloc[70:, paid] -= payout
    return frame[["Open", "High", "Low", "Close", "Volume", "Stock Splits", "Dividends"]]


def a_payout_decided_criterion_under_a_lower_top_series(
    *, payout: float = 0.30, start: str = "2026-01-02"
) -> pd.DataFrame:
    """The gate the payout decided, with a genuine earlier top that rejects on that same gate.

    Built as the gate fixture with a pullback inside the advance, so the search has a second
    turning point to land on. Read from that top the advance is only eighty-odd percent and fails
    outright; read from the peak it lands either side of the limit depending on which scale the
    prints are on. The chain is therefore loud with a rejection on a criterion that has no
    trustworthy answer, which is exactly the combination a verdict must not resolve by counting
    votes.
    """

    dormant, mid, dip, peak, flag = 50.0, 95.0, 90.0, 99.9, 94.0
    closes = (
        [dormant] * 60
        + [dormant + (mid - dormant) * (step + 1) / 18 for step in range(18)]
        + [mid - (mid - dip) * (step + 1) / 4 for step in range(4)]
        + [dip + (peak - dip) * (step + 1) / 4 for step in range(4)]
        + [flag] * 30
    )
    index = pd.bdate_range(start=start, periods=len(closes))
    frame = pd.DataFrame({"Open": closes, "Close": closes}, index=index)
    frame["High"] = frame["Close"] * 1.001
    frame["Low"] = frame["Close"] * 0.999
    frame["Volume"] = [400_000.0] * 60 + [2_400_000.0] * 26 + [800_000.0] * 30
    frame["Stock Splits"] = [0.0] * len(closes)
    frame["Dividends"] = [0.0] * len(closes)
    frame.iloc[70, frame.columns.get_loc("Dividends")] = payout
    paid = [frame.columns.get_loc(name) for name in ("Open", "High", "Low", "Close")]
    frame.iloc[70:, paid] -= payout
    return frame[["Open", "High", "Low", "Close", "Volume", "Stock Splits", "Dividends"]]


def two_tops_that_both_await_the_chart_series(
    *, flag_low: float = 100.0, start: str = "2026-01-02"
) -> pd.DataFrame:
    """Two candidate tops that agree on every measurable criterion and both ask about volume.

    A pullback inside the advance leaves a confirmed turning point a few percent under the peak,
    close enough to contest it. Every deterministic gate reads the same from both, so the only
    thing separating them is the question the bars decline to answer -- which is what makes this
    the fixture for what a reading of one top's chart does to the other's.
    """

    dormant, mid, dip, peak, flag_end = 50.0, 103.0, 96.0, 108.0, 105.0
    closes = (
        [dormant] * 60
        + [dormant + (mid - dormant) * (step + 1) / 16 for step in range(16)]
        + [mid - (mid - dip) * (step + 1) / 4 for step in range(4)]
        + [dip + (peak - dip) * (step + 1) / 4 for step in range(4)]
        + [peak - (peak - flag_low) * (step + 1) / 10 for step in range(10)]
        + [flag_low + (flag_end - flag_low) * (step + 1) / 10 for step in range(10)]
    )
    index = pd.bdate_range(start=start, periods=len(closes))
    frame = pd.DataFrame({"Open": closes, "Close": closes}, index=index)
    frame["High"] = frame["Close"] * 1.001
    frame["Low"] = frame["Close"] * 0.999
    frame["Volume"] = [400_000.0] * 60 + [2_400_000.0] * 24 + [800_000.0] * 20
    frame["Stock Splits"] = [0.0] * len(closes)
    frame["Dividends"] = [0.0] * len(closes)
    return frame[["Open", "High", "Low", "Close", "Volume", "Stock Splits", "Dividends"]]


def a_top_the_history_ends_before_series(
    *,
    flag_depth_pct: float = 12.0,
    unread_top_price: float = 20.1,
    advance_pct: float = 110.0,
    start: str = "2026-01-02",
) -> pd.DataFrame:
    """A clean structure whose next candidate top sits behind the first loaded bar.

    The frame opens on a confirmed high under the peak and there is no history behind it to
    measure a structure from, so the walk stops there rather than reading it. Whether the reading
    it never made would have had a vote is what ``unread_top_price`` sets: the default stands a
    few percent under the peak, inside the distance a top may contest from, and a lower value puts
    it far enough below to be a structure the stock has since overtaken.

    ``advance_pct`` moves the peak, which is only ever worth doing to land the pair of prices on a
    distance the float grid can represent exactly: at the default peak of 21.0 no price stands
    exactly ten percent below it, and a boundary that cannot be reached cannot be tested.
    """

    frame = power_play_series(
        dormancy_sessions=41,
        advance_sessions=1,
        flag_sessions=12,
        flag_depth_pct=flag_depth_pct,
        advance_pct=advance_pct,
        start=start,
    )
    columns = frame.columns.get_indexer(["Open", "High", "Low", "Close"])
    frame.iloc[0, columns] = [
        unread_top_price * 0.995,
        unread_top_price,
        unread_top_price * 0.99,
        unread_top_price * 0.995,
    ]
    return frame


def a_top_only_a_neighbour_confirms_series(*, dip_pct: float = 0.30, flag_sessions: int = 26, start: str = "2026-01-02") -> pd.DataFrame:
    """A candidate top the middle retracement misses and a neighbouring one confirms.

    The pullback inside the advance is sized to land between the retracements the segmentation
    convention's own sensitivity offsets produce: deep enough for the looser neighbour to confirm
    a turning point there, shallow enough for the middle reading to walk past it. Read from that
    top the flag runs past six weeks and the structure is out; read from the peak above it,
    nothing measurable fails.

    Which is the whole of the case. One reading of the same chart says this is not a Power Play,
    and a verdict taken off the middle reading alone never hears it.
    """

    dormant, lower_top, peak, flag_low, flag_end = 50.0, 103.0, 108.0, 100.0, 105.0
    sink = flag_sessions // 2
    closes = [dormant] * 60
    closes += [dormant + (lower_top - dormant) * (step + 1) / 16 for step in range(16)]
    closes += [lower_top * (1 - dip_pct / 100)]
    closes += [lower_top + (peak - lower_top) * (step + 1) / 4 for step in range(4)]
    closes += [peak - (peak - flag_low) * (step + 1) / sink for step in range(sink)]
    closes += [
        flag_low + (flag_end - flag_low) * (step + 1) / (flag_sessions - sink)
        for step in range(flag_sessions - sink)
    ]
    index = pd.bdate_range(start=start, periods=len(closes))
    frame = pd.DataFrame({"Open": closes, "Close": closes}, index=index)
    frame["High"] = frame["Close"] * 1.001
    frame["Low"] = frame["Close"] * 0.999
    frame["Volume"] = [400_000.0] * 60 + [2_400_000.0] * 21 + [800_000.0] * flag_sessions
    frame["Stock Splits"] = [0.0] * len(closes)
    frame["Dividends"] = [0.0] * len(closes)
    return frame[["Open", "High", "Low", "Close", "Volume", "Stock Splits", "Dividends"]]


def a_top_hidden_by_an_ambiguous_session_series(*, flag_sessions: int = 26, start: str = "2026-01-02") -> pd.DataFrame:
    """A top the segmenter had to choose against, because one bar reads two ways.

    The session after the lower top both prints a new high and retraces far enough to end the
    swing, and a daily bar does not say which happened first. The segmenter records the ambiguity
    and resolves it one way, which leaves no anchor at the top before it. Under the other order
    that top is confirmed -- and read from there the flag runs past six weeks and the structure is
    out.

    Same geometry as the neighbour-only fixture beside it, with the shallow pullback replaced by
    the ambiguous bar, so the two differ only in *why* the top goes missing.
    """

    dormant, lower_top, peak, flag_low, flag_end = 50.0, 103.0, 108.0, 100.0, 105.0
    ambiguous_low = 102.30
    sink = flag_sessions // 2
    closes = [dormant] * 60
    closes += [dormant + (lower_top - dormant) * (step + 1) / 16 for step in range(16)]
    closes += [ambiguous_low]
    closes += [lower_top + (peak - lower_top) * (step + 1) / 4 for step in range(4)]
    closes += [peak - (peak - flag_low) * (step + 1) / sink for step in range(sink)]
    closes += [
        flag_low + (flag_end - flag_low) * (step + 1) / (flag_sessions - sink)
        for step in range(flag_sessions - sink)
    ]
    index = pd.bdate_range(start=start, periods=len(closes))
    frame = pd.DataFrame({"Open": closes, "Close": closes}, index=index)
    frame["High"] = frame["Close"] * 1.001
    frame["Low"] = frame["Close"] * 0.999
    frame.iloc[76, frame.columns.get_loc("High")] = 103.30
    frame.iloc[76, frame.columns.get_loc("Low")] = ambiguous_low * 0.999
    frame["Volume"] = [400_000.0] * 60 + [2_400_000.0] * 21 + [800_000.0] * flag_sessions
    frame["Stock Splits"] = [0.0] * len(closes)
    frame["Dividends"] = [0.0] * len(closes)
    return frame[["Open", "High", "Low", "Close", "Volume", "Stock Splits", "Dividends"]]


def a_range_too_wide_to_segment_series(*, start: str = "2026-01-02") -> pd.DataFrame:
    """Bars whose ordinary session spans so much of its own close that the upper neighbour
    retracement leaves the segmenter's domain.

    Valid OHLCV throughout. The middle reading still runs; the neighbour the convention also
    registers does not, and running only the ones that happen to fit is reading a measurement
    nobody could take.
    """

    closes = [100.0 + (step % 7) for step in range(90)]
    index = pd.bdate_range(start=start, periods=len(closes))
    frame = pd.DataFrame({"Open": closes, "Close": closes}, index=index)
    frame["High"] = [close * 1.2 for close in closes]
    frame["Low"] = [close * 0.81 for close in closes]
    frame["Volume"] = [1_000_000.0] * len(closes)
    frame["Stock Splits"] = [0.0] * len(closes)
    frame["Dividends"] = [0.0] * len(closes)
    return frame[["Open", "High", "Low", "Close", "Volume", "Stock Splits", "Dividends"]]


def a_flag_tighter_than_one_days_range_series(*, start: str = "2026-01-02") -> pd.DataFrame:
    """A structure whose flag corrects less than an ordinary session spans.

    Nothing here is malformed: the advance is real, the flag is the tightest one this exception
    describes, and every criterion the bars can settle is satisfied. What the segmentation cannot
    do is confirm the peak as a turning point, because no retracement it registers is smaller than
    a single day's range on these bars -- so the structure hangs from a high the harness has not
    identified as a top.
    """

    frame = power_play_series(flag_depth_pct=0.1, start=start)
    frame["High"] = frame["Close"] * 1.02
    frame["Low"] = frame["Close"] * 0.98
    return frame


def two_orders_that_confirm_different_tops_series(*, start: str = "2026-05-19") -> pd.DataFrame:
    """One session that both extends the leg and ends it, followed by enough bars for the two
    readings to diverge.

    Whichever way the segmenter resolves that bar, it goes on running under that resolution and
    confirms turns the other one never reaches. Here each order confirms a high the other does
    not, which is the whole reason the candidate set has to come from running the segmenter twice
    rather than from patching the two bars either side of the ambiguity.
    """

    rows = [
        (100.0, 99.0, 99.5),
        (100.0, 99.5, 99.8),
        (106.0, 95.0, 100.0),
        (105.0, 100.0, 104.0),
        (104.5, 104.0, 104.2),
        (112.0, 104.0, 111.0),
    ]
    index = pd.bdate_range(start=start, periods=len(rows))
    frame = pd.DataFrame(
        {"High": [row[0] for row in rows], "Low": [row[1] for row in rows], "Close": [row[2] for row in rows]},
        index=index,
    )
    frame["Open"] = frame["Close"]
    frame["Volume"] = 1_000_000.0
    frame["Stock Splits"] = 0.0
    frame["Dividends"] = 0.0
    return frame[["Open", "High", "Low", "Close", "Volume", "Stock Splits", "Dividends"]]


def a_payout_that_confirms_the_peak_series(*, flag_depth_pct: float = 10.1, start: str = "2026-01-02") -> pd.DataFrame:
    """A structure whose peak is a confirmed turning point only because of the ex-date drop.

    The cash comes out of the print on the ex-date, and that drop is a retracement the stock never
    made. Read on the tape the segmentation confirms the top; read with every print on one scale
    it confirms nothing, so the withheld qualification is withheld on arithmetic about the
    dividend rather than on anything the stock did.
    """

    frame = power_play_series(flag_depth_pct=flag_depth_pct, start=start)
    frame["High"] = frame["Close"] * 1.03
    frame["Low"] = frame["Close"] * 0.97
    peak = int(frame["High"].to_numpy().argmax())
    ex_date = peak + 5
    frame.iloc[ex_date, frame.columns.get_loc("Dividends")] = 1.1
    columns = frame.columns.get_indexer(["Open", "High", "Low", "Close"])
    frame.iloc[ex_date:, columns] -= 1.1
    return frame


def a_top_behind_a_taller_bar_series(*, start: str = "2026-01-02") -> pd.DataFrame:
    """A confirmed top the descent reaches only if a bar it walked past leaves the window alone.

    The frame opens on a long slide from a high nothing confirms, so the search meets that taller
    bar before it meets the confirmed top in April. That bar is walked past -- it is not a reading
    of the structure -- and if walking past it also moves the *date* the next search must precede,
    the April top is behind it forever, though it is lower and the union confirms it.

    Read from that top the flag runs thirty-one sessions, past the six-week limit.
    """

    frame = a_top_only_a_neighbour_confirms_series(start=start)
    slide = np.r_[np.linspace(110.0, 104.2, 36), np.linspace(104.1, 50.1, 23), [50.0]]
    for position, close in enumerate(slide):
        for column, value in (
            ("Open", close),
            ("Close", close),
            ("High", close * 1.001),
            ("Low", close * 0.999),
        ):
            frame.iloc[position, frame.columns.get_loc(column)] = value
    return frame
