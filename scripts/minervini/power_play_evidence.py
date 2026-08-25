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

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from . import doctrine
from .setup_structure import (
    _CORPORATE_ACTION_COLUMN,
    _DISTRIBUTION_COLUMN,
    bars_fingerprint,
    read_bars,
)
from .power_play import FLAG_STILL_FORMING, measure_power_play, reading_rejects
from .swings import _typical_range_pct, segment


_CLAIM = "fundamentals.power_play_exception"
_WEEK = "convention.trading_week"
_TOPS = "convention.power_play_top_candidates"
_SEGMENTATION = "setup.swing_segmentation_convention"
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


def _observation(
    condition: str, state: str, measured: Any, required: str, *, read_from_chart: bool = False
) -> dict[str, Any]:
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
        # A verdict a person supplied must never read like one the numbers reached. This is the
        # only channel in the capability through which a human sentence becomes a machine `pass`,
        # so an auditor of a qualified Power Play has to be able to see it on the signal itself.
        "read_from_chart": read_from_chart,
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


# What a reading says when it has declined to answer rather than disagreed. Two readings of the
# same bars can only dispute a criterion by both answering it: a payout that decided one of them
# withdrew that answer, and a chart nobody has read never gave one.
_ABSTAINS = ("unavailable", "needs_chart")
# What a contesting reading did instead of agreeing, strongest first. The order is the precedence:
# a reading that gave a different answer has disputed the criterion whatever the others did, and
# only where nobody disputed it does the question become which kind of silence is holding it.
_DISAGREEMENTS = ("dissent", "payout", "chart")


def _how_the_tops_disagree(
    primary: Mapping[str, str], contesting: Sequence[Mapping[str, str]]
) -> dict[str, str]:
    """Per criterion, whether a top that may contest it failed to agree, and why.

    Qualification is every contesting reading affirmatively agreeing, never an absence of
    objections -- the same rule the required-evidence lists are built on. Read as "nobody
    objected", a reading that abstained counts as agreement, and the criterion closes on the
    strength of a top whose answer the dividend withdrew or whose chart nobody opened.

    So the three ways of not agreeing are separated rather than pooled, because each closes on a
    different action: another reading of the tops, the dividend calendar, or a chart.
    """
    disagreement: dict[str, str] = {}
    for condition, answer in primary.items():
        # The primary's own gap already blocks this criterion under its own name, and comparing
        # an abstention with anything says nothing about the tops.
        if answer in _ABSTAINS:
            continue
        causes = {
            "payout" if state == "unavailable" else "chart" if state == "needs_chart" else "dissent"
            for state in (criteria[condition] for criteria in contesting)
            if state != answer
        }
        for cause in _DISAGREEMENTS:
            if cause in causes:
                disagreement[condition] = cause
                break
    return disagreement


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
    """Everything about one walk of the tops that a distribution could have chosen.

    Structure only. Whether the two scales agree about the *answers* is asked separately, per
    criterion, because a payout that moves one gate has not made the whole reading unusable -- and
    a payout that moves the structure has.
    """
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


def _decided_by_the_payout(
    walk: Mapping[str, Any], adjusted: Mapping[str, Any], tight_limit: float
) -> list[set[str]]:
    """Which criteria answer differently once every print is on one scale.

    Paired reading by reading, because the tops sit at different sessions and a longer flag holds
    payouts a shorter one never saw -- left to the top reading alone, an earlier candidate could
    reject on a depth its own payout manufactured and cast that into "every top rejects". The
    pairing is sound only where the structures matched, which is what the boundary signature has
    already established by the time this runs.

    One coordinate system, not two. An earlier version added the cash back to the flag's low and
    to the peak's close while this series takes it off the prints before the ex-date, and the two
    disagreed about the very percentages they were correcting.
    """
    return [
        {
            condition
            for condition, state in _criteria(reading, tight_limit).items()
            if _criteria(other, tight_limit)[condition] != state
        }
        for reading, other in zip(walk["readings"], adjusted["readings"])
    ]


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


