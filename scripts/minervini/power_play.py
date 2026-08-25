"""Measure a Power Play from completed bars, with no doctrine in the room.

The same contract the base measurements keep: the registry owns every limit, the windows
arrive as an argument, and this returns numbers or ``None`` and decides nothing.

The structure is read backward from the session being traded, because that is the only form
the question is asked in. "The stock price *then* moves sideways" -- the flag runs from the
peak to the last completed bar, so the peak is looked for inside the longest flag the source
allows, and the advance inside the longest advance it allows before that peak. Both windows
are anchored at the last bar, which is what keeps the answer from moving when a caller loads
a different amount of history: measured against the whole history's maximum instead, fourteen
of eighteen real tickers reported a different peak, a different advance, or both, at two
lookbacks that differed only in how much dormancy they included.

That anchoring is also where the eight-week and six-week limits are enforced. They are not
emitted as gates that could reject, because nothing outside them is ever measured: an advance
that took nine weeks cannot be found by a search that only looks back eight, and its ninth
week is not silently forgiven -- it is the reason the eight-week window reports a smaller
advance than the criterion needs.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd

from .setup_structure import _CORPORATE_ACTION_COLUMN, _DISTRIBUTION_COLUMN, read_bars


def _paid_between(bars: pd.DataFrame, start: int, end: int) -> float | None:
    """What a holder was paid in cash across a span, or nothing when the input could not say.

    Reported as an amount rather than as an event, because that is the difference between a
    distribution and a split: the split's effect on a ratio is a rescale of unknown reach, and
    this one is a number that can be added back to the price it came out of.
    """
    if _DISTRIBUTION_COLUMN not in bars:
        return None
    return float(bars.iloc[start:end + 1][_DISTRIBUTION_COLUMN].sum())


def _dated_events(bars: pd.DataFrame, column: str, start: int, end: int) -> list[str] | None:
    """The dated events of one kind inside a span, or nothing when the input could not say."""

    if column not in bars:
        return None
    span = bars.iloc[start:end + 1]
    return [stamp.date().isoformat() for stamp in span.index[span[column] > 0]]


def _empty(reason: str | None) -> dict[str, Any]:
    return {
        "peak_date": None,
        "peak_high": None,
        "peak_close": None,
        "advance_low": None,
        "advance_low_date": None,
        "advance_pct": None,
        "advance_pct_closes": None,
        "advance_low_close": None,
        "corporate_action_evidence": None,
        "corporate_action_sessions": None,
        "distribution_sessions": None,
        "distribution_paid_in_the_flag": None,
        "distribution_paid_in_the_advance": None,
        "measured_span_first_session": None,
        "baseline_first_session": None,
        "baseline_last_session": None,
        "advance_anchor_date": None,
        "advance_sessions": None,
        "advance_weeks": None,
        "launch_volume_ratio": None,
        "advance_peak_volume_ratio": None,
        "advance_peak_volume_date": None,
        "advance_volume_ratio": None,
        "flag_sessions": None,
        "flag_weeks": None,
        "flag_depth_pct": None,
        "flag_low": None,
        "flag_low_date": None,
        "rejection": reason,
    }


def _label(bars: Any, position: int) -> str | None:
    """One session's date, or nothing when the position falls outside the loaded history."""

    if position < 0 or position >= len(bars):
        return None
    return str(bars.index[position].date())


