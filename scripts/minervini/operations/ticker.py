"""Price eligibility and setup evidence composition."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any, Mapping
from ..contracts import RequestError, envelope
from ..eligibility import EligibilityEvidence, evaluate_eligibility
from ..providers import ProviderUnavailable
from ..power_play import FLAG_STILL_FORMING, evaluate_power_play
from ..power_play_evidence import CHART_READING_WORDS, build_power_play_evidence
from ..runtime import Runtime
from ..setup import evaluate_setup
from ..swings import canonical_chain
from ..setup_evidence import build_setup_evidence
from ..setup_structure import read_bars
from ..technical import build_eligibility_evidence

from . import PriceRead, _as_of, _cached_provider, _clean_request, _clock, _missing_provider, _price_read, _reducer_named_doctrine_ids, _source, _ticker


def _qualify(request: Mapping[str, Any], runtime: Runtime) -> dict[str, Any]:
    ticker = _ticker(request.get("ticker"))
    clock = _clock(request.get("as_of"))
    requested_as_of = clock.date.isoformat()
    prices, gap, sources = _price_read(
        runtime, request, clock, ticker, PriceRead("ticker.qualify", {"eligibility_state": "incomplete"}, next_capabilities=[], partial_extra=lambda meta: {"price_as_of": meta.as_of.isoformat() if meta.as_of else None})
    )
    if gap is not None:
        return gap
    # Through the reader that owns what a usable history is, so the hard gate measures the same
    # bars the chart renders and the setup re-cuts. Its own reading coerced the closes and
    # dropped what would not coerce, which is the laundering that reading exists to stop: a
    # boolean column became a flat price, a doubled session became two sessions, and a history
    # half of whose closes were holes was measured on the survivors -- 150 rows, below the 200
    # the standard route needs, so a gap in the data left through the exception for a stock too
    # young to have them.
    bars, rejection = read_bars(prices.data)
    if bars is None:
        return envelope(
            "ticker.qualify",
            request=_clean_request({**request, "ticker": ticker}),
            as_of=_as_of(clock),
            status="unavailable",
            data={"ticker": ticker, "eligibility_state": "incomplete"},
            missing=[{"id": "usable_daily_bars", "reason": rejection, "required": True}],
            sources=sources,
            next_capabilities=[],
        )
    missing: list[dict[str, Any]] = []
    rating: int | None = None
    rating_date: str | None = None
    try:
        rs = _cached_provider(
            runtime,
            request,
            clock,
            capability="ticker.qualify",
            provider="ibd-rs-rating",
            operation="rating",
            params={"ticker": ticker},
            fetch=lambda: runtime.rs_rating(ticker, requested_as_of),
        )
    except ProviderUnavailable as error:
        missing.append(_missing_provider(error))
    else:
        rating = int(rs.data["rating"])
        rating_date = str(rs.data["rating_date"])
        sources.append(_source(rs.meta))

    measured = build_eligibility_evidence(
        bars,
        rs_rating=rating,
        primary_base_quality=request.get("primary_base_quality"),
        primary_base_emergence=request.get("primary_base_emergence"),
        primary_base_long_correction=request.get("primary_base_long_correction"),
    )
    result = evaluate_eligibility(EligibilityEvidence.from_mapping(measured)).to_dict()
    # A criterion the harness could not measure is a gap, and the envelope's completeness is
    # what a caller reads to know there is one. Status was decided from provider gaps alone, so
    # a reading that measured seven criteria out of eight published `ok` with an empty `missing`
    # beside `eligibility_state: incomplete` -- the envelope contradicting its own payload.
    #
    # Only where the reading could not reach a verdict, though. The recent-IPO route exists for
    # a stock with too little history to have a 200-day average and qualifies it on a Primary
    # Base instead, so those criteria are unavailable by the route's own design; naming them
    # would make an envelope that qualified a stock and claimed required evidence was missing
    # in the same breath. A criterion nobody could measure is a gap where the verdict needed it.
    if result["eligibility_state"] == "incomplete":
        missing.extend(
            {"id": signal["id"], "reason": "criterion_not_measurable", "required": True}
            for signal in result["signals"]
            if signal.get("state") == "unavailable"
        )
    # A band the harness measured has to reach the caller, or the rule that every band
    # is reported with its range is prose nothing carries out.
    primary_base = measured.get("primary_base") or {}
    bands = {"primary_base.depth": primary_base["depth_band"]} if primary_base.get("depth_band") else {}
    next_capabilities = ["ticker.setup", "ticker.fundamentals"] if result["eligibility_state"] == "eligible" else []
    if result["eligibility_state"] == "incomplete" and result["route"] == "recent_ipo_primary_base":
        next_capabilities = ["ticker.chart"]
    return envelope(
        "ticker.qualify",
        request=_clean_request({**request, "ticker": ticker}),
        as_of=_as_of(clock),
        status="partial" if missing else "ok",
        data={
            "ticker": ticker,
            "route": result["route"],
            "eligibility_state": result["eligibility_state"],
            "completed_session_count": len(bars),
            "price_as_of": measured["as_of"],
            "rs_rating": rating,
            "rs_rating_date": rating_date,
            "bands": bands,
        },
        signals=result["signals"],
        missing=missing,
        sources=sources,
        doctrine_ids=result["doctrine_ids"],
        next_capabilities=next_capabilities,
    )


_SEGMENTATION_CONVENTION = "setup.swing_segmentation_convention"
_TRADING_WEEK_CONVENTION = "convention.trading_week"
_VOLUME_STATE_CONVENTION = "setup.volume_state_convention"
_CHAIN_COMPLETENESS = "setup.declared_chain_completeness"


_CHART_READING_CONVENTION = "convention.power_play_chart_reading"


def _chart_readings(request: Mapping[str, Any]) -> dict[str, str]:
    """What no amount of price history could make valid, checked before any is fetched.

    Written KEY=word rather than as an object, and parsed here rather than in the command line,
    so the shape a programmatic caller is held to is the shape the flag spells. The key itself is
    not checked here: only a run that has measured the bars knows which questions are open.
    """

    declarations = request.get("chart_readings")
    if declarations is None:
        return {}
    if isinstance(declarations, str) or not isinstance(declarations, Sequence):
        raise RequestError("chart_readings is a list of KEY=observed|absent readings", "chart_readings")
    readings: dict[str, str] = {}
    for declaration in declarations:
        key, separator, word = str(declaration).partition("=")
        key, word = key.strip(), word.strip().lower()
        if not separator or not key or not word:
            raise RequestError(
                "a chart reading is written KEY=observed|absent, using a key from chart_questions",
                "chart_readings",
            )
        if word not in CHART_READING_WORDS:
            raise RequestError(
                f"{key} needs one of {', '.join(CHART_READING_WORDS)} after the equals sign",
                "chart_readings",
            )
        # Two answers to one question is a contradiction, not a correction. Silently keeping the
        # last one picks a winner the caller never chose.
        if key in readings:
            raise RequestError(f"{key} was answered twice; a question takes one reading", "chart_readings")
        readings[key] = word
    return readings


def _chart_digest(
    request: Mapping[str, Any], name: str, required: bool, prints: str, describes: str, kind: str
) -> str | None:
    """One of the digests an answer names the picture by, checked before anything is applied.

    Required with an answer, the way approved_bars is required with a complete chain, and for the
    same reason: a chart reading is a reading of one picture, and the harness never sees it.

    And it has to be a digest rather than any non-empty string. Taken as written, a typo was a
    picture this run had not measured -- so a malformed value came back as an honest reading of
    another vintage, which is a finding about the stock rather than about the request.
    """

    value = request.get(name)
    if required and not (isinstance(value, str) and value.strip()):
        raise RequestError(
            f"{name} is required with chart_readings: name the bars {describes}, as ticker.chart "
            f"reports them in {prints} and every chart question carries them",
            name,
        )
    if value is None:
        return None
    # Accepted on the stripped value, so it has to be *used* stripped too. A padded digest
    # passing validation and then being compared raw is worse than a refusal: it reads as an
    # honest chart of another vintage, and the padding is invisible in the reported reason.
    value = str(value).strip()
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise RequestError(
            f"{name} is {kind}: sixty-four lowercase hex characters, as ticker.chart reports "
            f"it in {prints}",
            name,
        )
    return value


def _power_play(request: Mapping[str, Any], runtime: Runtime) -> dict[str, Any]:
    ticker = _ticker(request.get("ticker"))
    clock = _clock(request.get("as_of"))
    readings = _chart_readings(request)
    # Two digests, because the picture and the overlay drawn on it have different inputs. The
    # candles are the five price columns; the span is not, and a history with the same prices and
    # a different corporate-action column asks different questions -- reproduced as two questions
    # from here, no span at all on the chart, and `input_sha256` matching on both, which let an
    # answer read off a blank picture through to `qualified`.
    drawn_bars = _chart_digest(
        request,
        "drawn_bars",
        bool(readings),
        "input_sha256",
        "the chart was read from",
        "a bars_fingerprint",
    )
    measured_bars = _chart_digest(
        request,
        "measured_bars",
        bool(readings),
        "power_play.measured_bars",
        "the overlay was drawn from",
        "the digest the overlay was computed from",
    )
    prices, gap, _ = _price_read(
        runtime, request, clock, ticker, PriceRead("ticker.power-play", {"power_play_state": "incomplete"})
    )
    if gap is not None:
        return gap
    evidence = build_power_play_evidence(
        prices.data, chart_readings=readings, drawn_bars=drawn_bars, measured_bars=measured_bars
    )
    # Refused rather than dropped, and before the verdict is assembled. The ordinary way an
    # approval stops matching is a session closing between the chart and the request; a caller
    # told nothing would read the unchanged answer as the harness ignoring them.
    stale = evidence["unmatched_chart_readings"]
    if stale:
        raise RequestError(
            "no question here is named by "
            + ", ".join(stale)
            + " -- read chart_questions from this capability and answer a key it issued",
            "chart_readings",
        )
    verdict = evaluate_power_play(evidence)
    rejection = verdict["structure"].get("rejection")
    if rejection is not None:
        return envelope(
            "ticker.power-play",
            request=_clean_request({**request, "ticker": ticker}),
            as_of=_as_of(clock),
            status="unavailable",
            data={"ticker": ticker, "power_play_state": "incomplete"},
            missing=[{"id": "usable_daily_bars", "reason": rejection, "required": True}],
            sources=[_source(prices.meta)],
            doctrine_ids=["fundamentals.power_play_exception", "scope.data_integrity"],
        )
    # Each gap names its own cause. Wrapping them all as one reason -- the shape the fundamentals
    # operation still uses for filed evidence -- would report a chart reading nobody has made and
    # a history that cannot say whether a split happened as the same kind of absence.
    reasons = {
        "corporate_action_evidence": (
            "corporate_action_inside_the_measured_span"
            if verdict["corporate_action_sessions"]
            else "corporate_action_evidence_missing"
        ),
        "peak_identity": "peak_identity_disputed",
        "peak_confirmation": "peak_not_a_confirmed_turning_point",
        "distribution_evidence": "distribution_evidence_missing",
    }
    contested = {
        f"fundamentals.power_play_exception.{condition}"
        for condition in verdict["contested_criteria"]
    }
    payout_sensitive = {
        f"fundamentals.power_play_exception.{condition}"
        for condition in verdict["payout_sensitive_criteria"]
    }
    awaiting_elsewhere = {
        f"fundamentals.power_play_exception.{condition}"
        for condition in verdict["awaiting_chart_under_another_top"]
    }
    payout_elsewhere = {
        f"fundamentals.power_play_exception.{condition}"
        for condition in verdict["payout_decided_under_another_top"]
    }
    action_elsewhere = {
        f"fundamentals.power_play_exception.{condition}"
        for condition in verdict["corporate_action_under_another_top"]
    }
    rejected_elsewhere = {
        f"fundamentals.power_play_exception.{condition}"
        for condition in verdict["rejected_under_another_top"]
    }
    # While an action stands, no criterion here was measured on one coordinate system, so the
    # cause of every gap is the action rather than anything a reader could supply.
    unreadable = (
        verdict["corporate_action_evidence"] != "present"
        or verdict["corporate_action_sessions"]
        or verdict["distribution_evidence"] != "present"
    )

    # Which criteria this run is still asking a reader about. Answered questions come back in the
    # payload with their answer, so counting those too would leave the envelope asking forever --
    # it would name a key that comes back already answered, and the next run would say the same.
    # And a gap reported as waiting on a chart with no key to answer it is a contradiction one
    # line apart.
    awaited = {
        f"fundamentals.power_play_exception.{question['condition']}"
        for question in verdict["chart_questions"]
        if question["answered"] is None
    }
    # A rejection is finished. Whatever it left unsatisfied stays in the payload as the shape of
    # the rejection, but it is not evidence anybody still owes -- neither the reason nor the
    # required flag may read as an instruction.
    decided = verdict["power_play_state"] == "not_qualified"

    # An answer read from another vintage of the series. Nothing was applied, so every criterion
    # it would have closed is open under that cause rather than under the chart it still waits on.
    other_bars = verdict["readings_cover_other_bars"]

    def _reason(item: str) -> str:
        if item in reasons:
            return reasons[item]
        if unreadable:
            if verdict["corporate_action_evidence"] != "present":
                return "corporate_action_evidence_missing"
            if verdict["distribution_evidence"] != "present":
                return "distribution_evidence_missing"
            return "corporate_action_inside_the_measured_span"
        if item == "lower_top_left_unread":
            return "history_ends_before_lower_top"
        if item in set(verdict["held_by_short_history"]):
            return "history_ends_before_lower_top"
        if item in set(verdict["held_by_another_top"]):
            return "structure_stands_under_another_top"
        if item in payout_sensitive:
            return "distribution_inside_the_measured_span"
        if item in contested:
            return "peak_identity_disputed"
        # The highest top answered it and a top that may contest it has not been looked at. What
        # closes it is that top's chart, not settling which top the structure hangs from.
        if item in awaiting_elsewhere:
            return "chart_unread_under_another_top"
        if item in payout_elsewhere:
            return "distribution_under_another_top"
        # A top whose own span holds a corporate action. Reported as a chart nobody has opened, it
        # named a picture no key exists for and pointed the reader at ticker.chart for an answer
        # this capability would refuse.
        if item in action_elsewhere:
            return "corporate_action_under_another_top"
        # A top the bars already threw out. It was issued no key either, so a reader sent to draw
        # its chart would come back with an answer this capability refuses.
        if item in rejected_elsewhere:
            return "structure_rejected_under_another_top"
        # The one gap that closes by itself. Reported as a chart reading, it would be closed by
        # whatever approval seam answers the chart -- and a twelve-session minimum would have been
        # waived by a reading of the volume.
        if item == FLAG_STILL_FORMING:
            return "flag_still_forming"
        # Two ways a chart criterion stops being something a chart closes. The structure was
        # rejected -- by the bars, or by this caller's own `absent` reading of another criterion --
        # and nothing supplied now moves it. Or no key was issued for it, because the reading it
        # belongs to was already out when the questions were handed round.
        #
        # Ahead of the vintage, because a rejection is not waiting on a picture of any vintage.
        # Read the other way round, a rejected structure answered from the wrong bars reported
        # every criterion as `approval_covers_different_bars` and sent a reader to redraw a chart
        # for a verdict that was finished -- the same mistake as reporting a still-forming flag
        # under the chart's name, one layer further out.
        if decided:
            return "structure_is_already_rejected"
        if other_bars:
            return "approval_covers_different_bars"
        if item not in awaited:
            return "reading_rejected_before_a_chart_was_needed"
        return "chart_reading_required"

    # `required` follows the verdict rather than the cause. Every gap keeps the reason that is
    # actually true of it -- a disputed peak on a rejected structure was still disputed -- but a
    # finished rejection owes nobody anything, and nine of twenty-three real tickers were coming
    # back `ok` with gaps marked required and no capability named to close them.
    #
    # And a criterion whose own reading is out owes nothing either, whatever the verdict does. No
    # key exists for it and none can, so it is unsatisfied evidence rather than evidence anybody
    # still has to supply -- which is what `required` has meant everywhere else in this harness.
    missing = [
        {
            "id": item,
            "reason": (reason := _reason(item)),
            "required": not decided and reason != "reading_rejected_before_a_chart_was_needed",
        }
        for item in verdict["missing"]
    ]
    # A rejection is finished, so it proposes nothing; an incomplete answer proposes a chart only
    # when a chart is what one of its gaps is actually waiting on.
    # Every gap a picture closes, because they are the same errand: read the highest top's chart,
    # read a contesting top's, or read the right vintage of either. Naming the capability for some
    # of them leaves a reader told to look at a chart with nowhere sent to draw it.
    awaits_a_chart = verdict["power_play_state"] == "incomplete" and any(
        item["reason"]
        in ("chart_reading_required", "chart_unread_under_another_top", "approval_covers_different_bars")
        for item in missing
    )
    return envelope(
        "ticker.power-play",
        request=_clean_request({**request, "ticker": ticker}),
        as_of=_as_of(clock),
        # The status is whether the evidence contract was satisfied; the state is the verdict.
        # A qualified Power Play has no gap left in it, so reporting it as `partial` would send
        # the reader looking for a missing piece that does not exist.
        status="partial" if verdict["power_play_state"] == "incomplete" else "ok",
        data={"ticker": ticker, **verdict},
        signals=verdict["signals"],
        missing=missing,
        sources=[_source(prices.meta)],
        # The two conventions belong here too: one converts every limit the source states in
        # weeks, the other decides where one reading of the structure stops and another begins.
        # Both move verdicts, so a reader auditing this one has to be able to reach them.
        doctrine_ids=[
            "fundamentals.power_play_exception",
            "convention.trading_week",
            "convention.power_play_top_candidates",
            # The candidates are the turning points that convention cuts, so the rule deciding
            # which highs count as tops is cited beside the one deciding how far down they argue.
            "setup.swing_segmentation_convention",
            # What a reading of the chart is bound to, and what it can never close. Cited on every
            # answer here, because a reader auditing a qualified verdict has to be able to reach
            # the rule that let a human sentence become a machine pass.
            _CHART_READING_CONVENTION,
            "scope.data_integrity",
        ],
        next_capabilities=["ticker.chart"] if awaits_a_chart else [],
    )


def _swings(request: Mapping[str, Any], runtime: Runtime) -> dict[str, Any]:
    ticker = _ticker(request.get("ticker"))
    clock = _clock(request.get("as_of"))
    prices, gap, _ = _price_read(
        runtime, request, clock, ticker, PriceRead("ticker.swings", {"state": "unavailable", "anchors": []})
    )
    if gap is not None:
        return gap
    chain = canonical_chain(prices.data)
    resolved = chain["state"] == "resolved"
    return envelope(
        "ticker.swings",
        request=_clean_request({**request, "ticker": ticker}),
        as_of=_as_of(clock),
        # Not needs_input: the parameters are deliberately out of the caller's reach, so there
        # is no argument that turns an unstable segmentation into a stable one. What is absent
        # is the evidence this capability exists to produce.
        status="ok" if resolved else "unavailable",
        data={"ticker": ticker, **chain},
        missing=[] if resolved else [{"id": "stable_segmentation", "reason": _segmentation_reason(chain), "required": True}],
        sources=[_source(prices.meta)],
        # The convention is the harness's; the boundary it bounds the base at is the source's.
        doctrine_ids=[_SEGMENTATION_CONVENTION, "setup.structural_pivot_and_trigger"],
        # A proposal is not an approval, and the chart is where a person turns one into the
        # other. With nothing proposed the chart draws no anchors, so pointing at it would send
        # a reader to a picture that cannot answer what they came for.
        next_capabilities=["ticker.chart"] if resolved else [],
    )


def _segmentation_reason(chain: Mapping[str, Any]) -> str:
    """Which of the ways a segmentation can fail this one failed.

    A chain that moves with the parameter and a chain with a session no daily bar can order
    are different problems, and a single reason word would hide which one a reader is looking
    at.
    """
    if chain.get("rejection"):
        return str(chain["rejection"])
    if chain.get("left_edge_disputed"):
        return "base_left_edge_ambiguous"
    if chain.get("ambiguous_sessions_in_base"):
        return "ambiguous_session_inside_the_base"
    if chain.get("sensitivity"):
        return "neighbouring_parameters_disagree"
    return "history_segments_into_no_base"


def _setup(request: Mapping[str, Any], runtime: Runtime) -> dict[str, Any]:
    ticker = _ticker(request.get("ticker"))
    clock = _clock(request.get("as_of"))
    # Before the provider, not after: a malformed request that reaches the network comes back as
    # a provider outage when the fault was the caller's, and pays for a fetch nobody can use.
    _refuse_unusable_setup_request(request)
    prices, gap, _ = _price_read(
        runtime, request, clock, ticker, PriceRead("ticker.setup", {"setup_state": "incomplete"})
    )
    if gap is not None:
        return gap
    swings = request.get("swing")
    entry = request.get("entry")
    evidence = build_setup_evidence(
        prices.data,
        swings or [],
        entry_kind=request.get("entry_kind") or "completed_pivot",
        tactic_opt_in=request.get("tactic_opt_in") is True,
        entry=entry,
        right_side_development=request.get("right_side_development"),
        chain_completeness=request.get("chain_completeness"),
        approved_bars=request.get("approved_bars"),
        entry_price=request.get("entry_price"),
        pivot_reset=request.get("pivot_reset"),
        entry_proximity=request.get("entry_proximity"),
    )
    result = evaluate_setup(evidence)
    # Two different questions, and they were being answered by one flag. Whether the verdict is
    # corroborated turns on the chain everything was measured off: a declared chain the detector
    # did not produce measures some other span, and one such chain reported an up/down volume
    # ratio of 0.08 where the base's own was 3.65, published as AVOID. Whether the caller can act
    # turns on something else entirely -- they can declare the detector's chain, and they cannot
    # make an unstable segmentation stable.
    corroborated = evidence["chain_corroborated"]
    unvouched = evidence["segmentation"].get("state") != "resolved"
    if not corroborated:
        # Every measurement was read off the declared chain, so a segmentation nothing vouched
        # for disqualifies what was measured from it -- a hard gate's failure included. Leaving
        # the reducer's AVOID in the payload while the envelope said unavailable published a
        # finding about the stock that rested on a data-integrity gap.
        # The reason travels with the state. Completeness failing lands in `unsatisfied` rather
        # than `missing`, so overriding the verdict without moving it left an incomplete answer
        # with nothing in it naming what was incomplete.
        missing_ids = [item for item in result["missing"] if item != _CHAIN_COMPLETENESS]
        result = {
            **result,
            "setup_state": "incomplete",
            "uncorroborated_verdict": result["setup_state"],
            "missing": [*missing_ids, _CHAIN_COMPLETENESS],
            "unsatisfied": [item for item in result["unsatisfied"] if item != _CHAIN_COMPLETENESS],
        }
    # A reading nobody declared and a reading nothing will corroborate are different absences.
    # The first is fixed by declaring one; the second is fixed by nothing the caller can type,
    # and reporting both as "evidence required" sends a reader looking for an argument.
    missing = [{"id": item, "reason": _missing_reason(item, evidence), "required": True} for item in result["missing"]]
    if unvouched:
        # The same gap ticker.swings calls unavailable, and for the same reason: the parameters
        # are out of the caller's reach and the chart draws no anchors for a chain the detector
        # refuses, so needs_input named nothing they could supply and the chart was a dead end.
        #
        # Ahead of the reducer's own state, not only when it came back incomplete. A hard gate
        # failing on an uncorroborated chain is still a verdict read off a segmentation nothing
        # vouched for, and letting it through returned ok, AVOID, and a pointer at ticker.risk
        # over a data-integrity gap the engine already knew about.
        status = "unavailable"
    elif result["setup_state"] != "incomplete":
        status = "ok"
    else:
        status = "needs_input"
    # Contrast evidence rides in the payload, never in `signals`: a reducer or a caller
    # scanning signal states would read another practitioner's disagreement as this harness's
    # own missing evidence. Named here rather than built inside the call because the citation
    # list below is harvested from it -- derived from `result` instead, the harvest read a
    # payload one key smaller than the one published, and the practitioners in that key were
    # reported to the caller and cited to nobody.
    data = {"ticker": ticker, **result, "contrast": evidence["contrast"]}
    return envelope(
        "ticker.setup",
        request=_clean_request({**request, "ticker": ticker}),
        as_of=_as_of(clock),
        status=status,
        data=data,
        # `signals` is the machine channel: what the verdict was built from. Measurements taken
        # off a chain nothing vouched for were not built into a verdict, and a caller or a later
        # reducer scanning states would read a hard gate's failure there as this harness's
        # finding about the stock. They stay in the payload, where a person reads them beside the
        # reason nothing counted. This is the rule contrast evidence already follows, for the
        # same reason.
        signals=result["signals"] if corroborated else [
            item for item in result["signals"] if item.get("id") == _CHAIN_COMPLETENESS
        ],
        missing=missing,
        sources=[_source(prices.meta)],
        # The detector's own convention decided the chain every measurement was read off, so it
        # is cited alongside the claims the signals name. Deriving the list from signals alone
        # left the one rule that is the harness's rather than the source's out of the answer.
        # The reducer's own list rather than a second derivation of it: the declared tactic is a
        # claim this verdict was reached under, and it appears in no signal because the caller
        # declared it instead of the bars measuring it.
        # The trading week joins it for the same reason: the base duration both week bands are
        # read against is a session count divided by that convention, so a reader following the
        # citation to either band arrives at a number this claim decided the unit of. So does
        # the volume-state convention, which sizes the two baselines every volume measurement
        # here is a ratio against -- both are read while the spec is compiled, so neither can
        # appear in a signal and neither is optional to the answer.
        #
        # And the contrast block's own names, because the reducer's list is what it reasoned
        # from and the contrast is a reading it made beside that: practitioners this harness
        # reads for comparison, published without their claims in the citation list, are a
        # standard the reader is shown and cannot look up.
        #
        # Harvested through the echo rule, so the caller's own `entry` object -- handed back
        # verbatim in `data` -- cannot name a claim and have this envelope report it as
        # doctrine the setup was decided under.
        doctrine_ids=sorted(
            {
                *result["doctrine_ids"],
                *_reducer_named_doctrine_ids(data, request),
                _SEGMENTATION_CONVENTION,
                _TRADING_WEEK_CONVENTION,
                _VOLUME_STATE_CONVENTION,
            }
        ),
        next_capabilities=[] if status == "unavailable" else ["ticker.chart"] if status == "needs_input" else ["ticker.risk"],
    )


def _refuse_unusable_setup_request(request: Mapping[str, Any]) -> None:
    """What no amount of price history could make valid."""

    swings = request.get("swing")
    if swings is not None and not isinstance(swings, list):
        raise RequestError("swing must be a list of completed session dates", "swing")
    entry = request.get("entry")
    if entry is not None and not isinstance(entry, Mapping):
        raise RequestError("entry must be an object", "entry")
    # Which entry this is, and whether the caller opted into it, are contract terms with their own
    # arguments. Restated inside the declaration they are a caller who has misunderstood the seam,
    # and dropping them quietly leaves that caller reading a gap they believe they filled.
    for reserved in ("kind", "opt_in"):
        if isinstance(entry, Mapping) and reserved in entry:
            raise RequestError(
                f"entry.{reserved} cannot be supplied; use entry_kind and tactic_opt_in",
                "entry",
            )
    for reserved in ("completeness_source", "detected_chain", "segmentation"):
        if request.get(reserved) is not None:
            # Naming a supplier is not being one, and neither is handing in a segmentation and
            # calling it independent. The seam exists for one this harness produced.
            raise RequestError(f"{reserved} cannot be supplied by the caller", reserved)
    # A chart reading with no picture named is a reading of nothing in particular. The value is
    # printed by both ticker.swings and ticker.chart, so carrying it costs a copy and buys the
    # one thing the date comparison cannot see: that the approval was of these bars. Only for
    # `complete`, which is the reading it gates -- a caller admitting a gap is telling the truth
    # whichever vintage they read it from, and charging them for the receipt would be the
    # opposite of costing them nothing.
    if request.get("chain_completeness") == "complete" and request.get("approved_bars") is None:
        raise RequestError(
            "approved_bars is required with chain_completeness complete: name the bars the chain was approved from, as ticker.swings and ticker.chart report them",
            "approved_bars",
        )


def _missing_reason(item: str, evidence: Mapping[str, Any]) -> str:
    """Which absence this is, because they are not fixed by the same thing.

    A reading nobody declared is fixed by declaring one. A reading the detector will not
    corroborate is fixed by nothing the caller can type. An approval of other bars is fixed by
    looking at the current chart again. Reporting all three as "evidence required" sends a
    reader looking for an argument in two of the three cases.
    """
    # Not evidence the caller could have supplied. "Early" is a time, and the source names five
    # tactics; what closes this is picking one, and telling a reader to supply evidence sends them
    # looking for a measurement of a tactic nobody named.
    if item == "named_entry_tactic":
        return "no_tactic_named"
    if item != _CHAIN_COMPLETENESS:
        return "evidence_required"
    segmentation = evidence["segmentation"]
    if segmentation.get("state") != "resolved":
        return "segmentation_unstable"
    if not evidence["chain_corroborated"]:
        return "declared_chain_is_not_the_detected_one"
    signal = next((item for item in evidence["signals"] if item.get("id") == _CHAIN_COMPLETENESS), {})
    measured = signal.get("measured") or {}
    if "approved_bars" in measured:
        return "approval_covers_different_bars"
    return "evidence_required"