def power_play_fingerprint(history: Any) -> str | None:
    """One digest of the bars *and* the events this capability reads.

    The shared bars fingerprint covers the five price columns, which is right for the surfaces
    that share a chain: they measure price. This one also measures events -- a split inside the
    span leaves it deciding nothing, a payout inside it withholds the criteria it decided -- so
    two histories with identical prices and different events are different inputs here and must
    not digest the same. An approval bound to a digest that cannot see the split would not be
    bound to the evidence the verdict turned on.

    Returns None where the event columns are absent, because a history that never said whether a
    split occurred is not a history that said none did. Digesting the absence as zeroes is the
    substitution the reducer already refuses to make when it decides.
    """

    bars, _ = read_bars(history)
    if bars is None or bars.empty:
        return None
    if not {_CORPORATE_ACTION_COLUMN, _DISTRIBUTION_COLUMN}.issubset(bars.columns):
        return None
    events = json.dumps(
        {
            "bars": bars_fingerprint(bars),
            "events": [
                {
                    "date": stamp.date().isoformat(),
                    _CORPORATE_ACTION_COLUMN: float(row[_CORPORATE_ACTION_COLUMN]),
                    _DISTRIBUTION_COLUMN: float(row[_DISTRIBUTION_COLUMN]),
                }
                for stamp, row in bars.iterrows()
                if float(row[_CORPORATE_ACTION_COLUMN]) or float(row[_DISTRIBUTION_COLUMN])
            ],
        },
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    )
    return hashlib.sha256(events.encode("utf-8")).hexdigest()


# The two criteria the source states without a magnitude, and the measurement each one turns on.
# The measurement is in the key because it is what the reader was looking at: a chart approved at
# a nine percent flag is not an approval of the same flag re-measured at eleven.
_CHART_CONDITIONS = {
    "launch_volume_character": "advance_peak_volume_ratio",
    "flag_tightness_or_vcp": "flag_depth_pct",
}
# Two words, not three. "I looked and could not tell" leaves the criterion exactly where a reader
# who never looked leaves it, so a third word would buy a different gap reason and nothing else;
# a reader who cannot tell supplies no approval and the envelope goes on asking.
_CHART_ANSWERS = {"observed": "pass", "absent": "fail"}
# The vocabulary itself, for the request boundary. Read from the same dict the answers are
# applied from, so the words a caller may spell cannot drift from the words that do anything.
CHART_READING_WORDS = tuple(_CHART_ANSWERS)
# Long enough that "a key names one question" is a fact rather than a probability. The key is
# copied, never typed, so the extra characters cost a caller nothing.
_CHART_KEY_LENGTH = 32


def _chart_key(fingerprint: str, condition: str, reading: Mapping[str, Any]) -> str:
    """The name of one question, which is everything answering it would have to be about.

    A key is issued rather than assembled by the caller, so an approval cannot be partly right.
    Echoing four fields lets a caller match the ones they kept and miss the one that moved; a
    digest either is the question that was asked or is not.
    """
    payload = json.dumps(
        {
            "measured_bars": fingerprint,
            "condition": condition,
            "boundaries": {name: reading[name] for name in _BOUNDARIES},
            "measured": reading[_CHART_CONDITIONS[condition]],
        },
        separators=(",", ":"),
        sort_keys=True,
        default=str,
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:_CHART_KEY_LENGTH]


def _turning_points(history: Any) -> frozenset[str] | None:
    """The highs the segmentation this harness already owns calls turning points.

    A candidate top is a high price has since fallen away from, which is what the detector
    confirms and what a reader would draw on the chart. Every descending high is a weaker thing
    entirely: inside a flag it includes the bar that printed a hundredth of a percent above the
    last one, and reading the structure from there is reading a bar rather than a top.

    The retracement is derived the way ticker.swings derives it, from the same registered
    convention, so both capabilities cut the same bars at the same places. What is not borrowed is
    that capability's refusal to vouch when a neighbouring parameter would move an anchor: it
    exists to corroborate a chain a caller declared, and here the disagreement is reported as a
    disputed top rather than as no reading at all.
    """

    bars, _ = read_bars(history)
    typical = _typical_range_pct(bars)
    if typical is None:
        return None
    multiple = float(doctrine.parameter(_SEGMENTATION, "retracement_range_multiple"))
    anchors = segment(bars, retracement_pct=multiple * typical)["anchors"]
    return frozenset(str(anchor["date"]) for anchor in anchors if anchor["kind"] == "high")