def measure_power_play(history: Any, spec: Mapping[str, Any], *, below: float | None = None, before: str | None = None) -> dict[str, Any]:
    """Reduce a history to the numbers the Power Play criteria are read against.

    ``below`` and ``before`` cap the peak search, which is how the same bars are read a second time
    from the highest top preceding the one they were first read from. Both bounds are needed: a
    lower top *inside* the flag is later than the peak the flag hangs from and cannot be an
    alternative reading of it -- it is the same structure with most of itself cut off. Nothing
    else about the measurement changes; it is the same arithmetic asked about another candidate.
    """

    bars, rejection = read_bars(history)
    if bars is None:
        return _empty(rejection)

    flag_window = int(spec["flag_window_sessions"])
    advance_window = int(spec["advance_window_sessions"])
    # The same conversion the windows were compiled through. Divided by a constant here instead,
    # the two owners agree only as long as the registered value stays five: at four, a
    # twenty-five session flag is six and a quarter weeks and this would pass it as five.
    week = int(spec["sessions_per_trading_week"])

    # The peak the flag hangs from is the highest bar of the longest structure the criteria
    # describe -- an advance of up to eight weeks and a flag of up to six -- and then the FIRST
    # session that printed it, counting from the last time the stock traded above it.
    #
    # Both halves of that are load-bearing, and each was wrong on its own once. Looking only
    # inside the flag's own limit makes the limit satisfied by the search: every flag measures
    # six weeks or less because nothing longer can be found, and a stock ten weeks past its
    # high reports a fictional flag off some lower high inside the decline. Reading the peak
    # from the LAST equal high instead re-labels the flag before it as advance, so a forty
    # session flag becomes twelve and clears the limit that way. Together the limit rejects
    # what it is supposed to reject: a flag that really ran ten weeks measures ten.
    window = bars.iloc[-(advance_window + flag_window + 1):]
    if below is not None:
        window = window.loc[window["High"] < below]
    if before is not None:
        window = window.loc[window.index < pd.Timestamp(before)]
    if not len(window):
        return _empty("history_has_no_earlier_top_to_read_from")
    peak_high = float(window["High"].max())
    # Inside the search span and nowhere else. Taking the first equal high anywhere in the loaded
    # history is the mirror of taking the last: one glues the flag to a session months earlier
    # that merely printed the same price, the other re-labels the flag as advance. A tie says
    # nothing about whether two sessions belong to one structure, so the span decides which ties
    # are even candidates and the first of those starts the flag.
    #
    # A version of this also looked for the last session that traded *above* the peak and started
    # from there. Nothing can trade above the maximum of the window it is the maximum of, so that
    # search never found anything and the clause described a rule the code did not run.
    peak_label = window.index[window["High"] == peak_high][0]
    peak = int(bars.index.get_loc(peak_label))

    before = bars.iloc[max(0, peak - advance_window):peak]
    flag = bars.iloc[peak + 1:]

    if not len(before):
        return _empty("history_has_no_sessions_before_the_peak")

    # The extremes reading, reported and never gating. A bar that wicked to forty-nine three days
    # after a launch from fifty is the lowest low of the window without being where anything
    # began: read as the advance's origin it measured the price move from seventy-five instead of
    # fifty, and put the ten-times-volume session that started the move outside the span looked at.
    low_label = before["Low"].idxmin()
    advance_low = float(before.loc[low_label, "Low"])
    advance_low_close = float(before["Close"].min())
    # One session anchors the size of the move, its length, and the volume it came out of. Reading
    # the price close to close and the duration from the lowest low counts them from two different
    # days: a forty-session advance whose late bar wicked down reports eight weeks of price gain
    # in one week of time, and the eight-week limit never sees it.
    #
    # The *last* session at that close, not the first. Ties are the normal case -- a stock sitting
    # quiet for forty sessions closes at its low repeatedly -- and the first of them dates the
    # advance to wherever the loaded history happens to begin. The last one is the last session the
    # stock was still at its low, which is the session the move left.
    lows = before.index[before["Close"] == advance_low_close]
    launch = int(bars.index.get_loc(lows[-1]))
    # What the stock traded before this move began, so no session of the advance is in its own
    # baseline. Anchored to the launch rather than to a fixed offset from the peak, because a
    # window forty to eighty sessions ahead of the peak is whatever regime the stock was in then:
    # forty old sessions at ten million behind thirty-one quiet ones at one million made a
    # five-times launch measure as half, and removed it as a known failure.
    #
    # Required in full rather than taken as far as it reaches: sliced to a shorter lookback, five
    # real tickers reported the same peak, advance and flag while this ratio moved, because the
    # only thing that had changed was how many sessions were left to average.
    #
    # The median, not the mean. One 400M session in an otherwise 400K history lifts the mean to
    # 10M, and a genuine ten-fold expansion to 4M then measures as 0.38 of it -- an advance that
    # plainly expanded, removed as a known failure by an outlier behind it.
    start = peak - advance_window
    baseline = bars.iloc[launch - advance_window:launch] if launch >= advance_window else bars.iloc[0:0]
    # The first session anything here reads. Derived from the baseline rather than restated, so
    # moving the baseline moves the span checked for corporate actions with it.
    # With no baseline to reach back through, the advance window itself is the earliest thing read.
    earliest = max(0, launch - advance_window if len(baseline) else start)

    # The advance itself, which is the span the anchor and the peak bound. Read across the whole
    # eight-week window instead, the numerator overlapped the baseline -- dormancy compared with
    # itself, so a heavy session before the move commenced reported as the expansion it commenced
    # on -- and it stopped one bar short of the peak, which in a one-session advance dropped the
    # only session there was and read a six-times launch as no expansion at all.
    advance = bars.iloc[launch + 1:peak + 1]
    baseline_volume = float(baseline["Volume"].median()) if len(baseline) else None
    measurable = baseline_volume is not None and baseline_volume > 0

    return {
        "peak_date": peak_label.date().isoformat(),
        "peak_high": peak_high,
        "peak_close": float(bars.iloc[peak]["Close"]),
        "advance_low": advance_low,
        "advance_low_date": low_label.date().isoformat(),
        # Three readings of one move, because the raw tape cannot tell a move from a corporate
        # action or from a single wick. Extremes take the session's own low against the peak's
        # own high and are the widest; the closes reading is the same move between two prices the
        # tape settled at; the adjusted reading is that one corrected for splits and dividends.
        #
        # Reported apart rather than reduced to one number here. Which reading a criterion is
        # read against is doctrine, and taking the smallest -- the first thing tried -- turns the
        # source's single hundred percent condition into a new three-way AND: on real bars the
        # extremes reading runs a median of 5.4 points above the closes one, and on the one
        # ticker whose advance actually reached a hundred percent it was 101.8 against 96.4.
        "advance_pct": (peak_high - advance_low) / advance_low * 100 if advance_low > 0 else None,
        "advance_pct_closes": (float(bars.iloc[peak]["Close"]) - advance_low_close) / advance_low_close * 100 if advance_low_close > 0 else None,
        "advance_low_close": advance_low_close,
        # Whether a corporate action sits anywhere the measurements read, and -- separately --
        # whether the input was in a position to say. A history that does not carry the event
        # column has not reported "no split"; it has reported nothing, and folding those together
        # is how a reverse split that moved nobody's money reads as a hundred percent advance.
        #
        # The span is every session any measurement here reads: from the volume baseline through
        # the last bar. Both ends were wrong once, and the near end twice. Starting at the launch
        # leaves a split before the advance with the baseline in pre-split share counts and the
        # advance in post-split ones -- forty quiet sessions at 100K against a launch at 1M is an
        # eight-fold expansion that never happened. Starting forty sessions before the launch is
        # the same bug one step quieter: the baseline is anchored to the peak, the launch is
        # wherever the lowest low fell inside the window, and the gap between them is baseline the
        # span never covered. Ending at the peak misses the flag, which is measured too: a
        # two-for-one split partway through it halves every printed price after it, so the flag
        # reads as a fifty percent correction nobody took and the history that cannot be measured
        # comes back as a confident failure on depth.
        "corporate_action_evidence": "present" if _CORPORATE_ACTION_COLUMN in bars else "missing",
        "corporate_action_sessions": _dated_events(bars, _CORPORATE_ACTION_COLUMN, earliest, len(bars) - 1),
        "distribution_sessions": _dated_events(bars, _DISTRIBUTION_COLUMN, earliest, len(bars) - 1),
        # Split by the span each criterion reads, because a payout only moves the measurement it
        # was paid inside of.
        "distribution_paid_in_the_flag": _paid_between(bars, peak + 1, len(bars) - 1),
        "distribution_paid_in_the_advance": _paid_between(bars, launch + 1, peak),
        # The three boundaries the numbers above are counted between. A duration reported without
        # the session it is counted from cannot be checked, and the anchor is deliberately not the
        # extremes date printed beside it.
        "measured_span_first_session": _label(bars, earliest),
        "baseline_first_session": _label(bars, launch - advance_window) if len(baseline) else None,
        "baseline_last_session": _label(bars, launch - 1) if len(baseline) else None,
        "advance_anchor_date": _label(bars, launch),
        "advance_sessions": peak - launch,
        "advance_weeks": (peak - launch) / week,
        # Three readings of the volume clause, because "commences on huge volume" asks about a
        # session and the search cannot say for certain which session that was.
        #
        # The average across the advance answers a different question and answers it wrongly: one
        # bar at ten times its baseline followed by nineteen quiet ones averages below the
        # baseline and reads as no expansion at all. The lowest bar is not reliably the one the
        # move began on either -- a quiet undercut five weeks before the peak wins the lowest-low
        # search, and reading the clause there reported no expansion on a stock that went from
        # ninety to two hundred in nine sessions at ten times its usual volume.
        #
        # So the heaviest session of the advance is reported with its date, and it is the reading
        # a numberless observation can be taken on: an advance with no expanded session anywhere
        # in it did not commence on huge volume under any identification of its first bar. Whether
        # the expansion was *huge*, and whether it came at the commencement rather than in the
        # middle, is what the chart is asked -- and the date beside the ratio is what that
        # question is asked about.
        # The first session of the move rather than the last session before it: "an explosive
        # price move commences on huge volume" points at the bar that did the commencing, and the
        # anchor is by construction the last quiet one.
        "launch_volume_ratio": float(bars.iloc[min(launch + 1, peak)]["Volume"]) / baseline_volume if measurable else None,
        "advance_peak_volume_ratio": float(advance["Volume"].max()) / baseline_volume if measurable else None,
        "advance_peak_volume_date": advance.index[int(advance["Volume"].to_numpy().argmax())].date().isoformat() if measurable else None,
        "advance_volume_ratio": float(advance["Volume"].mean()) / baseline_volume if measurable else None,
        "flag_sessions": int(len(flag)),
        "flag_weeks": len(flag) / week,
        "flag_depth_pct": (peak_high - float(flag["Low"].min())) / peak_high * 100 if len(flag) else None,
        "flag_low": float(flag["Low"].min()) if len(flag) else None,
        "flag_low_date": flag["Low"].idxmin().date().isoformat() if len(flag) else None,
        "rejection": None,
    }





