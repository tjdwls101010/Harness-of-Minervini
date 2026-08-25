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
from .power_play import FLAG_STILL_FORMING, measure_power_play, reading_rejects


_CLAIM = "fundamentals.power_play_exception"
_WEEK = "convention.trading_week"
# A runaway guard, not a doctrine limit: the longest chain any cached history produced was
# nineteen tops. Hitting it is reported, never silently truncated into an agreement.
_MOST_TOPS_READ = 200


def compile_power_play_spec() -> dict[str, Any]:
    """The two search windows, in completed sessions."""

    week = int(doctrine.parameter(_WEEK, "sessions_per_trading_week"))
    return {
        "advance_window_sessions": int(doctrine.threshold(_CLAIM, "advance_maximum_weeks")) * week,
        "flag_window_sessions": int(doctrine.threshold(_CLAIM, "flag_maximum_weeks")) * week,
        # Carried rather than re-derived, so the module that reports durations in weeks converts
        # them the same way the windows were compiled.
        "sessions_per_trading_week": week,
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
    )


def build_power_play_evidence(history: Any) -> dict[str, Any]:
    """Measure a history and read the criteria against it, deciding nothing.

    The structure is found rather than declared, so the same bars are read from every top the
    search could have landed on: the highest of the span, then the highest below that, and down
    until the span holds no more. The source names no size below which a new high stops counting
    -- a hundredth of a percent above the last high restarts the flag and turns thirty sessions
    into four -- so a criterion decides only where every reading answers it the same way, and a
    rejection stands only where every reading reaches one.

    Two readings were not enough, and the shortfall was not theoretical: two ticks a hundredth of
    a percent apart inside one flag hand the search three tops, and both of the first two reject
    while the structure they sit inside has nothing decisive against it. Across every cached
    history the chain runs one to nineteen tops, and twenty-two of twenty-three still reject on a
    criterion every reading agreed on.
    """

    spec = compile_power_play_spec()
    tight_limit = float(doctrine.threshold(_CLAIM, "tight_action_maximum_pct"))
    measurements = measure_power_play(history, spec)
    actions = measurements["corporate_action_sessions"]

    readings: list[dict[str, Any]] = []
    below, before = None, None
    top = measurements["peak_high"]
    # Bounded twice. By price, because a top the stock later exceeded by more than the tightness
    # this criterion itself allows was overtaken rather than consolidated against: the flag
    # hanging from it contains sessions outside the range the criterion describes, so it is not a
    # competing reading of this structure but a different, older one. Unbounded, the chain walks
    # one bar at a time down an ordinary advance and every criterion ends up contested by a bar
    # nobody would call a top -- measured across the cached histories, the bound takes the chains
    # from one-to-nineteen readings down to one-to-fifteen and raises the tickers still rejecting
    # on a named, agreed criterion from twenty-two of twenty-three to all of them.
    #
    # And by count, so a pathological history cannot spin here. Reaching that bound is reported
    # rather than passed over as agreement.
    while len(readings) < _MOST_TOPS_READ:
        reading = measurements if not readings else measure_power_play(history, spec, below=below, before=before)
        if reading["rejection"] is not None:
            break
        if top is not None and (top - reading["peak_high"]) / top * 100 > tight_limit:
            break
        readings.append(reading)
        below, before = reading["peak_high"], reading["peak_date"]
    exhausted = len(readings) >= _MOST_TOPS_READ

    # Which criteria a cash payout inside the span decided. Everything else it touched, it did
    # not decide, and an ordinary quarterly payment touches nearly nothing against these limits.
    every_criteria, every_payout_sensitive = map(
        list, zip(*(_read_criteria(reading, tight_limit) for reading in readings))
    ) if readings else ([], [])
    primary_criteria, payout_sensitive = (
        (every_criteria[0], every_payout_sensitive[0])
        if readings
        else _read_criteria(measurements, tight_limit)
    )
    contested = {
        condition
        for condition in primary_criteria
        if any(criteria[condition] != primary_criteria[condition] for criteria in every_criteria)
    }
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

    # A rejection every top agrees on is a rejection whichever top the search landed on. Left at
    # the two nearest tops it was not "every reading" at all, and it said so in its own name.
    # A truncated chain has readings nobody took, so it cannot claim they agreed.
    rejected_under_every_reading = (
        bool(contested) and not exhausted and bool(readings) and not surviving and not unreadable
    )

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
        "surviving_readings": surviving,
        "unreadable_readings": unreadable,
        "reading_rejections": reading_rejections,
        "rejected_under_every_reading": rejected_under_every_reading,
        # Which criteria the choice of top actually moved. The reducer reads this rather than the
        # summary word, because agreeing on the verdict is not agreeing on every criterion: two
        # readings can both reject and still disagree about which limit did it, and reporting the
        # primary reading's version of that as a confident failure is a finding about the search.
        "contested_criteria": sorted(contested),
        "payout_sensitive_criteria": sorted(payout_sensitive),
        "alternate_peak": None if len(readings) < 2 else {
            "peak_date": readings[1]["peak_date"],
            "peak_high": readings[1]["peak_high"],
            "flag_sessions": readings[1]["flag_sessions"],
            "flag_depth_pct": readings[1]["flag_depth_pct"],
            "advance_pct_closes": readings[1]["advance_pct_closes"],
        },
        # Separate from the signals because it is a fact about the input rather than about the
        # stock: a history that does not carry the event column has not reported "no split".
        "corporate_action_evidence": measurements["corporate_action_evidence"],
        # Surfaced beside the split events rather than left in the payload: a payout that decided
        # a criterion is the reason that criterion stopped deciding, and the reader is owed it.
        "distribution_sessions": measurements["distribution_sessions"],
        "corporate_action_sessions": actions,
        "spec": spec,
        "measurements": measurements,
        "signals": signals,
    }


__all__ = ["build_power_play_evidence", "compile_power_play_spec"]