def _walk_the_tops(
    history: Any, spec: Mapping[str, Any], first: Mapping[str, Any], turning_points: frozenset[str] | None = None
) -> dict[str, Any]:
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
    first_non_contesting: dict[str, Any] | None = None
    ran_out_of_history = False
    unread_may_contest = False
    may_contest = 0
    steps = 0
    while len(readings) < _MOST_TOPS_READ and steps < _MOST_TOPS_READ:
        steps += 1
        reading = first if not readings else measure_power_play(history, spec, below=below, before=before)
        if reading["rejection"] is not None:
            # One refusal means the opposite of the others. `_NO_MORE_TOPS` is the chain ending;
            # anything else is a top that exists with too little history behind it to measure --
            # a gap, and treating it as the chain ending turns it into a silent vote for whatever
            # the tops above it decided. That is the shape a recently listed stock arrives in.
            if reading["rejection"] != _NO_MORE_TOPS:
                ran_out_of_history = True
                # How far below the highest that unread top stands, when the measurement got far
                # enough to find it. Objecting to a rejection survives the distance -- a structure
                # nobody read is still one nobody read -- so `ran_out_of_history` alone withholds
                # a rejection whatever the distance is. Contesting does not survive it, so this is
                # what decides whether the same top can withhold a qualification. Unknown counts
                # as close: a top whose price the measurement never established could be anywhere.
                unread = reading["peak_high"]
                unread_may_contest = (
                    top is None or unread is None or (top - unread) / top * 100 <= bound
                )
            break
        # Walked past rather than read. The bar is still where the next search starts from -- the
        # tops below it are found by descending -- but it is not a reading of the structure, so it
        # neither contests a criterion nor has to consent to a rejection.
        if readings and turning_points is not None and str(reading["peak_date"]) not in turning_points:
            below, before = reading["peak_high"], reading["peak_date"]
            continue
        distance = None if top is None else (top - reading["peak_high"]) / top * 100
        if distance is not None and distance > bound:
            if first_non_contesting is None:
                first_non_contesting = {"peak_date": reading["peak_date"], "distance_pct": distance}
        else:
            may_contest = len(readings) + 1
        readings.append(reading)
        below, before = reading["peak_high"], reading["peak_date"]
    return {
        "readings": readings,
        "first_non_contesting": first_non_contesting,
        "ran_out_of_history": ran_out_of_history,
        "unread_top_may_contest": unread_may_contest,
        "may_contest": may_contest,
    }