_CLAIM = "fundamentals.power_play_exception"
# What a Power Play must positively have. Qualification is this list being satisfied, never an
# absence of objections -- the same rule the setup routes are built on, for the same reason: a
# structure nobody measured has nothing to object to.
_REQUIRED = (
    f"{_CLAIM}.advance_minimum_pct",
    f"{_CLAIM}.advance_maximum_weeks",
    f"{_CLAIM}.flag_minimum_sessions",
    f"{_CLAIM}.flag_maximum_weeks",
    f"{_CLAIM}.flag_maximum_decline_gate_pct",
    f"{_CLAIM}.launch_volume_character",
    f"{_CLAIM}.flag_tightness_or_vcp",
)
_CORPORATE_ACTIONS = "corporate_action_evidence"
# What a corporate action costs a reading, which is all of it. A split rescales every printed
# price and every share count, so a depth, an advance and a volume ratio measured across one are
# arithmetic about the action rather than about the stock.
#
# The session counts looked exempt -- sixty-five sessions is sixty-five sessions whatever the
# prices did -- and they are not, because the peak they are counted from is itself chosen by
# comparing prices. A forward split in the flag halves everything after the real top and leaves
# it standing, which is what made the exemption look sound; the same event in the other direction
# doubles the flag's own bars until they outprint the top, and a sixty-five session flag measures
# as zero. A split inside the advance makes the last pre-split bar the highest high and hands
# back a thirty-five session flag for a structure that had twenty.
#
# Detecting an action and then letting what it manufactured reject the stock is worse than not
# detecting it: the answer comes back as a confident finding about price action that never
# happened. So while an action stands in the span, nothing here decides, and the measurements
# stay in the payload for a person to read -- the same separation an uncorroborated chain gets in
# the setup path, and for the same reason.


