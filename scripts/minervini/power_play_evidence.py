"""Wire the Power Play measurements to the claim they are read against.

The measurement module knows no doctrine and takes its windows as an argument; this is where
those windows come from. Both are the source's own limits -- eight weeks of advance, six of
flag -- converted to sessions through a registered parameter rather than a constant, because
whether a thirty-one session flag is inside six weeks is a verdict that conversion decides.

Enforcing a limit by not looking past it is not the same as forgiving what lies beyond. The
advance is searched inside the eight weeks the criterion allows, so a stock that took nine
weeks to double reports whatever it managed in eight and fails on that number.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from . import doctrine
from .setup_structure import _DISTRIBUTION_COLUMN, read_bars
from .power_play import FLAG_STILL_FORMING, measure_power_play, reading_rejects


_CLAIM = "fundamentals.power_play_exception"
_WEEK = "convention.trading_week"
_TOPS = "convention.power_play_top_candidates"
# A runaway guard, not a doctrine limit: the longest chain any cached history produced was
# nineteen tops. Hitting it is reported, never silently truncated into an agreement.
_MOST_TOPS_READ = 200
# The one refusal that means the chain is finished rather than unreadable.
_NO_MORE_TOPS = "history_has_no_earlier_top_to_read_from"


def compile_power_play_spec() -> dict[str, Any]:
    """The two search windows, in completed sessions."""

    week = int(doctrine.parameter(_WEEK, "sessions_per_trading_week"))
    return {
        "advance_window_sessions": int(doctrine.threshold(_CLAIM, "advance_maximum_weeks")) * week,
        "flag_window_sessions": int(doctrine.threshold(_CLAIM, "flag_maximum_weeks")) * week,
        # Carried rather than re-derived, so the module that reports durations in weeks converts
        # them the same way the windows were compiled.
        "sessions_per_trading_week": week,
        # Where the chain of candidate tops stops. Registered at the harness layer rather than
        # borrowed from the tight-action figure it happens to equal: that one describes a flag's
        # decline after a peak has been chosen and offers VCP character as an alternative to it,
        # and neither of those is a statement about which printed high the flag hangs from.
        "candidate_top_maximum_distance_pct": float(
            doctrine.parameter(_TOPS, "candidate_top_maximum_distance_pct")
        ),
    }





def _summary(claim_id: str) -> str:
    return str(doctrine.get_claim(claim_id)["claim"]["rule"]["summary"])


def _observation(condition: str, state: str, measured: Any, required: str) -> dict[str, Any]:
    """One criterion the source states without a magnitude, reported under its own name.

    The id carries the condition and the doctrine_id carries the claim, because four separate
    criteria live inside this one exception and a signal named only after the claim would have
    them overwrite each other. Prefix lookup finds the claim from the id, which is how the rest
    of the engine already resolves a threshold's owner.
    """
    return {
        "id": f"{_CLAIM}.{condition}",
        "doctrine_id": _CLAIM,
        "role": "observation",
        "binds": doctrine.binds(_CLAIM),
        "state": state,
        "measured": measured,
        "required": required,
    }


def _volume_state(ratio: float | None) -> str:
    """"An explosive price move commences on huge volume."

    No magnitude is attached to "huge", so no ratio here can pass it -- but an advance with no
    expanded session anywhere in it did not commence on huge volume under any reading of which
    session was its first, and observing that needs no number. Everything above that line is the
    chart's to answer.
    """
    if ratio is None:
        return "unavailable"
    return "needs_chart" if ratio > 1 else "fail"


def _tightness_state(depth: float | None, limit: float) -> str:
    """"very tight price action that doesn't correct ... more than 10 percent, or ... VCP."

    An or, and evaluating the tight half alone would turn the source's alternative into a
    requirement. A flag inside ten percent satisfies the criterion on measurement. One outside it
    has not failed the criterion; it has fallen to the other branch, and whether a flag shows VCP
    character over twelve to thirty sessions is not something these bars settle.
    """
    if depth is None:
        return "unavailable"
    return "pass" if depth <= limit else "needs_chart"


def _without_the_payout(measurements: Mapping[str, Any]) -> dict[str, Any]:
    """The same measurements with the cash the company paid added back to the price it left.

    Not a correction of the tape -- the printed prices stay printed. It is the second reading the
    criteria are checked against, so that a payout decides a verdict only when the verdict was
    going to turn on it. Blocking on any distribution instead would leave every dividend payer
    unreadable for months at a time over a fraction of a percent.
    """
    adjusted = dict(measurements)
    paid_in_the_flag = measurements["distribution_paid_in_the_flag"]
    if paid_in_the_flag and measurements["flag_depth_pct"] is not None:
        peak_high = measurements["peak_high"]
        adjusted["flag_depth_pct"] = (
            (peak_high - measurements["flag_low"] - paid_in_the_flag) / peak_high * 100
        )
    paid_in_the_advance = measurements["distribution_paid_in_the_advance"]
    if paid_in_the_advance and measurements["advance_pct_closes"] is not None:
        low_close = measurements["advance_low_close"]
        adjusted["advance_pct_closes"] = (
            (measurements["peak_close"] + paid_in_the_advance) / low_close - 1
        ) * 100
    return adjusted


def _criteria(measurements: Mapping[str, Any], tight_limit: float) -> dict[str, str]:
    """How each criterion reads on one set of measurements, without the payloads."""

    return {
        "advance_minimum_pct": doctrine.evaluate_gate(_CLAIM, "advance_minimum_pct", measurements["advance_pct_closes"])["state"],
        "advance_maximum_weeks": doctrine.evaluate_gate(_CLAIM, "advance_maximum_weeks", measurements["advance_weeks"])["state"],
        "flag_minimum_sessions": doctrine.evaluate_gate(_CLAIM, "flag_minimum_sessions", measurements["flag_sessions"])["state"],
        "flag_maximum_weeks": doctrine.evaluate_gate(_CLAIM, "flag_maximum_weeks", measurements["flag_weeks"])["state"],
        "flag_maximum_decline_gate_pct": doctrine.evaluate_gate(_CLAIM, "flag_maximum_decline_gate_pct", measurements["flag_depth_pct"])["state"],
        "launch_volume_character": _volume_state(measurements["advance_peak_volume_ratio"]),
        "flag_tightness_or_vcp": _tightness_state(measurements["flag_depth_pct"], tight_limit),
    }


# Every session this reading treats as a boundary of the structure. Comparing peak dates alone
# asks whether the payout picked the top, and the top is not the only thing it picks: the anchor
# is the last session at the window's lowest close, so a distribution can leave the peak exactly
# where it was and still move where the advance starts, how long it took, and which forty sessions
# the volume is measured against.
_BOUNDARIES = (
    "peak_date",
    "advance_anchor_date",
    "flag_low_date",
    "baseline_first_session",
    "baseline_last_session",
    "measured_span_first_session",
)


def _boundaries(measurements: Mapping[str, Any]) -> tuple[Any, ...]:
    return tuple(measurements[name] for name in _BOUNDARIES)


def _signature(walk: Mapping[str, Any]) -> tuple[Any, ...]:
    """Everything about one walk of the tops that a distribution could have chosen."""

    return (
        tuple(_boundaries(reading) for reading in walk["readings"]),
        walk["may_contest"],
        walk["ran_out_of_history"],
    )


def _on_one_scale(history: Any) -> Any:
    """The same bars with every print put on the scale that follows all of its distributions.

    Only ever used to ask whether the tops keep their order. The measurement itself stays on the
    prints the tape made -- this harness names corporate events rather than rewriting prices --
    but *which* bar is the highest is a comparison across sessions, and across an ex-date that
    comparison is between two scales. A session before a payout can outprint the top the stock
    actually made, and the flag then hangs from a bar the dividend chose; worse, the real top is
    later than it and a chain that walks backward never reaches it.
    """
    # Through the same normaliser the measurement uses. Read straight off the caller's frame, a
    # history handed over newest-first accumulated its distributions backwards and this check
    # answered the opposite question -- same dates, same prices, opposite verdict. Row order is
    # not evidence, and one module owns saying so.
    bars, _ = read_bars(history)
    if bars is None or _DISTRIBUTION_COLUMN not in bars:
        return None
    adjusted = bars.copy()
    # What each session still had coming to it. Subtracting it puts every print after the last
    # distribution and every print before it on the same footing.
    owed = adjusted[_DISTRIBUTION_COLUMN][::-1].cumsum()[::-1] - adjusted[_DISTRIBUTION_COLUMN]
    for column in ("Open", "High", "Low", "Close"):
        adjusted[column] = adjusted[column] - owed
    return adjusted


def _read_criteria(measurements: Mapping[str, Any], tight_limit: float) -> tuple[dict[str, str], set[str]]:
    """One reading's criteria, with whatever a cash payout decided taken back out of them.

    Computed per reading rather than once for the top one, because the tops sit at different
    sessions and a longer flag holds payouts a shorter one never saw. Left to the top reading
    alone, an earlier candidate could reject on a depth its own payout manufactured and cast that
    into "every reading rejects".
    """
    criteria = _criteria(measurements, tight_limit)
    without = _criteria(_without_the_payout(measurements), tight_limit)
    decided_by_the_payout = {condition for condition, state in criteria.items() if without[condition] != state}
    return (
        {
            condition: "unavailable" if condition in decided_by_the_payout else state
            for condition, state in criteria.items()
        },
        decided_by_the_payout,
    )


def _unmoved(measurements: Mapping[str, Any]) -> bool:
    """Whether this reading's own span is free of corporate actions.

    Each reading carries its own span, because the tops cover different sessions and a split
    inside one of them says nothing about another.
    """
    return (
        measurements["corporate_action_evidence"] == "present"
        and not measurements["corporate_action_sessions"]
        and measurements["distribution_evidence"] == "present"
    )


def _walk_the_tops(history: Any, spec: Mapping[str, Any], first: Mapping[str, Any]) -> dict[str, Any]:
    readings: list[dict[str, Any]] = []
    below, before = None, None
    top = first["peak_high"]
    # The chain is walked to the end of the span, and the registered distance decides only which
    # of those tops may *contest* a criterion. Contesting is a claim about one structure, so a top
    # far below the highest is a different structure and letting it dispute a limit would leave
    # every criterion permanently open -- unbounded contesting walks an ordinary advance one bar
    # at a time and nothing ever decides.
    #
    # Objecting is weaker and survives the distance. A structure the chain walked past is still a
    # reading of these bars under which nothing decisive failed, and rejecting while holding its
    # date in hand decides against evidence already in the envelope: one cent on a later high used
    # to delete a hundred-and-eight percent advance in five weeks from consideration entirely.
    #
    # The count bound is a runaway guard. Reaching it is reported rather than passed over.
    bound = spec["candidate_top_maximum_distance_pct"]
    cut_at: dict[str, Any] | None = None
    ran_out_of_history = False
    may_contest = 0
    while len(readings) < _MOST_TOPS_READ:
        reading = first if not readings else measure_power_play(history, spec, below=below, before=before)
        if reading["rejection"] is not None:
            # One refusal means the opposite of the others. `_NO_MORE_TOPS` is the chain ending;
            # anything else is a top that exists with too little history behind it to measure --
            # a gap, and treating it as the chain ending turns it into a silent vote for whatever
            # the tops above it decided. That is the shape a recently listed stock arrives in.
            if reading["rejection"] != _NO_MORE_TOPS:
                ran_out_of_history = True
            break
        distance = None if top is None else (top - reading["peak_high"]) / top * 100
        if distance is not None and distance > bound:
            if cut_at is None:
                cut_at = {"peak_date": reading["peak_date"], "distance_pct": distance}
        else:
            may_contest = len(readings) + 1
        readings.append(reading)
        below, before = reading["peak_high"], reading["peak_date"]
    return {
        "readings": readings,
        "cut_at": cut_at,
        "ran_out_of_history": ran_out_of_history,
        "may_contest": may_contest,
    }


def build_power_play_evidence(history: Any) -> dict[str, Any]:
    """Measure a history and read the criteria against it, deciding nothing.

    The structure is found rather than declared, so the same bars are read from every top the
    search could have landed on: the highest of the span, then the highest below that, and down
    until a top stands further below the highest than the registered candidate distance. The
    source names no size below which a new high stops counting -- a hundredth of a percent above
    the last high restarts the flag and turns thirty sessions into four -- so a criterion decides
    only where every top read answers it the same way, and a rejection stands only where every
    one of them reaches one.

    Two readings were not enough, and the shortfall was not theoretical: two ticks a hundredth of
    a percent apart inside one flag hand the search three tops, and both of the first two reject
    while the structure they sit inside has nothing decisive against it. Nor is the chain left
    open: unbounded it runs to nineteen tops across the cached histories and walks an ordinary
    advance one bar at a time, and twenty-two of twenty-three tickers still reject on an agreed
    criterion; bounded it runs to fifteen and all twenty-three do.
    """

    spec = compile_power_play_spec()
    tight_limit = float(doctrine.threshold(_CLAIM, "tight_action_maximum_pct"))
    measurements = measure_power_play(history, spec)
    actions = measurements["corporate_action_sessions"]

    walk = _walk_the_tops(history, spec, measurements)
    readings, cut_at = walk["readings"], walk["cut_at"]
    ran_out_of_history, may_contest = walk["ran_out_of_history"], walk["may_contest"]
    exhausted = len(readings) >= _MOST_TOPS_READ

    # Which criteria a cash payout inside the span decided. Everything else it touched, it did
    # not decide, and an ordinary quarterly payment touches nearly nothing against these limits.
    every_criteria, every_payout_sensitive = map(
        list, zip(*(_read_criteria(reading, tight_limit) for reading in readings))
    ) if readings else ([], [])
    primary_criteria = every_criteria[0] if readings else _read_criteria(measurements, tight_limit)[0]
    # Every reading's, not the highest top's alone. The tops sit at different sessions, so a
    # criterion a payout decided for one of them would otherwise reach the envelope as a question
    # about which top the search landed on -- and send the reader to the chart for something the
    # dividend calendar already answered.
    payout_sensitive = set().union(*every_payout_sensitive) if readings else _read_criteria(measurements, tight_limit)[1]
    contested = {
        condition
        for condition in primary_criteria
        if any(criteria[condition] != primary_criteria[condition] for criteria in every_criteria[:may_contest])
    }
    # And the ordering itself. If the tops keep their places once every print is on one scale, the
    # search read the stock; if they do not, it read the dividend, and no amount of adding cash
    # back to a depth afterwards recovers a top that was never the top.
    # The whole chain, not just the reading at the top of it. Which tops the chain holds is
    # decided by comparing highs, and a payout moves highs -- the highest top can keep its date
    # and every one of its boundaries while the tops beneath it change places, and those are the
    # readings that decide whether a criterion is contested and whether the rejection stands.
    on_one_scale = _on_one_scale(history)
    reordered = False
    if on_one_scale is not None and measurements["peak_date"] is not None:
        first = measure_power_play(on_one_scale, spec)
        adjusted = _walk_the_tops(on_one_scale, spec, first)
        reordered = _signature(walk) != _signature(adjusted)
    if reordered:
        contested = set(primary_criteria)
    # Three states, because a reading nobody could read is not a reading that came through. A
    # span holding a corporate action was not measured on one coordinate system, so it rejects
    # nothing -- and folding it into the survivors reports the structure as intact under every
    # reading, then sends the reader to the chart to settle a top when what needs settling is the
    # split.
    surviving: list[str] = []
    unreadable: list[str] = []
    reading_rejections: list[dict[str, Any]] = []
    for criteria, reading in zip(every_criteria, readings):
        if not _unmoved(reading):
            unreadable.append(reading["peak_date"])
        elif reading_rejects(criteria, corporate_action_unmoved=True):
            reading_rejections.append(
                {
                    "peak_date": reading["peak_date"],
                    # `failed` carries only the criteria every reading agreed on, so a rejection
                    # the readings reached by different routes would otherwise arrive as a verdict
                    # with nothing behind it -- a state no signal explains. The one criterion left
                    # out is the flag that has not finished: the reducer calls it unfinished, and
                    # one envelope cannot call it a failure on the line below.
                    "failed": [
                        f"{_CLAIM}.{condition}"
                        for condition, state in criteria.items()
                        if state == "fail" and f"{_CLAIM}.{condition}" != FLAG_STILL_FORMING
                    ],
                }
            )
        else:
            surviving.append(reading["peak_date"])

    # A rejection every top agrees on is a rejection whichever of them the search landed on.
    #
    # "Every top read", not "every reading": the chain stops at the registered distance, so tops
    # beyond it were never taken and cannot have agreed to anything. `readings_cut_at` names the
    # first of them. Left at the two nearest tops this claimed all of them and was wrong in its
    # own name -- two ticks a hundredth of a percent apart hide a structure behind them -- and a
    # count-truncated chain has the same problem for a different reason.
    # Every top in the span, read and rejecting. Nothing weaker will do: a top nobody could read
    # has not consented to a rejection by being silent, and a top the distance excluded from
    # contesting is still a reading under which the structure stands. And a chain that read the
    # dividend's ordering read the wrong tops, so agreement among them is agreement about nothing.
    every_top_rejects = (
        bool(readings)
        and not exhausted
        and not reordered
        and not surviving
        and not unreadable
        # A lower top the loaded history cannot reach behind is still a top nobody read.
        and not ran_out_of_history
    )
    rejected_under_every_top_read = every_top_rejects and bool(contested)

    signals = [
        # The close-to-close reading, because the criterion is about the stock's price rather
        # than about the widest pair of prints inside two sessions. Read on the extremes, a single
        # intraday wick to half the peak reported a hundred and four percent advance on a stock
        # whose close moved half a percent. The extremes reading travels in the measurements.
        doctrine.evaluate_gate(_CLAIM, "advance_minimum_pct", measurements["advance_pct_closes"]),
        doctrine.evaluate_gate(_CLAIM, "advance_maximum_weeks", measurements["advance_weeks"]),
        doctrine.evaluate_gate(_CLAIM, "flag_minimum_sessions", measurements["flag_sessions"]),
        doctrine.evaluate_gate(_CLAIM, "flag_maximum_weeks", measurements["flag_weeks"]),
        doctrine.evaluate_gate(_CLAIM, "flag_maximum_decline_gate_pct", measurements["flag_depth_pct"]),
        doctrine.evaluate_band(_CLAIM, "flag_duration_weeks", measurements["flag_weeks"]),
        doctrine.evaluate_band(_CLAIM, "flag_maximum_decline_pct", measurements["flag_depth_pct"]),
        _observation(
            "launch_volume_character",
            _volume_state(measurements["advance_peak_volume_ratio"]),
            {
                "advance_peak_volume_ratio": measurements["advance_peak_volume_ratio"],
                "advance_peak_volume_date": measurements["advance_peak_volume_date"],
                "launch_volume_ratio": measurements["launch_volume_ratio"],
                "advance_volume_ratio": measurements["advance_volume_ratio"],
            },
            "the advance commences on huge volume",
        ),
        _observation(
            "flag_tightness_or_vcp",
            _tightness_state(measurements["flag_depth_pct"], tight_limit),
            {"flag_depth_pct": measurements["flag_depth_pct"], "tight_action_maximum_pct": tight_limit},
            f"the flag corrects no more than {tight_limit} percent, or shows VCP characteristics",
        ),
    ]
    return {
        "structure": {
            "state": "unavailable" if measurements["rejection"] else "measured",
            "rejection": measurements["rejection"],
        },
        "peak_identity": "disputed" if contested else "settled",
        "readings": len(readings),
        "readings_exhausted": exhausted,
        "readings_cut_at": cut_at,
        "surviving_readings": surviving,
        "unreadable_readings": unreadable,
        "readings_ran_out_of_history": ran_out_of_history,
        "reading_rejections": reading_rejections,
        "rejected_under_every_top_read": rejected_under_every_top_read,
        "every_top_rejects": every_top_rejects,
        # Which criteria the choice of top actually moved. The reducer reads this rather than the
        # summary word, because agreeing on the verdict is not agreeing on every criterion: two
        # readings can both reject and still disagree about which limit did it, and reporting the
        # primary reading's version of that as a confident failure is a finding about the search.
        "contested_criteria": sorted(contested),
        "payout_sensitive_criteria": sorted(payout_sensitive),
        # Separate from the signals because it is a fact about the input rather than about the
        # stock: a history that does not carry the event column has not reported "no split".
        "corporate_action_evidence": measurements["corporate_action_evidence"],
        # Surfaced beside the split events rather than left in the payload: a payout that decided
        # a criterion is the reason that criterion stopped deciding, and the reader is owed it.
        "distribution_evidence": measurements["distribution_evidence"],
        "distribution_sessions": measurements["distribution_sessions"],
        "corporate_action_sessions": actions,
        "spec": spec,
        "measurements": measurements,
        "signals": signals,
    }


__all__ = ["build_power_play_evidence", "compile_power_play_spec"]