def build_power_play_evidence(
    history: Any, chart_readings: Mapping[str, str] | None = None, drawn_bars: str | None = None
) -> dict[str, Any]:
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

    walk = _walk_the_tops(history, spec, measurements, _turning_points(history))
    readings, first_non_contesting = walk["readings"], walk["first_non_contesting"]
    ran_out_of_history, may_contest = walk["ran_out_of_history"], walk["may_contest"]
    unread_top_may_contest = walk["unread_top_may_contest"]
    exhausted = len(readings) >= _MOST_TOPS_READ

    # The ordering first. If the tops keep their places once every print is on one scale, the
    # search read the stock; if they do not, it read the dividend, and nothing measured against
    # those boundaries recovers a top that was never the top.
    #
    # The whole chain, not just the reading at the top of it. Which tops the chain holds is
    # decided by comparing highs, and a payout moves highs -- the highest top can keep its date
    # and every one of its boundaries while the tops beneath it change places, and those are the
    # readings that decide whether a criterion is contested and whether the rejection stands.
    on_one_scale = _on_one_scale(history)
    adjusted: dict[str, Any] | None = None
    reordered = False
    if on_one_scale is not None and measurements["peak_date"] is not None:
        adjusted = _walk_the_tops(
            on_one_scale, spec, measure_power_play(on_one_scale, spec), _turning_points(on_one_scale)
        )
        reordered = _signature(walk) != _signature(adjusted)

    # Then which criteria the payout decided, paired reading by reading against that same scale.
    # Structure surviving does not make the answers survive with it: the payout comes out of the
    # prints between the anchor and the peak, so ninety-eight and a half percent on the tape is a
    # hundred and a half on one scale, every boundary matches, and which side of the limit that
    # lands on is the whole verdict.
    # Per reading, not pooled across the chain. The tops sit at different sessions, so a payout a
    # longer flag held is one a shorter one never saw -- and pooling withholds the top reading's
    # own confident failure over a limit some lower candidate happened to sit on.
    every_payout_sensitive: list[set[str]] = [set() for _ in readings]
    if adjusted is not None and not reordered:
        every_payout_sensitive = _decided_by_the_payout(walk, adjusted, tight_limit)
    payout_sensitive = every_payout_sensitive[0] if readings else set()

    every_criteria = [
        {
            condition: "unavailable" if condition in decided else state
            for condition, state in _criteria(reading, tight_limit).items()
        }
        for reading, decided in zip(readings, every_payout_sensitive)
    ]

    # Then the two questions the bars decline to answer, offered to a reader and taken back.
    #
    # Per reading, because both questions are asked about a span the top decides: for a lower top
    # the advance starts elsewhere and the flag is longer, so it is a different chart and gets its
    # own key. A caller who wants a criterion settled has to answer every top that may contest it,
    # which is the honest cost of two candidate structures rather than a gap in the seam.
    #
    # No key at all where the reading is not the stock's own. While a split stands in the span the
    # measurements are arithmetic about the action, and while the tops read the dividend's
    # ordering the search found the wrong top -- asking a reader to corroborate either is asking
    # them to confirm something that never happened.
    # Both surfaces read the same sentence: the question offered to a reader and the requirement
    # reported beside the answer have to be the criterion, not two paraphrases of it.
    asks = {
        "launch_volume_character": "the advance commences on huge volume",
        "flag_tightness_or_vcp": (
            f"the flag corrects no more than {tight_limit} percent, or shows VCP characteristics"
        ),
    }
    given = dict(chart_readings or {})
    fingerprint = power_play_fingerprint(history)
    # Which picture the reader looked at, in the form ticker.chart prints it. The key already
    # binds an answer to the bars this verdict is measured on; what it cannot do is attest that
    # the chart came from those bars, and the two capabilities reach the provider through their
    # own cache entry, so one can be drawn from a vintage the other never measured. Answered
    # anyway, the eyes corroborated one series and the machine qualified another.
    #
    # A mismatch withholds rather than refuses. The caller answered honestly about a picture that
    # existed; it is the wrong picture for this reading, which is a gap and not a bad request --
    # the same call a setup approval of another vintage gets.
    measured_from = bars_fingerprint(read_bars(history)[0])
    covers_other_bars = bool(given) and drawn_bars != measured_from
    if covers_other_bars:
        given = {}
    chart_questions: list[dict[str, Any]] = []
    answered: list[dict[str, str]] = [{} for _ in readings]
    for index, (criteria, reading) in enumerate(zip(every_criteria, readings)):
        if fingerprint is None or reordered or not _unmoved(reading):
            continue
        # Nor for a reading the bars already threw out. A visual opinion never overturns a
        # deterministic failure, so a key here would send a reader to draw a picture, come back
        # with an answer, and find the verdict exactly where they left it.
        if reading_rejects(criteria, corporate_action_unmoved=True):
            continue
        for condition, measured in _CHART_CONDITIONS.items():
            if criteria[condition] != "needs_chart":
                continue
            key = _chart_key(fingerprint, condition, reading)
            answer = given.get(key)
            chart_questions.append(
                {
                    "key": key,
                    "condition": condition,
                    "reading": index,
                    "measured_bars": fingerprint,
                    # The digest to compare against the chart's manifest, so a reader can see in
                    # one string whether the picture in front of them is this reading's.
                    "drawn_bars": measured_from,
                    "peak_date": reading["peak_date"],
                    "advance_anchor_date": reading["advance_anchor_date"],
                    "flag_low_date": reading["flag_low_date"],
                    "measured": {measured: reading[measured]},
                    "asks": asks[condition],
                    "answered": answer,
                }
            )
            if answer is not None:
                criteria[condition] = _CHART_ANSWERS[answer]
                answered[index][condition] = criteria[condition]
    # Refused rather than dropped. The ordinary way an approval goes stale is a session closing
    # between the chart and the request, and a caller told nothing would read the unchanged
    # `incomplete` as the harness ignoring them rather than as their answer not applying.
    unmatched = sorted(set(given) - {question["key"] for question in chart_questions})

    primary_criteria = every_criteria[0] if readings else _criteria(measurements, tight_limit)
    primary_answered = answered[0] if readings else {}
    # A reading whose answer the payout decided abstains rather than dissents. It has not disputed
    # the top reading's answer; it has declined to give one, and counting that as disagreement
    # sends the reader to the chart to settle a top when the dividend calendar is what moved.
    # Three buckets rather than one, because a criterion the highest top answered can be held open
    # by a top that disputed it, by a top whose answer the dividend decided, or by a top whose
    # chart nobody has read -- and a reader sent to settle the wrong one has not settled anything.
    disagreement = _how_the_tops_disagree(primary_criteria, every_criteria[1:may_contest])
    contested = {condition for condition, cause in disagreement.items() if cause == "dissent"}
    payout_elsewhere = {condition for condition, cause in disagreement.items() if cause == "payout"}
    awaiting_elsewhere = {condition for condition, cause in disagreement.items() if cause == "chart"}
    if reordered:
        contested = set(primary_criteria)
        payout_elsewhere = set()
        awaiting_elsewhere = set()
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
    # Every top rejected and no one criterion carries it, so there is nothing trustworthy to name:
    # reporting the highest top's list would name limits the others say were never exceeded. This
    # explains a rejection rather than reaching one -- `every_top_rejects` is the rejection, and a
    # criterion every reading failed is named through the reducer's own `failed` list.
    #
    # It used to be `every_top_rejects and bool(contested)`, which read "the tops disagree about
    # which limit did it" off the contested set. That proxy broke the moment an unanswered chart
    # stopped counting as disagreement: two tops that each reject on their own `absent` reading
    # agree about nothing and contest nothing, and the composite rejection vanished.
    rejected_under_every_top_read = every_top_rejects and not any(
        all(criteria[condition] == "fail" for criteria in every_criteria)
        for condition in primary_criteria
        if f"{_CLAIM}.{condition}" != FLAG_STILL_FORMING
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
            primary_answered.get("launch_volume_character", _volume_state(measurements["advance_peak_volume_ratio"])),
            {
                "advance_peak_volume_ratio": measurements["advance_peak_volume_ratio"],
                "advance_peak_volume_date": measurements["advance_peak_volume_date"],
                "launch_volume_ratio": measurements["launch_volume_ratio"],
                "advance_volume_ratio": measurements["advance_volume_ratio"],
            },
            asks["launch_volume_character"],
            read_from_chart="launch_volume_character" in primary_answered,
        ),
        _observation(
            "flag_tightness_or_vcp",
            primary_answered.get("flag_tightness_or_vcp", _tightness_state(measurements["flag_depth_pct"], tight_limit)),
            {"flag_depth_pct": measurements["flag_depth_pct"], "tight_action_maximum_pct": tight_limit},
            asks["flag_tightness_or_vcp"],
            read_from_chart="flag_tightness_or_vcp" in primary_answered,
        ),
    ]
    return {
        # The name of the input this verdict was reached on, prices and events together, so an
        # approval can be bound to it and a later reader can tell a rule change from a data one.
        "measured_bars": fingerprint,
        # The price digest of the same bars, in the form ticker.chart prints it, so the picture a
        # reader looked at and the bars this verdict was measured on can be compared in one string.
        "measured_from": measured_from,
        "readings_cover_other_bars": covers_other_bars,
        # What this run is still asking a reader, and what the reader would be answering about.
        # Issued rather than assembled: a key names one criterion under one reading of the tops,
        # measured off one set of bars, at one value -- and stops naming it the moment any of
        # those move.
        "chart_questions": chart_questions,
        "unmatched_chart_readings": unmatched,
        "structure": {
            "state": "unavailable" if measurements["rejection"] else "measured",
            "rejection": measurements["rejection"],
        },
        "peak_identity": "disputed" if contested else "settled",
        "readings": len(readings),
        "readings_exhausted": exhausted,
        "first_non_contesting_reading": first_non_contesting,
        "surviving_readings": surviving,
        "unreadable_readings": unreadable,
        "readings_ran_out_of_history": ran_out_of_history,
        "unread_top_may_contest": unread_top_may_contest,
        "reading_rejections": reading_rejections,
        "rejected_under_every_top_read": rejected_under_every_top_read,
        "every_top_rejects": every_top_rejects,
        # Which criteria the choice of top actually moved. The reducer reads this rather than the
        # summary word, because agreeing on the verdict is not agreeing on every criterion: two
        # readings can both reject and still disagree about which limit did it, and reporting the
        # primary reading's version of that as a confident failure is a finding about the search.
        "contested_criteria": sorted(contested),
        # Separate from the contested set because each closes on a different action.
        "awaiting_chart_under_another_top": sorted(awaiting_elsewhere),
        "payout_decided_under_another_top": sorted(payout_elsewhere),
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


__all__ = [
    "CHART_READING_WORDS",
    "build_power_play_evidence",
    "compile_power_play_spec",
    "power_play_fingerprint",
]