# The one criterion a structure can miss by not having happened yet. Twelve sessions is the least
# a flag can be and still be one, so a shorter flag has not failed the criterion -- it has not
# finished, and the only thing it needs is time.
#
# That distinction decides real cases here because the peak is found rather than declared. A new
# high a hundredth of a percent above the last one restarts the flag, and the source names no size
# below which a new high stops counting; calling the four sessions after it a failure removes a
# twenty-session flag from consideration on the strength of one cent.
FLAG_STILL_FORMING = f"{_CLAIM}.flag_minimum_sessions"
_STILL_FORMING = FLAG_STILL_FORMING


def reading_rejects(criteria: Mapping[str, str], *, corporate_action_unmoved: bool) -> bool:
    """Whether one reading of the structure rejects on its own, under the reducer's trust rule.

    Two readings of the same bars can disagree about every intermediate state and still both
    reject. A rejection is the one outcome a later chart reading never overturns, so when both
    reach it the choice between the tops decided nothing -- withholding the verdict then discards
    a finding the bars made twice, and reports a forty percent advance as an open question.

    The trust rule has to be the reducer's own, or the two would drift into calling a structure
    settled on a failure the reducer will not use. Hence one predicate, read from both sides.
    """
    if not corporate_action_unmoved:
        return False
    return any(
        criteria.get(claim_id[len(_CLAIM) + 1:]) == "fail" and claim_id != _STILL_FORMING
        for claim_id in _REQUIRED
    )


