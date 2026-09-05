"""Prospective and active-position risk evidence composition."""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping
import pandas as pd
from ..dates import request_date as _request_date
from ..contracts import RequestError, envelope
from ..providers import ProviderSnapshot, ProviderUnavailable
from ..management_evidence import AVERAGES as MANAGEMENT_AVERAGES, BLOCKS as MANAGEMENT_BLOCKS, build_management_evidence
from ..risk import AUDIT_BASIS as _AUDIT_BASIS, crosses as _crosses, declares_exit_plan, reduce_risk, settled_breach, supplied_price_path, triggered_state as _triggered_state
from ..runtime import Runtime
from ..setup_structure import read_price_kinds
from ..stop_audit import _positive, _check_declared_shapes, _UNCROSSABLE_REASONS, _COVERAGE_FIELDS, _combine_audits, _max_high_since, _completed_stop_path, _attest_components, _AUDITED_COLUMNS

from . import PriceRead, _as_of, _cached_provider, _clean_request, _clock, _missing_provider, _price_read, _reducer_named_doctrine_ids, _source, _stale_price_gap, _ticker


# Every price the harness publishes is rounded to this many places, so a positive number
# below it is a price the reader would be handed as zero -- and the measurements divided by
# it come back infinite beside that zero. Such a scale is refused rather than reported on.
def _risk(request: Mapping[str, Any], runtime: Runtime) -> dict[str, Any]:
    ticker = _ticker(request.get("ticker"))
    clock = _clock(request.get("as_of"))
    mode = request.get("mode", "prospective")
    if mode not in {"prospective", "active"}:
        raise RequestError("mode must be prospective or active", "mode")
    evidence = {key: value for key, value in request.items() if key not in {"ticker", "as_of", "format", "no_cache"}}
    evidence["mode"] = mode
    # The reducer measures every audit window against the decision date, so it
    # cannot be the one input the operation keeps to itself.
    evidence["as_of"] = clock.date.isoformat()
    # For the same reason, and now for one more: the reducer cross-checks every component
    # attestation against the ticker it is reducing, and cannot do that on a ticker it was
    # never told.
    evidence["ticker"] = ticker
    # An attestation is minted below from an envelope and is never accepted from a request.
    # The CLI has no flag that produces one, but `execute` is a seam too, and a reference the
    # caller composed is the typed word this guard replaced, wearing the shape that replaced
    # it. Cleared unconditionally: a request that attaches nothing is exactly the one where a
    # forged reference has nothing to compete with.
    for plane in ("market", "eligibility", "setup", "fundamentals"):
        declared = evidence.get(plane)
        if isinstance(declared, Mapping) and "attested_by" in declared:
            evidence[plane] = {key: value for key, value in declared.items() if key != "attested_by"}
    attached = evidence.pop("evidence", None)
    attested_evidence: list[dict[str, Any]] = []
    if attached is not None:
        # The request keeps the envelopes it was given, unchanged: the input is declared as
        # envelopes, and an echo of a different shape is a request nobody can replay. What a
        # reader wants -- which capability, which ticker, which session vouched for each
        # plane, and which attachment was refused -- is a finding, so it goes in the payload.
        attested_evidence = _attest_components(evidence, attached, ticker=ticker, as_of=clock.date.isoformat())
    sources: list[dict[str, Any]] = []
    provider_missing: list[dict[str, Any]] = []
    _check_declared_shapes(evidence)
    invalidation = evidence.get("invalidation")
    # The audit needs the date the position started and a plan to clear; what it
    # was bought at decides 3R protection, not whether a level was breached. Both
    # predicates come from the reducer so routing cannot drift from the verdict.
    has_position_anchors = evidence.get("entry_date") is not None and declares_exit_plan(evidence)
    raw_stop_price = evidence.get("stop_price")
    stop_price = _positive(raw_stop_price)
    raw_invalidation_price = invalidation.get("price") if isinstance(invalidation, Mapping) else None
    invalidation_price = _positive(raw_invalidation_price)
    raw_initial_stop = evidence.get("initial_stop_price")
    initial_stop_price = _positive(raw_initial_stop)
    raw_current_price = evidence.get("current_price")
    current_price_input = _positive(raw_current_price)
    raw_entry_price = evidence.get("entry_price")
    entry_price = _positive(raw_entry_price)
    for raw, resolved, field in (
        (raw_stop_price, stop_price, "stop_price"),
        (raw_invalidation_price, invalidation_price, "invalidation_price"),
        (raw_initial_stop, initial_stop_price, "initial_stop_price"),
        # A price the caller hands in decides the verdict where the audit could not speak,
        # so a zero, a negative or a string in that field is not a value to drop quietly:
        # dropping it falls back on the provider and answers a question the caller asked a
        # different way, and keeping it sells the position at a price that is not a price.
        (raw_current_price, current_price_input, "current_price"),
        (raw_entry_price, entry_price, "entry_price"),
    ):
        if raw is not None and resolved is None:
            raise RequestError(f"{field} must be a finite positive number", field)
    widened = initial_stop_price is not None and stop_price is not None and stop_price < initial_stop_price
    protective_level = max(
        [level for level in (stop_price, invalidation_price, initial_stop_price if widened else None) if level is not None],
        default=None,
    )
    stop_effective_date: date | None = None
    entry_date: date | None = None
    if mode == "active" and evidence.get("entry_date") is not None:
        entry_date = _request_date(evidence["entry_date"], "entry_date")
        raw_effective_date = evidence.get("stop_effective_date")
        stop_effective_date = entry_date if raw_effective_date is None else _request_date(raw_effective_date, "stop_effective_date")
        # Chronology is checked before any evidence is fetched: a position that does
        # not exist on the decision date cannot be sold, held, or audited.
        if entry_date > clock.date:
            raise RequestError("entry_date cannot be after as_of", "entry_date")
        if stop_effective_date < entry_date:
            raise RequestError("stop_effective_date cannot precede entry_date", "stop_effective_date")
        if stop_effective_date > clock.date:
            raise RequestError("stop_effective_date cannot be after as_of", "stop_effective_date")
        # A stop the trade started with sits below the price it was entered at, or the
        # position runs no risk for the stop to bound and every measurement read from it --
        # the loss percent, the reward-to-risk, the R multiple -- is about a trade nobody
        # could have taken. A stop raised later is the opposite case and is left alone:
        # defending a gain above entry is the rule this harness is built on.
        if stop_price is not None and entry_price is not None and stop_price >= entry_price and stop_effective_date == entry_date:
            raise RequestError("stop_price must be below entry_price unless it was raised later, on a stop_effective_date after entry_date", "stop_price")
        if evidence.get("stop_effective_date") is not None:
            # Written back only when the caller declared it: the reducer's request contract
            # says a stop that differs from the initial one was raised on some date, and
            # materialising the default here would answer that question for them.
            evidence["stop_effective_date"] = stop_effective_date.isoformat()
    stage2_start: date | None = None
    if evidence.get("stage2_start") is not None:
        stage2_start = _request_date(evidence["stage2_start"], "stage2_start")
        if stage2_start > clock.date:
            raise RequestError("stage2_start cannot be after as_of", "stage2_start")
        evidence["stage2_start"] = stage2_start.isoformat()
    if evidence.get("management_average") is not None and evidence["management_average"] not in MANAGEMENT_AVERAGES:
        raise RequestError(f"management_average must be one of {', '.join(MANAGEMENT_AVERAGES)}", "management_average")
    raw_base_top = evidence.get("base_top")
    base_top = _positive(raw_base_top)
    if raw_base_top is not None and base_top is None:
        raise RequestError("base_top must be a finite positive number", "base_top")
    if evidence.get("earnings_date") is not None:
        evidence["earnings_date"] = _request_date(evidence["earnings_date"], "earnings_date").isoformat()
        evidence["earnings_source"] = "declared"
        evidence["earnings_confirmation"] = "declared_by_caller"
    elif not (mode == "active" and has_position_anchors):
        # Nothing to manage, so nothing to look up. Fetching a calendar for a request that
        # declares no position spends a provider call and puts a gap in `missing` about a
        # question the request never asked.
        pass
    elif clock.mode != "last_completed_session":
        # A calendar entry is a forecast, and no feed can say what it forecast last March.
        # Dating today's answer to an explicit past session would put a schedule nobody
        # published then inside a point-in-time verdict.
        evidence["earnings_unavailable_reason"] = "earnings_calendar_is_current_only"
    else:
        try:
            calendar = _cached_provider(
                runtime,
                request,
                clock,
                capability="ticker.risk",
                provider="yfinance",
                operation="next_earnings",
                params={"ticker": ticker},
                fetch=lambda: runtime.earnings_calendar(ticker),
                # The same short life every mutable current snapshot gets. A schedule that
                # moves is the normal case, and a day-old cached date would answer "still
                # ahead" about a report that has already been released.
                ttl_seconds=900,
            )
        except ProviderUnavailable as error:
            provider_missing.append({**_missing_provider(error), "required": False})
            evidence["earnings_unavailable_reason"] = error.reason
        else:
            sources.append(_source(calendar.meta))
            evidence["earnings_date"] = calendar.data["earnings_date"]
            evidence["earnings_source"] = "provider"
            evidence["earnings_confirmation"] = calendar.data["confirmation"]
            evidence["earnings_window"] = calendar.data["window"]
    raw_base_count = evidence.get("base_count")
    if raw_base_count is not None:
        if isinstance(raw_base_count, bool) or not isinstance(raw_base_count, int) or raw_base_count < 1:
            raise RequestError("base_count must be a whole number of bases, at least 1", "base_count")
    breakout_date: date | None = None
    if evidence.get("breakout_date") is not None:
        breakout_date = _request_date(evidence["breakout_date"], "breakout_date")
        if breakout_date > clock.date:
            raise RequestError("breakout_date cannot be after as_of", "breakout_date")
        evidence["breakout_date"] = breakout_date.isoformat()

    # A stop raised later is only in force from its own date, while the structural
    # invalidation has stood since entry. Auditing both against one date would let
    # the later start hide a breach the earlier level already suffered.
    protective_plan: list[tuple[str, float, date, date | None]] = []
    if stop_price is not None and stop_effective_date is not None:
        protective_plan.append(("stop", stop_price, stop_effective_date, None))
    if invalidation_price is not None and entry_date is not None:
        protective_plan.append(("invalidation", invalidation_price, entry_date, None))
    if initial_stop_price is not None and stop_price is not None and entry_date is not None and stop_effective_date is not None:
        if stop_price >= initial_stop_price:
            # The initial stop governed every completed session before the raise took effect.
            if stop_effective_date > entry_date:
                protective_plan.append(("initial_stop", initial_stop_price, entry_date, stop_effective_date))
        else:
            # A stop is never widened, so a lower later stop does not relieve the initial
            # one; the initial stop stays in force over the whole window.
            protective_plan.append(("initial_stop", initial_stop_price, entry_date, None))

    explicit_current = evidence.get("current_price")
    explicit_declared = protective_level is not None and isinstance(explicit_current, (int, float)) and not isinstance(explicit_current, bool)
    # Each level is read the way its own audit reads it: a stop is a price the position
    # transacts at, an invalidation a threshold the close has to be carried through.
    explicit_crossed = (
        [(role, level, effective) for role, level, effective, _end in protective_plan if _crosses(role, float(explicit_current), level)]
        if explicit_declared
        else []
    )
    explicit_completed_breach = bool(explicit_crossed)
    explicit_path: dict[str, Any] | None = None
    explicit_audits: list[dict[str, Any]] = []
    if mode == "active" and explicit_completed_breach and stop_effective_date is not None:
        price = float(explicit_current)
        # One price says one thing: which levels it is at or below. A level under it was not
        # cleared -- no bar was read, and a session last week could have taken it out -- so
        # it is unaudited rather than clear. The record is about the level the price actually
        # crossed, named by role, because a breached invalidation is not a breached stop.
        # A completed close below a resting stop proves the session traded at least that low,
        # so that stop was taken out intraday, before the close could invalidate anything.
        # Among levels read from the same price the highest is the one crossed first -- and
        # that is also why no expired-window filter is needed here: a window only ends when a
        # raise replaced it, so the level that expired is always below the one that replaced
        # it, and this comparison never reaches it. The audits below check the window itself.
        governing_role, governing_level, governing_from = min(explicit_crossed, key=lambda item: (0 if _AUDIT_BASIS[item[0]] == "completed_daily_low" else 1, -item[1]))
        explicit_audits = [
            {
                "role": role,
                "level": level,
                "effective_from": effective.isoformat(),
                **(
                    {"through": clock.date.isoformat(), "state": "breached", "basis": "explicit_completed_price", "breach_date": clock.date.isoformat(), "breach_price": price}
                    if _crosses(role, price, level) and (end_before is None or clock.date < end_before)
                    else {"state": "unavailable", "reason": "not_audited_after_explicit_breach"}
                ),
            }
            for role, level, effective, end_before in protective_plan
        ]
        explicit_path = {
            "state": "breached",
            "basis": "explicit_completed_price",
            "from": (governing_from or stop_effective_date).isoformat(),
            "through": clock.date.isoformat(),
            "checked_level": governing_level,
            "governing_role": governing_role,
            "breach_date": clock.date.isoformat(),
            "breach_price": price,
            "audits": explicit_audits,
        }
    # An assertion settles the verdict, not the record. It says the position ended without
    # saying when, and the bars can hold an exit that happened first -- so they are read, and
    # the earliest dated exit names the failure. What a settled verdict does buy is that the
    # absence of those bars cannot downgrade it: they were consulted, not depended on.
    # The one exception is a price path the caller handed in, which is the same record the
    # bars would produce; re-deriving it would discard what they supplied.
    settled = settled_breach(evidence)
    if mode == "active" and has_position_anchors and not supplied_price_path(evidence) and _triggered_state(evidence.get("completed_price_path")):
        # Not a record, so it does not stand in for one. It is still what the caller said,
        # and a verdict that quietly drops it is a payload the caller cannot reconcile with
        # their own request -- so it travels as the assertion it is and meets the bars.
        evidence["asserted_price_path"] = evidence.pop("completed_price_path")
    if mode == "active" and has_position_anchors and supplied_price_path(evidence):
        # The structural blocks still travel with the SELL, saying why they are empty: a
        # block that vanishes reads as a measurement with nothing to report.
        evidence["management"] = {
            key: {"state": "unavailable", "reason": "price_history_not_fetched_after_supplied_price_path"}
            for key in MANAGEMENT_BLOCKS
        }
    if mode == "active" and has_position_anchors and not supplied_price_path(evidence):
        try:
            prices, _, _ = _price_read(runtime, request, clock, ticker, PriceRead("ticker.risk"))
        except ProviderUnavailable as error:
            provider_missing.append({**_missing_provider(error), "required": not settled})
            # The blocks still travel with a verdict the request settled on its own, and they
            # say what actually happened: the history was asked for and the provider had none.
            # A block that vanishes reads as a measurement with nothing to report instead.
            evidence["management"] = {key: {"state": "unavailable", "reason": "price_history_unavailable"} for key in MANAGEMENT_BLOCKS}
        else:
            sources.append(_source(prices.meta))
            # The three readings below -- the stop audit, the management evidence, and the
            # current close -- each normalised the frame separately, and each read a value
            # that is not a price as one. A boolean Low became 1.0 and breached every stop;
            # complex prices lost their imaginary part and sold the position; the management
            # averages read timestamps as epoch numbers and published a breach at 1.58e15;
            # a positional index became nanoseconds after 1970 and moved the window into a
            # year the position did not exist in.
            #
            # Holes are left to the blocks, which name the bar they could not read and report
            # the prefix they had already cleared. That is a finer answer than withholding
            # the verdict, and it is why this reads the narrower reader rather than the one
            # a whole-window measurement needs.
            bars, rejection = read_price_kinds(prices.data, columns=_AUDITED_COLUMNS)
            if bars is None:
                provider_missing.append({"id": "usable_daily_bars", "reason": rejection, "required": not settled})
                evidence["management"] = {key: {"state": "unavailable", "reason": rejection} for key in MANAGEMENT_BLOCKS}
            else:
                prices = ProviderSnapshot(bars, prices.meta)
                stale_price = _stale_price_gap(prices.meta)
                if stale_price is not None:
                    provider_missing.append(stale_price)
                current_price = None
                # A High that was printed is a fact whether or not the history reaches as_of,
                # so this is measured before staleness is weighed; the reducer only acts on
                # it under a HOLD the audit has established.
                if entry_date is not None:
                    evidence.update(_max_high_since(prices.data, entry_date=entry_date, as_of=clock.date))
                    evidence["management"] = build_management_evidence(
                        prices.data,
                        entry_date=entry_date,
                        as_of=clock.date,
                        management_average=evidence.get("management_average"),
                        stage2_start=stage2_start,
                        base_top=base_top,
                        breakout_date=breakout_date,
                    )
                if protective_plan:
                    # Runs even when the history stops early: a completed breach is
                    # irreversible, and a later missing bar cannot undo one.
                    audits: list[dict[str, Any]] = []
                    path_price = None
                    for role, level, effective, end_before in protective_plan:
                        audit, audit_price = _completed_stop_path(
                            prices.data,
                            effective_date=effective,
                            as_of=clock.date,
                            protective_level=level,
                            end_before=end_before,
                            # A stop can be moved on a day the market was shut; an entry cannot happen on one.
                            require_session=effective == entry_date,
                            basis=_AUDIT_BASIS[role],
                        )
                        audits.append({**audit, "role": role, "level": level, "effective_from": effective.isoformat()})
                        path_price = audit_price if audit_price is not None else path_price
                    # A price handed in is an observation dated as_of, which is the latest date any
                    # exit can carry. It stands where the bars found no breach of that level, and
                    # yields to a breach the bars printed, because that one happened first.
                    crossed_now = {item["role"]: item for item in explicit_audits if item["state"] == "breached"}

                    def with_price(audit: dict[str, Any]) -> dict[str, Any]:
                        told = crossed_now.get(audit["role"])
                        # A window the audit refused because it spans a corporate action is not a
                        # window one more price can settle: the declared level is in the old
                        # coordinate system and the price is in the new one, and comparing them is
                        # the arithmetic that refusal exists to prevent.
                        if told is None or audit["state"] == "breached" or audit.get("reason") in _UNCROSSABLE_REASONS:
                            return audit
                        # The bars still covered what they covered; the price only added what they
                        # could not say. Both belong in one record.
                        return {**told, **{key: value for key, value in audit.items() if key in _COVERAGE_FIELDS}}

                    audits = [with_price(audit) for audit in audits]
                    price_path = _combine_audits(audits)
                    evidence["completed_price_path"] = price_path
                    if stale_price is None:
                        current_price = path_price
                    # Whichever observation the record was built from is the one published beside
                    # it: two different latest prices for one session tells the reader the trade
                    # ended at a price the payload denies.
                    if price_path.get("basis") == "explicit_completed_price":
                        current_price = float(explicit_current)
                        # The history stopping a session short is what the price was handed in
                        # for. It is still reported, as evidence this reading did without.
                        provider_missing = [item if item["id"] != "completed_price_evidence" else {**item, "required": False} for item in provider_missing]
                    elif price_path.get("reason") in _UNCROSSABLE_REASONS:
                        current_price = None
                        evidence.pop("current_price", None)
                    if price_path.get("state") == "unavailable":
                        provider_missing.append(
                            {
                                "id": "completed_price_path",
                                "provider": prices.meta.provider,
                                "reason": price_path.get("reason", "completed_price_path_unavailable"),
                                "required": True,
                                "attempts": 1,
                                "retryable": False,
                            }
                        )
                elif stale_price is None:
                    # A price from an earlier session can only make a position look
                    # safer than the evidence supports, so it is withheld entirely. A price
                    # from a *later* one is not this analysis's to report at all -- the frame
                    # can reach past the session being analysed, and the last row was read
                    # straight through whatever session it belonged to.
                    through = prices.data.loc[prices.data.index <= pd.Timestamp(clock.date)]
                    try:
                        current_price = float(through["Close"].iloc[-1])
                    except (AttributeError, KeyError, IndexError, TypeError, ValueError):
                        current_price = None
                if current_price is not None:
                    evidence["current_price"] = current_price
    if explicit_path is not None and evidence.get("completed_price_path") is None:
        # No audit reached the levels -- the provider had nothing to give, or the request
        # declared no plan to audit. The price the caller handed in is then the whole record.
        evidence["completed_price_path"] = explicit_path
    result = reduce_risk(evidence)
    status = "partial" if any(item.get("required") for item in provider_missing) else "needs_input" if result["verdict"] == "INCOMPLETE" else "ok"
    provider_missing_ids = {item["id"] for item in provider_missing}
    # A plane that came in as a word nobody measured is not the same gap as evidence that was
    # never supplied, and the fix is different: run the capability that settles it and attach
    # what it returns. Saying "evidence required" there sends a reader to type the word again.
    unattested = result.get("unattested") or {}
    missing = [
        *provider_missing,
        *(
            {"id": item, "reason": unattested.get(item, "evidence_required"), "required": True}
            for item in result["missing"]
            if item not in provider_missing_ids
        ),
    ]
    data = {
        "ticker": ticker,
        **result,
        "attested_evidence": attested_evidence,
        "current_price": evidence.get("current_price"),
        "max_high_since_entry": evidence.get("max_high_since_entry"),
        "max_high_date": evidence.get("max_high_date"),
        "max_high_withheld_reason": evidence.get("max_high_withheld_reason"),
        "max_high_withheld_date": evidence.get("max_high_withheld_date"),
    }
    return envelope(
        "ticker.risk",
        request=_clean_request({**request, "ticker": ticker}),
        as_of=_as_of(clock),
        status=status,
        data=data,
        signals=[
            {"id": item, "state": "fail"} for item in result["failed"]
        ] + [{"id": item, "state": "not_triggered"} for item in result["waiting"]],
        missing=missing,
        sources=sources,
        doctrine_ids=_risk_doctrine_ids(mode, data, request),
    )


def _risk_doctrine_ids(mode: str, data: Mapping[str, Any], request: Mapping[str, Any]) -> list[str]:
    """The claims this result actually cites: the mode's own risk claims, plus every claim
    the payload names beside a measurement or an action. A fixed list said more than the
    result used in one mode and less than it used in the other."""

    base = (
        ["risk.initial_stop_and_reward", "risk.profit_protection_at_3r"]
        if mode == "prospective"
        else ["risk.hard_stop_and_no_average_down", "risk.profit_protection_at_3r"]
    )
    return base + sorted(_reducer_named_doctrine_ids(data, request) - set(base))