# Which reported band each criterion shares a measurement with. A band is not required evidence
# and no reducer reads it, but it is in the machine channel beside the gate, measured off the same
# peak -- so when the gate is withheld and the band is not, the channel contradicts itself one
# line down.
_BANDS_BESIDE = {
    f"{_CLAIM}.flag_minimum_sessions": f"{_CLAIM}.flag_duration_weeks",
    f"{_CLAIM}.flag_maximum_weeks": f"{_CLAIM}.flag_duration_weeks",
    f"{_CLAIM}.flag_maximum_decline_gate_pct": f"{_CLAIM}.flag_maximum_decline_pct",
}


def _withhold(signal: Mapping[str, Any], cause: str) -> dict[str, Any]:
    """The measurement kept, the verdict withdrawn, the reason named.

    `unavailable` rather than a new word, because that is what every other reading in the harness
    says when it has a number it cannot turn into an answer.
    """
    return {**signal, "state": "unavailable", "withheld": cause}


def evaluate_power_play(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Classify a measured Power Play without deciding what may be done about it.

    Two of the four criteria end in questions completed bars do not answer -- whether volume was
    *huge* rather than merely expanded, and whether a flag outside ten percent nonetheless shows
    VCP character -- so a structure that clears every measurable limit comes back incomplete and
    names the reading it waits on. That is the honest shape of this capability today: it removes
    candidates deterministically and assembles the evidence for the ones it cannot remove.
    """
    signals = {str(signal["id"]): signal for signal in evidence.get("signals") or []}
    unmoved = evidence.get(_CORPORATE_ACTIONS) == "present" and not evidence.get("corporate_action_sessions")
    # A criterion resting on which of two tops the search landed on is a statement about the
    # search. Read per criterion rather than as one verdict-wide switch, because the two readings
    # can reach the same conclusion by different routes: throwing away everything they agreed on
    # reports a forty percent advance as an open question, and trusting everything reports a limit
    # the rival reading says was never exceeded.
    contested = set(evidence.get("contested_criteria") or ())
    # A payout inside the span is the third way a criterion can stop being the stock's own.
    payout_sensitive = set(evidence.get("payout_sensitive_criteria") or ())
    # Only the tops speak to this. A payout withholds the criterion it decided and says so under
    # its own name; calling it a question about which top the search landed on sends the reader
    # looking at the chart for something the dividend calendar already answered.
    settled = not contested
    failed: list[str] = []
    missing: list[str] = []
    for claim_id in _REQUIRED:
        signal = signals.get(claim_id)
        state = None if signal is None else str(signal.get("state"))
        condition = claim_id[len(_CLAIM) + 1:]
        agreed = condition not in contested and condition not in payout_sensitive
        trusted = agreed and unmoved
        if state == "pass" and trusted:
            continue
        if state == "fail" and claim_id != _STILL_FORMING and trusted:
            failed.append(claim_id)
        else:
            missing.append(claim_id)

    # A history that does not carry the event column has not said there was no split, and a span
    # containing one is a span whose prices are partly the action rather than the stock. Neither
    # is a finding about the stock, so both are gaps rather than failures.
    if evidence.get(_CORPORATE_ACTIONS) != "present" or evidence.get("corporate_action_sessions"):
        missing.append(_CORPORATE_ACTIONS)
    if not settled:
        missing.append("peak_identity")

    # Whatever the reducer declined, the machine channel declines too -- each under the cause that
    # actually withdrew it, because a reader who fixes the wrong thing has not fixed anything.
    withheld: dict[str, str] = {}

    def _decline(claim_ids: set[str], cause: str) -> None:
        for claim_id in claim_ids:
            withheld.setdefault(claim_id, cause)
            band = _BANDS_BESIDE.get(claim_id)
            if band is not None:
                withheld.setdefault(band, cause)

    if not unmoved:
        cause = (
            "corporate_action_evidence_missing"
            if evidence.get(_CORPORATE_ACTIONS) != "present"
            else "corporate_action_inside_the_measured_span"
        )
        _decline({str(signal["id"]) for signal in signals.values()} | set(_BANDS_BESIDE.values()), cause)
    _decline({f"{_CLAIM}.{condition}" for condition in payout_sensitive}, "distribution_inside_the_measured_span")
    _decline({f"{_CLAIM}.{condition}" for condition in contested}, "peak_identity_disputed")
    reported = [
        _withhold(signal, withheld[str(signal["id"])]) if str(signal["id"]) in withheld else dict(signal)
        for signal in evidence.get("signals") or []
    ]

    # A criterion both readings agreed on, or a rejection both readings reached by their own
    # routes. The second leaves nothing trustworthy to name -- reporting the primary reading's
    # list would name limits the rival says were never exceeded -- but there is no reading of
    # these bars under which the structure qualifies, and that is a finished answer.
    rejected_under_every_reading = bool(evidence.get("rejected_under_every_reading"))
    if failed or rejected_under_every_reading:
        state = "not_qualified"
    elif missing:
        state = "incomplete"
    else:
        state = "qualified"
    return {
        "power_play_state": state,
        "required_evidence": list(_REQUIRED),
        "failed": failed,
        "missing": missing,
        "structure": evidence.get("structure") or {},
        "measurements": evidence.get("measurements") or {},
        "peak_identity": evidence.get("peak_identity"),
        "contested_criteria": sorted(contested),
        "payout_sensitive_criteria": sorted(payout_sensitive),
        "readings": evidence.get("readings"),
        "surviving_readings": evidence.get("surviving_readings"),
        "reading_rejections": evidence.get("reading_rejections"),
        "rejected_under_every_reading": rejected_under_every_reading,
        "alternate_peak": evidence.get("alternate_peak"),
        "corporate_action_evidence": evidence.get(_CORPORATE_ACTIONS),
        "distribution_sessions": evidence.get("distribution_sessions"),
        "corporate_action_sessions": evidence.get("corporate_action_sessions"),
        "signals": reported,
    }


__all__ = ["FLAG_STILL_FORMING", "evaluate_power_play", "measure_power_play", "reading_rejects"]
