"""Pure verdict reducer for prospective entries and active positions."""

from __future__ import annotations

import math
from collections.abc import Mapping
from copy import deepcopy
from datetime import date, timedelta
from typing import Any

from . import doctrine


# Enough places to strip binary-float noise from a reported figure and far too many
# to soften any limit the registry states.
_REPORTED_PRECISION = 10
_ENTRY_RISK = "risk.initial_stop_and_reward"
_PROFIT_PROTECTION = "risk.profit_protection_at_3r"
_TL_HALF_AT_FIVE = "management.tl_stage12_half_at_five_percent"
_STRENGTH_REFERENCES = "management.tl_sell_into_strength_at_average_gain_and_r_multiples"
# A management profile is a tagged practice-layer default the trader opts into. It reaches
# the management actions under HOLD and never the verdict, and each action it produces says
# so: binds false, source "[TL]", and the contrast state the gate actually returned.
_PROFILES = {"tl_stage12": _TL_HALF_AT_FIVE}
_ROLES = "management.ema21_sma50_roles"
_PAUSE_ZONE = "management.tl_base_extension_pause_zone"
_FAILED_VOLUME = "management.low_volume_breakout_then_high_volume_selling"
_MARKET_DEFENSE = "management.market_defense_tightens_stops"
_EARNINGS = "management.earnings_awareness_while_holding"
_ZANGER_EARNINGS = "management.zanger_does_not_hold_through_earnings"
_BASE_COUNT = "basecount.typical_top_after_3_to_5_bases"
_BASE_COUNT_DISCLAIMER = "basecount.role_and_disclaimer"
_DECLARED_PLAN = "contract.declared_exit_plan_is_audited"
_DIFFICULT_MARKET = ("cautious", "defensive")
_TWENTY_DAY = "management.close_below_20_day_average_lowers_probability"
_LARGEST_DECLINE = "management.largest_decline_since_stage2_start"
# The averages the harness measures a held position against. One of them may be the
# trader's declared exit plan; the other is still read, as review evidence.
_AVERAGES = ("ema21", "sma50")

# `waived_by_exception` is deliberately absent. It is the one word in this vocabulary that
# claims an absence of evidence has been forgiven, and it was reachable by writing it: with
# nothing else supplied, `--fundamentals-state waived_by_exception` produced BUY-READY on a
# ticker whose fundamentals nobody had looked at and whose Power Play nothing had measured.
# The exception is real, but it is earned by measurement plus an approved chart, and no
# reducer that reads caller-supplied state words is in a position to check that it was.

# The four planes whose word is a verdict some other capability reached, and the capability
# that reaches each. The comment above is about one word; the argument under it was never
# about one word. Every plane here is a state this reducer cannot check and a caller can
# type, and typed together on a ticker that does not exist they returned BUY-READY with the
# envelope's own `sources` list empty beside it. So a pass on one of these counts only when
# the envelope that measured it is referenced here. The rule the four share is one sentence:
# a word the caller supplies may only move the verdict toward no-trade. A declared failure
# still fails and a declared wait still waits -- both are conservative, and doctrine already
# reaches AVOID from a known failure. Passing is the one direction where being wrong costs
# money, and it is the one direction a word alone no longer buys.
_ATTESTING_OPERATION = {
    "market": "market.snapshot",
    "eligibility": "ticker.qualify",
    "setup": "ticker.setup",
    "fundamentals": "ticker.fundamentals",
}

# What each capability calls its own verdict, so a caller who pastes that payload in is read
# correctly. The market names its regime rather than a state, and is read from `state` alone.
_PLANE_ALIAS = {
    "eligibility": "eligibility_state",
    "setup": "setup_state",
    "fundamentals": "fundamentals_state",
}

_PASS = {"pass", "ready", "confirmed", "eligible", "supports", "observed", "complete", "favorable", "supports_convergence"}
_FAIL = {"fail", "failed", "avoid", "contradicts", "broken", "invalid", "does_not_support_convergence"}
_WAIT = {"wait", "pending", "watch", "not_triggered", "cautious", "defensive"}
_MISSING = {"unavailable", "needs_input", "needs_chart", "incomplete", "unknown"}


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _state(value: Any, default: str = "unavailable", alias: str | None = None) -> str:
    if isinstance(value, bool):
        return "pass" if value else "fail"
    if isinstance(value, Mapping):
        # A plane's own capability names its verdict after the plane -- `setup_state`,
        # `eligibility_state` -- so a caller pasting that payload in is understood. The alias
        # is per plane rather than shared: read for every object, `setup_state` spoke for the
        # risk plane too, and `{"state": "fail", "setup_state": "ready"}` turned a declared
        # risk failure into a pass.
        aliased = value.get(alias) if alias else None
        if aliased is not None:
            value = aliased
        else:
            value = value.get("state", value.get("status"))
    if value is None:
        return default
    normalized = str(value).strip().lower().replace("-", "_")
    if normalized in _PASS:
        return "pass"
    if normalized in _FAIL:
        return "fail"
    if normalized in _WAIT:
        return "wait"
    if normalized in _MISSING:
        return "unavailable"
    return default


def is_non_passing(value: Any) -> bool:
    """Whether this word makes a component plane more cautious than a pass.

    The vocabulary lives beside the reducer that reads it. A second copy anywhere else is a
    second place for `avoid` to quietly stop meaning avoid. `incomplete` is not one of these:
    it says the caller does not know, and something that does know may still answer.
    """

    return _state(value, default="") in {"fail", "wait"}


def _attests(value: Any, plane: str, ticker: Any, as_of: Any) -> bool:
    """Whether this evidence object references the envelope that measured its own plane.

    A reference rather than a flag, and cross-checked rather than trusted: `attested: true`
    would be the same defect one level up, another word the caller can type. The reference
    has to name the capability that measures this plane, so a setup envelope cannot vouch
    for eligibility, and it has to name the ticker and the session being reduced, because a
    stale reference is the ordinary way a correct one goes wrong.
    """

    if not isinstance(value, Mapping):
        return False
    reference = value.get("attested_by")
    if not isinstance(reference, Mapping):
        return False
    if reference.get("operation") != _ATTESTING_OPERATION.get(plane):
        return False
    if reference.get("status") not in {"ok", "partial"}:
        return False
    if not as_of or reference.get("as_of") != as_of:
        return False
    # The market is measured for the session and not for a ticker, so its envelope names
    # none. Requiring one there would refuse the only shape that capability can produce.
    if plane == "market":
        return reference.get("ticker") is None
    return bool(ticker) and reference.get("ticker") == ticker


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value > 0 and math.isfinite(value):
        return float(value)
    return None


def _risk_value(payload: Mapping[str, Any], name: str) -> Any:
    risk = payload.get("risk")
    if isinstance(risk, Mapping) and name in risk:
        return risk[name]
    return payload.get(name)


def _prospective(payload: Mapping[str, Any]) -> dict[str, Any]:
    ticker = payload.get("ticker")
    as_of = payload.get("as_of")
    components: dict[str, str] = {}
    unattested: dict[str, str] = {}
    for name in ("market", "eligibility", "setup", "fundamentals"):
        supplied = payload.get(name)
        state = _state(supplied, alias=_PLANE_ALIAS.get(name))
        if state == "pass" and not _attests(supplied, name, ticker, as_of):
            # Not a failure and not a pass: nobody this reducer can name measured it. That is
            # the harness's own word for unavailable evidence, and it reaches INCOMPLETE.
            state = "unavailable"
        if state == "unavailable":
            refused = supplied.get("attestation_refused") if isinstance(supplied, Mapping) else None
            if refused is not None:
                # An envelope was attached and did not survive the comparison. The reason is
                # the refusal's own, because "unattested" would send a reader to attach the
                # envelope they already attached.
                unattested[name] = str(refused)
            elif _state(supplied, default="") == "pass":
                unattested[name] = "unattested_state_word"
        components[name] = state
    risk_input = _mapping(payload.get("risk"))
    has_risk_inputs = bool(risk_input) or any(
        payload.get(name) is not None for name in ("entry_price", "stop_price", "upside_price", "target_price", "average_gain_pct")
    )
    risk_state = _state(risk_input, default="pass" if has_risk_inputs else "unavailable")
    failed: list[str] = []
    missing: list[str] = []
    waiting: list[str] = []

    for name in ("eligibility", "setup", "fundamentals"):
        if components[name] == "fail":
            failed.append(name)
        elif components[name] == "unavailable":
            missing.append(name)
        elif components[name] == "wait":
            waiting.append(name)
    if components["market"] == "unavailable":
        missing.append("market")
    elif components["market"] in {"fail", "wait"}:
        waiting.append("market")

    entry = _number(_risk_value(payload, "entry_price"))
    stop = _number(_risk_value(payload, "stop_price"))
    upside = _number(_risk_value(payload, "upside_price")) or _number(_risk_value(payload, "target_price"))
    average_gain = _number(_risk_value(payload, "average_gain_pct"))
    stop_ceiling = doctrine.threshold(_ENTRY_RISK, "initial_stop_ceiling_pct")
    average_gain_multiple = doctrine.threshold(_ENTRY_RISK, "half_average_gain_multiple")
    controls: dict[str, Any] = {
        "initial_stop_pct": None,
        "initial_stop_cap_pct": stop_ceiling,
        # At the precision every other figure here is printed at. Tidied to four places, a
        # cap prints below a stop it actually admits, and the reader is handed a failure the
        # verdict beside it did not reach.
        "half_average_gain_cap_pct": _reported(average_gain * average_gain_multiple) if average_gain else None,
        "loss_target": None,
        "reward_to_risk": None,
        "minimum_reward_to_risk": doctrine.threshold(_ENTRY_RISK, "reward_to_risk_minimum"),
        "preferred_reward_to_risk": doctrine.threshold(_ENTRY_RISK, "reward_to_risk_preferred"),
        "breakeven_at_r": doctrine.threshold(_PROFIT_PROTECTION, "breakeven_protection_trigger_r"),
    }

    if risk_state == "fail":
        failed.append("risk")
    elif risk_state == "unavailable":
        missing.append("risk")
    elif risk_state == "wait":
        waiting.append("risk")

    if entry is None:
        missing.append("entry_price")
    if stop is None:
        missing.append("stop_price")
    if upside is None:
        missing.append("upside_price")
    if average_gain is None:
        # The half-average-gain cap is the tighter of the two stop ceilings for most
        # traders, so an absent realized average gain hides a gate rather than relaxing one.
        missing.append("average_gain_pct")
    if entry is not None and stop is not None:
        if stop >= entry:
            failed.append("initial_stop_price")
        else:
            # Rounded for the reader, never for the comparison: a value tidied to the
            # limit before it is checked is a tolerance the gate design forbids.
            stop_pct = (entry - stop) / entry * 100
            controls["initial_stop_pct"] = _reported_beside_gate(stop_pct, _ENTRY_RISK, "initial_stop_ceiling_pct")
            # The source gives the ordinary loss target as a range, so the reading
            # travels with its range instead of collapsing to a pass.
            controls["loss_target"] = doctrine.evaluate_band(_ENTRY_RISK, "ordinary_loss_target_pct", stop_pct)
            if doctrine.evaluate_gate(_ENTRY_RISK, "initial_stop_ceiling_pct", stop_pct)["state"] == "fail":
                failed.append("initial_stop_pct")
            if average_gain is not None and stop_pct > average_gain * average_gain_multiple:
                failed.append("half_average_gain_cap")
            if upside is not None:
                reward_to_risk = (upside - entry) / (entry - stop)
                controls["reward_to_risk"] = _reported_beside_gate(reward_to_risk, _ENTRY_RISK, "reward_to_risk_minimum")
                if doctrine.evaluate_gate(_ENTRY_RISK, "reward_to_risk_minimum", reward_to_risk)["state"] == "fail":
                    failed.append("reward_to_risk")
    elif entry is not None and upside is not None and upside <= entry:
        failed.append("upside_price")

    if failed:
        verdict = "AVOID"
    elif missing:
        verdict = "INCOMPLETE"
    elif waiting:
        verdict = "WAIT"
    else:
        verdict = "BUY-READY"
    return {
        "mode": "prospective",
        "verdict": verdict,
        "components": {**components, "risk": risk_state},
        "risk_controls": controls,
        "base_count_context": _base_count_context(payload),
        "failed": list(dict.fromkeys(failed)),
        "missing": list(dict.fromkeys(missing)),
        "waiting": list(dict.fromkeys(waiting)),
        # Named separately from the rest of `missing` because the two gaps are closed by
        # different acts. An ordinary gap is closed by supplying evidence; this one is closed
        # by running the capability that measures the plane and handing its envelope back.
        "unattested": unattested,
    }


def _reported(value: float | None) -> float | None:
    """Round for the reader only; every comparison ran on the measurement itself.

    A figure that is not finite is not a measurement, whatever arithmetic produced it, and
    an infinity on the page is worse than the absence it stands for: it reads as a quantity.
    """

    if value is None or not math.isfinite(value):
        return None
    return round(value, _REPORTED_PRECISION)


def _reported_beside_gate(value: float, claim_id: str, name: str) -> float:
    """Round for the reader unless rounding would move the figure across the gate.

    A measurement one part in ten billion short of a limit rounds to the limit itself and
    then sits beside a state that says the limit was not reached. Publishing the raw figure
    in that one case keeps the number and the state saying the same thing.
    """

    rounded = round(value, _REPORTED_PRECISION)
    if doctrine.evaluate_gate(claim_id, name, rounded)["state"] != doctrine.evaluate_gate(claim_id, name, value)["state"]:
        return value
    return rounded


def _status_word(value: Any) -> str:
    """The one way this module reads a state, so two readers cannot disagree."""

    if not isinstance(value, Mapping):
        return ""
    return str(value.get("state", value.get("status", ""))).strip().lower()


def _triggered(value: Any) -> bool:
    return _status_word(value) in {"triggered", "breached"}


def _iso_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _audit_records(path: Mapping[str, Any], path_state: str) -> list[dict[str, Any]]:
    """Per-level audit records; a single-level path counts as one record."""

    audits = path.get("audits")
    if isinstance(audits, list):
        return [dict(item) for item in audits if isinstance(item, Mapping)]
    if not path:
        return []
    return [
        {
            "level": path.get("checked_level"),
            "role": "stop",
            "effective_from": path.get("from"),
            "through": path.get("through"),
            "bars_checked": path.get("bars_checked"),
            "state": path_state,
        }
    ]


def _context_blocks(payload: Mapping[str, Any], *, as_of: date | None, entry: float | None) -> dict[str, Any]:
    """Context the caller declares rather than the bars carry, for a position being managed.

    Neither of these can sell. A deteriorating market tightens the stop the trader already
    has, and a coming report is a review.
    """

    blocks: dict[str, Any] = {}
    market_state = _status_word(payload.get("market")) or None
    # The level the position is actually defended by, which is not always the declared stop:
    # a stop is never widened, so an initial stop above a later, looser one stays in force,
    # and measuring the loss from the looser level would report a risk the trade does not run
    # and then order a raise to the level the audit says never stopped governing.
    stop = _effective_stop(payload)
    # A stop raised above entry defends a gain rather than bounding a loss, so there is no
    # loss percent to read: publishing the negative distance would put a number under a
    # band about how tight a stop should be that is not the thing the band measures.
    loss_pct = (entry - stop) / entry * 100 if entry and stop is not None and stop < entry else None
    band = doctrine.evaluate_band(_MARKET_DEFENSE, "difficult_market_loss_pct", loss_pct)
    # Read off the evaluation rather than out of the registry a second time. Indexing the
    # threshold directly is the end-run around `threshold()`'s refusal to hand back a band
    # raw, and it skips the out-of-scope and quarantine refusals that seam also carries.
    low, high = band["source_range"]
    tighten_to = _reported(entry * (1 - high / 100)) if entry else None
    current = _number(payload.get("current_price"))
    # A stop above the last price is not a tighter stop, it is a sale at the market -- which
    # is exactly what this claim says a deteriorating tape must not cause. When the range the
    # source names sits above where the stock trades, the range is reported and nothing acts.
    # With no last price there is nothing to establish that against, and an unknown is not a
    # yes: placeability is reported unavailable rather than assumed.
    placeable = None if tighten_to is None or current is None else tighten_to < current
    reason = (
        None
        if placeable
        else "entry_price_unavailable"
        if tighten_to is None
        else "current_price_unavailable"
        if current is None
        else "tightened_level_is_at_or_above_the_last_price"
    )
    blocks["market_defense"] = {
        "doctrine_id": _MARKET_DEFENSE,
        "binds": doctrine.binds(_MARKET_DEFENSE),
        "state": "reported" if market_state is not None else "unavailable",
        "market_state": market_state,
        "stop_pct": band.get("measured"),
        "measured_from_stop": stop,
        "difficult_market_band": band,
        "tighten_to": tighten_to,
        "tighten_to_is_placeable": placeable,
        "not_placeable_reason": reason,
        "never_sells_on_market_opinion": True,
    }
    earnings_date = _iso_date(payload.get("earnings_date"))
    if earnings_date is None:
        # Three different silences, and only one of them is the analyst's. A date the harness
        # looked up and did not find is not the same gap as one it declined to look up, and a
        # reader deciding whether to go and check the calendar themselves needs to know which.
        blocks["earnings"] = {"state": "unavailable", "reason": payload.get("earnings_unavailable_reason") or "earnings_date_not_declared"}
    else:
        # A report dated on as_of belongs to a session that has completed, so it is not still
        # ahead; it is due on the session the request is asking about, which is its own state.
        ahead = as_of is not None and earnings_date > as_of
        due_on_as_of = as_of is not None and earnings_date == as_of
        blocks["earnings"] = {
            "doctrine_id": _EARNINGS,
            "binds": doctrine.binds(_EARNINGS),
            "state": "reported",
            "earnings_date": earnings_date.isoformat(),
            "ahead": ahead,
            "due_on_as_of": due_on_as_of,
            "days_until": (earnings_date - as_of).days if as_of is not None else None,
            # Where the date came from and how firm it is. A REVIEW raised on a window the feed
            # guessed at is a weaker thing than one raised on a confirmed date, and the action
            # reads the same either way -- so the difference has to be here.
            "source": payload.get("earnings_source") or "declared",
            "confirmation": payload.get("earnings_confirmation") or "declared_by_caller",
            "window": payload.get("earnings_window"),
            "contrast": {
                "doctrine_id": _ZANGER_EARNINGS,
                "binds": doctrine.binds(_ZANGER_EARNINGS),
                "source": "Zanger",
                "practice": "has not held a position through an earnings release in more than ten years",
            },
        }
    return blocks


def _base_count_context(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Where the advance sits among its own bases, reported and never acted on.

    Every mode publishes it in the same place. It travelled inside management_evidence
    before, which is a bundle keyed to a position being managed -- so a prospective request
    had nowhere to put it and dropped the count it had been handed, and an active request
    that never established a position dropped it too, along with the measurements that
    emptying is actually about. The count is a property of the advance rather than of a
    position, and its claims are scoped to the entry decision, so it is neither of those.

    It cannot act. The source attaches its own refusal to predict a top from the count to
    the count itself, so the band reports where the measurement sat and stops there.
    """

    base_count = payload.get("base_count")
    if isinstance(base_count, bool) or not isinstance(base_count, int) or base_count < 1:
        return {"state": "unavailable", "reason": "base_count_not_declared"}
    return {
        "doctrine_id": _BASE_COUNT,
        "binds": doctrine.binds(_BASE_COUNT),
        "state": "reported",
        "base_count": base_count,
        "band": doctrine.evaluate_band(_BASE_COUNT, "typical_base_count_before_top", base_count),
        "disclaimer_doctrine_id": _BASE_COUNT_DISCLAIMER,
        "disclaimer": "Counting bases gives perspective on maturity; by itself it cannot say a stock has topped.",
        # The disclaimer's claim also lists price and volume history, which this reading
        # never consumes: it reports the count the caller declared against the source's
        # band and quotes the qualification the source attached to it.
        "claim_inputs_not_read": ["price_history", "volume_history"],
    }


# Which basis an audit's clear finding can settle. A window where no Low reached a level
# is a window where no close fell below it either, because a close is inside its own
# session's range -- so the order audit answers both questions. The reverse does not hold:
# closes that stayed above a level say nothing about the lows underneath them, and reading
# a cleared invalidation as a cleared stop is how an order that was taken out intraday goes
# unreported.
_PROVES = {
    "completed_daily_low": frozenset({"completed_daily_low", "completed_daily_close"}),
    "completed_daily_close": frozenset({"completed_daily_close"}),
}


def _record_basis(record: Mapping[str, Any]) -> str | None:
    """Which prices a record was audited against, taken from its role or its own word."""

    role = record.get("role")
    if isinstance(role, str) and role in AUDIT_BASIS:
        return AUDIT_BASIS[role]
    basis = record.get("basis")
    return basis if isinstance(basis, str) else None


def _audited(records: list[Mapping[str, Any]], role: str, level: float, required_from: date | None, required_to: date | None) -> bool:
    """Whether some record cleared ``role``'s ``level`` over every session from ``required_from`` to ``required_to``.

    ``required_to`` is as_of for a level still in force and the eve of the raise for an
    initial stop that a later stop superseded upward.
    """

    if required_from is None or required_to is None:
        return False
    wanted = AUDIT_BASIS[role]
    for record in records:
        audited_level = _number(record.get("level"))
        if audited_level is None or audited_level < level:
            continue
        basis = _record_basis(record)
        if basis is None or wanted not in _PROVES[basis]:
            continue
        if _status_word(record) != "clear":
            continue
        # A window that starts late leaves the sessions before it unexamined, and one
        # that ends early cannot speak for the sessions after it.
        effective_from = _iso_date(record.get("effective_from"))
        through = _iso_date(record.get("through"))
        if effective_from is None or through is None:
            continue
        if effective_from > required_from or through < required_to:
            continue
        bars = record.get("bars_checked")
        if not isinstance(bars, int) or isinstance(bars, bool) or bars < 1:
            continue
        return True
    return False


def _exit_plan(payload: Mapping[str, Any]) -> tuple[float | None, bool]:
    """The invalidation's auditable level and whether it carries a real condition."""

    invalidation = _mapping(payload.get("invalidation"))
    condition = invalidation.get("condition")
    return _number(invalidation.get("price")), isinstance(condition, str) and bool(condition.strip())


def _effective_stop(payload: Mapping[str, Any]) -> float | None:
    """The protective level actually in force: the higher of the declared and initial stops.

    A stop is never widened. When a later stop sits below the one the trade started with,
    the initial one keeps governing -- the stop audit already reads it that way -- and every
    measurement of what the position risks has to read the same level the audit does.
    """

    stop = _number(payload.get("stop_price"))
    initial = _number(payload.get("initial_stop_price"))
    levels = [level for level in (stop, initial) if level is not None]
    return max(levels) if levels else None


def declares_exit_plan(evidence: Mapping[str, Any]) -> bool:
    """Whether an exit level or condition was actually declared.

    A mapping that carries only a status declares no level and no condition, so
    there is nothing for a "triggered" flag to be a trigger of.
    """

    payload = _mapping(evidence)
    invalidation_price, has_condition = _exit_plan(payload)
    return payload.get("stop_price") is not None or invalidation_price is not None or has_condition


def settled_breach(evidence: Mapping[str, Any]) -> bool:
    """Whether the evidence already settles the verdict without completed price history.

    The operation asks this before fetching bars: a breach it would never look at
    is a request that can only downgrade a terminal SELL to a partial one.

    Only an undated assertion settles anything here. A price handed in carries a date --
    ``as_of``, the latest one any exit can have -- so the bars can still hold an exit that
    happened first, and the earliest dated exit is the one that names the failure. Skipping
    the fetch for it would publish the wrong level on the wrong day.
    """

    payload = _mapping(evidence)
    if payload.get("mode") != "active":
        return False
    invalidation = _mapping(payload.get("invalidation"))
    invalidation_price, _ = _exit_plan(payload)
    stop = _number(payload.get("stop_price"))
    current = _number(payload.get("current_price"))
    levels = [level for level in (stop, invalidation_price) if level is not None]
    live_stop = _mapping(payload.get("live_stop"))
    return (
        # Every asserted stop breach is about the declared stop, so with none declared there
        # is nothing asserted and nothing settled -- the operation still fetches the bars.
        (stop is not None and bool(payload.get("live_stop_check")) and live_stop.get("partial_session") is True and _triggered(live_stop))
        or (stop is not None and _triggered(payload.get("completed_stop")))
        or (stop is not None and _triggered(payload.get("stop_event")))
        or _triggered(payload.get("completed_price_path"))
        or (declares_exit_plan(payload) and _triggered(invalidation))
    )


# Which price each protective level is a level of, and what counts as crossing it. A stop is
# an order resting in the market: the tape takes it out the moment the Low reaches it, so
# reaching it is enough. A structural invalidation is a threshold the thesis has to be
# carried through -- the condition a caller writes beside one says "below" -- so a close that
# stopped exactly on it has not gone below it. Both the audit over completed bars and every
# comparison against a price handed in read a level from here, because a level read two ways
# is two answers to one question.
AUDIT_BASIS = {"stop": "completed_daily_low", "initial_stop": "completed_daily_low", "invalidation": "completed_daily_close"}
_CROSSES = {
    "completed_daily_low": lambda price, level: price <= level,
    "completed_daily_close": lambda price, level: price < level,
}


def crosses(role: str, price: float, level: float) -> bool:
    """Whether ``price`` crossed ``level``, asked the way that role's own audit asks it."""

    return _CROSSES[AUDIT_BASIS[role]](price, level)


def triggered_state(record: Any) -> bool:
    """Whether a record's state word says the thing it is about happened."""

    return _triggered(record)


def level_windows(evidence: Mapping[str, Any]) -> list[tuple[str, float, date | None, date | None]]:
    """Each declared level with the first and last session it was in force over.

    A stop raised later governs only from its own date, and the initial stop governs only
    until the eve of the raise -- unless the later stop is looser, since a stop is never
    widened and the initial one then never stopped governing. The structural invalidation
    has stood since entry. One owner, because both readers of these windows -- the audit
    that has to cover them, and the check that a handed-in record falls inside one -- would
    otherwise each have their own copy to drift from.
    """

    payload = _mapping(evidence)
    as_of = _iso_date(payload.get("as_of"))
    entry_date = _iso_date(payload.get("entry_date"))
    stop = _number(payload.get("stop_price"))
    initial_stop = _number(payload.get("initial_stop_price"))
    invalidation_price, _ = _exit_plan(payload)
    stop_effective_date = _iso_date(payload.get("stop_effective_date"))
    stop_from = stop_effective_date or entry_date
    windows = [
        (role, level, required_from, as_of)
        for role, level, required_from in (("stop", stop, stop_from), ("invalidation", invalidation_price, entry_date))
        if level is not None
    ]
    if initial_stop is not None and stop is not None and initial_stop != stop and entry_date is not None and stop_effective_date is not None:
        if stop > initial_stop:
            if stop_effective_date > entry_date:
                windows.append(("initial_stop", initial_stop, entry_date, stop_effective_date - timedelta(days=1)))
        else:
            windows.append(("initial_stop", initial_stop, entry_date, as_of))
    return windows


def supplied_price_path(evidence: Mapping[str, Any]) -> bool:
    """Whether the caller handed in the completed-bar audit itself.

    This is the one settled breach the bars cannot improve on, because it is the same record
    they would produce -- but only if it is one. A record carries the coordinates that make
    it auditable, and each of them is a way the record could be about some other request:
    which level it checked, which declared level that was, and which session it found. A
    state word on its own is an assertion wearing the shape of an audit, and it goes to the
    bars like any other assertion.

    Every coordinate is checked against what this request declared, because a record whose
    level is not the level the trader is carrying, or whose session is outside the window
    the position existed in, describes a position that is not this one -- and settling this
    request on it would skip the audit that would have found nothing.
    """

    payload = _mapping(evidence)
    path = _mapping(payload.get("completed_price_path"))
    breach_date = _iso_date(path.get("breach_date"))
    checked_level = _number(path.get("checked_level"))
    if not _triggered(path) or breach_date is None or checked_level is None:
        return False
    invalidation_price, _ = _exit_plan(payload)
    declared = {"stop": _number(payload.get("stop_price")), "initial_stop": _number(payload.get("initial_stop_price")), "invalidation": invalidation_price}
    role = path.get("governing_role")
    if declared.get(role) is None or declared[role] != checked_level:
        return False
    # The basis and the price have to agree with the role too. A record that says it read
    # closes cannot settle a stop, which is an order the tape takes out intraday; and a
    # price that never reached the level is a record of nothing having happened, wearing a
    # breached state word. Either one, taken on trust, skips the audit that would have
    # found the position still open.
    if path.get("basis") != AUDIT_BASIS[role]:
        return False
    found = _number(path.get("breach_low" if AUDIT_BASIS[role] == "completed_daily_low" else "breach_close"))
    if found is None or not crosses(role, found, checked_level):
        return False
    # Inside the window that level itself was in force over, not merely inside the position.
    # A stop cannot have been broken five days before it was placed, and an initial stop
    # cannot have been broken after a raise took it out of the market.
    for windowed_role, level, required_from, required_to in level_windows(payload):
        if windowed_role == role and level == checked_level:
            return required_from is not None and required_to is not None and required_from <= breach_date <= required_to
    return False


_POST_BREAKOUT_BLOCKS = ("key_reversal", "gaps_since_breakout", "post_breakout_behavior", "failed_volume_confirmation")
# Two ways a declared breakout is not a session these rules can hang from: no bar printed on
# it, or the history the provider returned begins after it. Either way the anchor is absent.
_UNLOCATABLE_BREAKOUT_REASONS = frozenset({"no_completed_bar_on_breakout_date", "history_starts_after_breakout_date"})


def _unlocatable_breakout(management: Mapping[str, Any]) -> str | None:
    """The reason a declared breakout cannot anchor a rule, or None when it can.

    The blocks measured from the breakout are the ones that know whether a session printed
    on it. Reading their reason keeps one answer in one place: the measurements and the
    actions cannot disagree about whether the anchor exists.
    """

    for name in _POST_BREAKOUT_BLOCKS:
        reason = _mapping(management.get(name)).get("reason")
        if reason in _UNLOCATABLE_BREAKOUT_REASONS:
            return reason
    return None


def _active(payload: Mapping[str, Any]) -> dict[str, Any]:
    as_of = _iso_date(payload.get("as_of"))
    entry = _number(payload.get("entry_price"))
    entry_date = _iso_date(payload.get("entry_date"))
    stop = _number(payload.get("stop_price"))
    initial_stop = _number(payload.get("initial_stop_price"))
    profile = payload.get("management_profile")
    management_average = payload.get("management_average")
    management = _mapping(payload.get("management"))
    trail = _mapping(management.get("moving_average_trail"))
    selected_trail = _mapping(trail.get(management_average)) if management_average in _AVERAGES else {}
    invalidation = _mapping(payload.get("invalidation"))
    invalidation_price, has_condition = _exit_plan(payload)
    declared_plan = declares_exit_plan(payload)
    # A stop raised later is only in force from its own date; the structural
    # invalidation has stood since entry.
    stop_effective_date = _iso_date(payload.get("stop_effective_date"))
    stop_from = stop_effective_date or entry_date
    protective_plan = level_windows(payload)

    # Anchors describe whether the request is a coherent position at all. A breach
    # outranks evidence nobody gathered, but never a request that contradicts itself.
    anchors: list[str] = []
    if as_of is None:
        anchors.append("as_of")
    if entry_date is None:
        anchors.append("entry_date")
    if entry_date is not None and as_of is not None and entry_date > as_of:
        anchors.append("entry_date_after_as_of")
    if stop_effective_date is not None and entry_date is not None and stop_effective_date < entry_date:
        anchors.append("stop_effective_date_before_entry_date")
    if stop_effective_date is not None and as_of is not None and stop_effective_date > as_of:
        anchors.append("stop_effective_date_after_as_of")
    if not declared_plan:
        anchors.append("stop_or_invalidation")
    if initial_stop is not None and entry is not None and initial_stop >= entry:
        # Initial risk is entry minus the initial stop; a stop at or above entry leaves none.
        anchors.append("initial_stop_price")
    if initial_stop is not None and stop is not None and initial_stop != stop and stop_effective_date is None:
        # A stop that differs from the one the trade started with was raised on some date,
        # and without it the raised level would be audited back to entry.
        anchors.append("stop_effective_date")
    if profile is not None and profile not in _PROFILES:
        anchors.append("management_profile")
    if management_average is not None and management_average not in _AVERAGES:
        anchors.append("management_average")

    live_stop = _mapping(payload.get("live_stop"))
    live_triggered = bool(payload.get("live_stop_check")) and live_stop.get("partial_session") is True and _triggered(live_stop) and stop is not None
    current = _number(payload.get("current_price"))
    completed_price_path = _mapping(payload.get("completed_price_path"))
    path_state = _status_word(completed_price_path)
    # An asserted breach is the caller telling the harness what the tape did, and it can only
    # be asserted about a level the caller declared: "the stop was hit" with no stop declared
    # names no level, and an invalidation plan cannot stand in for one.
    asserted_stop = (_triggered(payload.get("completed_stop")) or _triggered(payload.get("stop_event"))) and stop is not None
    # A path handed in without the coordinates that make it an audit was moved here: it says
    # the position ended and nothing more, which is what an assertion is.
    asserted_path = _triggered(payload.get("asserted_price_path"))
    asserted_stop = asserted_stop or asserted_path
    completed_stop = asserted_stop or _triggered(completed_price_path) or (current is not None and stop is not None and crosses("stop", current, stop))
    invalidation_price_breach = (current is not None and invalidation_price is not None and crosses("invalidation", current, invalidation_price)) or (
        _triggered(completed_price_path) and completed_price_path.get("governing_role") == "invalidation"
    )
    invalidation_triggered = _triggered(invalidation) or invalidation_price_breach
    # Two completed closes below the average the trader declared they manage by is
    # that trader's own exit plan breached, audited over completed bars like a stop.
    trail_breached = _status_word(selected_trail) == "breached"
    breached = live_triggered or completed_stop or invalidation_triggered or trail_breached

    # An assertion outranks evidence nobody gathered. It does not outrank evidence that was
    # gathered about the same levels and says the opposite: a completed breach asserted
    # beside an audit that cleared every declared level over its whole window is a request
    # contradicting itself, and neither half of it can be published as a verdict.
    if asserted_stop and protective_plan:
        records = _audit_records(completed_price_path, path_state)
        if path_state == "clear" and all(_audited(records, role, level, required_from, required_to) for role, level, required_from, required_to in protective_plan):
            anchors.append("asserted_breach_contradicted_by_completed_bars")

    gaps: list[str] = []
    if not breached:
        if entry is None:
            # Entry economics decide 3R protection, never whether a level was breached.
            gaps.append("entry_price")
        if current is None:
            gaps.append("current_price")
        if declared_plan and not protective_plan:
            # A condition nobody can evaluate against completed bars, or a price that
            # is not a price, leaves nothing for the audit to clear.
            gaps.append("auditable_protective_level")
        if protective_plan:
            records = _audit_records(completed_price_path, path_state)
            if path_state != "clear" or not all(_audited(records, role, level, required_from, required_to) for role, level, required_from, required_to in protective_plan):
                gaps.append("completed_price_path")
        if invalidation_price is None and has_condition:
            # HOLD asserts nothing has invalidated the thesis; an exit condition the
            # harness never evaluated cannot be part of that assertion.
            gaps.append("invalidation_condition_not_audited")
        if management_average in _AVERAGES and _status_word(selected_trail) != "clear":
            # The declared average is an exit plan; a HOLD cannot stand on one the bars
            # could not read, any more than on an unaudited stop.
            gaps.append("management_average_trail")

    breakeven_at_r = doctrine.threshold(_PROFIT_PROTECTION, "breakeven_protection_trigger_r")
    controls: dict[str, Any] = {
        "breakeven_at_r": breakeven_at_r,
        # Nothing, until the excursion is measured. `False` here would say protection was
        # not required about a position whose favorable excursion nobody read -- a SELL and
        # an INCOMPLETE never enter the block below, and inside it a position with no
        # measurable initial risk does not reach the gate either. Its two companions below
        # already say "not measured" the way this block says it everywhere else.
        "breakeven_protection_required": None,
        "initial_risk": None,
        "initial_risk_basis": None,
        "r_multiple_reached": None,
        "favorable_excursion_basis": None,
    }
    # Measurements beside the position that prescribe nothing. The structural blocks
    # travel with every verdict -- a SELL on the declared average needs its breach shown --
    # and the strength references are filled under HOLD.
    management_evidence: dict[str, Any] = {
        key: management[key]
        for key in (
            "moving_average_trail",
            "twenty_day_average",
            "largest_decline_since_stage2_start",
            "base_extension",
            "moving_average_extension",
            "key_reversal",
            "gaps_since_breakout",
            "climax",
            "failed_volume_confirmation",
            "post_breakout_behavior",
            "stage3_transition",
        )
        if key in management
    }
    management_evidence.update(_context_blocks(payload, as_of=as_of, entry=entry))
    if management_average in _AVERAGES:
        # The average is TraderLion's; what makes two closes below it end the position is the
        # trader having declared it as their exit plan, which is a contract of this harness
        # rather than a mined gate. The measurement keeps its own claim beside it so a reader
        # can see whose number was measured and whose rule executed.
        management_evidence["declared_exit_plan"] = {
            "doctrine_id": _DECLARED_PLAN,
            "binds": doctrine.binds(_DECLARED_PLAN),
            "declared": management_average,
            "measurement_doctrine_id": _ROLES,
            "measurement_binds": doctrine.binds(_ROLES),
            "measurement_source": "[TL]",
            "state": _status_word(selected_trail) or "unavailable",
        }
    # What to do while holding. SELL leaves nothing to manage and INCOMPLETE has not
    # established that there is a position to manage, so only HOLD fills this.
    actions: list[dict[str, Any]] = []
    reasons: list[str] = []
    if anchors:
        verdict = "INCOMPLETE"
        missing = anchors + gaps

    elif breached:
        verdict = "SELL"
        missing = []
        # A path that names the level it is about decides the word: when one price is under
        # both an invalidation and a stop, the trade ended at the line it crossed first, and
        # the failure has to be reported under that line.
        path_names_invalidation = _triggered(completed_price_path) and completed_price_path.get("governing_role") == "invalidation"
        default = (
            "live_stop_breach"
            if live_triggered
            else "invalidation_breach"
            if path_names_invalidation
            else "completed_stop_breach"
            if completed_stop
            else "invalidation_triggered"
            if _triggered(invalidation)
            else "invalidation_breach"
            if invalidation_triggered
            else "management_average_exit"
        )
        # Two exits can both have happened, and the position ended at the first of them: a
        # stop print three weeks after the declared average already closed the trade is a
        # level a position that no longer existed could not have reached. Where the evidence
        # carries dates, the earliest dated exit names the failure; where it does not, the
        # order above stands.
        # Two exits on one session did not happen at the same moment. A stop resting in the
        # market is taken out the moment the Low reaches it, and a live breach is a session
        # still in progress; a close below an average, and a level read from the close, are
        # settled at the bell. So each dated exit carries when inside the session it
        # happened, and the word is the last tiebreak rather than the first.
        # And within one moment, what the bars measured names it before what the caller
        # asserted about the same session: the assertion says a level was hit, the audit
        # says which session's price hit which level.
        intraday, at_the_close, measured, asserted = 0, 1, 0, 1
        dated = [
            (day, moment, source, word)
            for day, moment, source, word in (
                (
                    _iso_date(completed_price_path.get("breach_date")),
                    intraday if completed_price_path.get("basis") == "completed_daily_low" else at_the_close,
                    measured,
                    "invalidation_breach" if path_names_invalidation else "completed_stop_breach",
                ),
                (_iso_date(selected_trail.get("breach_date")) if trail_breached else None, at_the_close, measured, "management_average_exit"),
                # A live breach is a partial session, which is today, and it is happening
                # while the session runs rather than at its close.
                (as_of if live_triggered else None, intraday, asserted, "live_stop_breach"),
            )
            if day is not None
        ]
        reasons = [min(dated)[3] if len(dated) > 1 else default]
    elif gaps:
        verdict = "INCOMPLETE"
        missing = gaps
    else:
        verdict = "HOLD"
        missing = []
        # Three R is measured from the furthest the position got, not from where it
        # happens to be: a gain that was reached and given back is exactly the loss the
        # rule exists to prevent. The highest completed High since entry is that
        # measurement; without it, the last close is the floor of what was reached.
        max_high = _number(payload.get("max_high_since_entry"))
        reached = [(price, basis) for price, basis in ((max_high, "max_high_since_entry"), (current, "current_price")) if price is not None]
        # R is a multiple of the risk the trade started with. A stop raised since then is
        # not that risk, so a raised stop needs the initial one declared or R goes unmeasured.
        initial_risk: float | None = None
        if entry is not None and initial_stop is not None:
            initial_risk = entry - initial_stop
            controls["initial_risk_basis"] = "initial_stop_price"
        elif entry is not None and stop is not None and stop < entry and (stop_effective_date is None or stop_effective_date == entry_date):
            initial_risk = entry - stop
            controls["initial_risk_basis"] = "stop_price"
        if initial_risk is not None:
            controls["initial_risk"] = round(initial_risk, _REPORTED_PRECISION)
        if entry is not None and initial_risk is not None and reached:
            price, basis = max(reached, key=lambda item: item[0])
            r_multiple = (price - entry) / initial_risk
            controls["r_multiple_reached"] = _reported_beside_gate(r_multiple, _PROFIT_PROTECTION, "breakeven_protection_trigger_r")
            controls["favorable_excursion_basis"] = basis
            # Measured, so the answer is a yes or a no rather than a gap: three R short of
            # the trigger, or reached with the stop already standing above entry, are both
            # nothing left to require.
            controls["breakeven_protection_required"] = False
            if stop is not None and stop < entry and doctrine.evaluate_gate(_PROFIT_PROTECTION, "breakeven_protection_trigger_r", r_multiple)["state"] == "pass":
                controls["breakeven_protection_required"] = True
                evidence = {"r_multiple_reached": controls["r_multiple_reached"], "measured_from": basis}
                placeable = current is None or entry < current
                if placeable:
                    actions.append({"action": "RAISE_STOP", "doctrine_id": _PROFIT_PROTECTION, "to_at_least": entry, "evidence": evidence})
                else:
                    # Price has already come back through breakeven. A stop ordered above the
                    # last completed close is not a stop -- it is a sale this harness never
                    # said it was making -- so the protection that was missed is reported and
                    # not ordered. The same placeability rule the market-defense action uses.
                    controls["breakeven_protection_not_placeable"] = {
                        **evidence,
                        "to_at_least": entry,
                        "current_price": current,
                        "reason": "breakeven_is_above_the_current_price",
                    }
        if profile == "tl_stage12" and entry is not None and reached:
            price, basis = max(reached, key=lambda item: item[0])
            gain_pct = (price - entry) / entry * 100
            signal = doctrine.evaluate_gate(_TL_HALF_AT_FIVE, "half_sale_profit_pct", gain_pct)
            if signal["state"] == "contrast_pass":
                evidence = {"gain_pct_reached": _reported_beside_gate(gain_pct, _TL_HALF_AT_FIVE, "half_sale_profit_pct"), "measured_from": basis, "state": signal["state"]}
                tagged = {"doctrine_id": _TL_HALF_AT_FIVE, "binds": False, "source": "[TL]", "evidence": evidence}
                actions.append({"action": "REDUCE", **tagged, "fraction": doctrine.parameter(_TL_HALF_AT_FIVE, "half_sale_fraction")})
                # The rule is a pair. A position holding a stop at or above entry has the
                # breakeven half already; one with no declared stop at all is told to set it.
                if stop is None or stop < entry:
                    # The same placeability rule the 3R protection uses: a stop ordered above
                    # the last completed close is a sale this harness never said it was
                    # making. Price back through breakeven means the half was missed, and
                    # the record says so instead of ordering it.
                    if current is None or entry < current:
                        actions.append({"action": "RAISE_STOP", **tagged, "to_at_least": entry})
                    else:
                        controls["breakeven_protection_not_placeable"] = {
                            **evidence,
                            "to_at_least": entry,
                            "current_price": current,
                            "reason": "breakeven_is_above_the_current_price",
                        }
        # Structure that deteriorated while the stop held. The average the trader did not
        # declare is review evidence; the one they declared is a SELL above and never here.
        for name in _AVERAGES:
            record = _mapping(trail.get(name))
            if name != management_average and _status_word(record) == "breached":
                actions.append({"action": "REVIEW", "doctrine_id": _ROLES, "binds": doctrine.binds(_ROLES), "source": "[TL]", "reason": f"two_closes_below_{name}", "evidence": record})
        twenty = _mapping(management.get("twenty_day_average"))
        # The source's sentence begins "Once the stock successfully breaks out", so the rule
        # belongs to a position that broke out. Without a declared breakout the measurement
        # is published and nothing acts: an early or cheat entry has not reached this rule yet.
        # A date the caller typed is not a breakout the bars can find. When the measurements
        # report that no completed session printed on it -- a weekend, a holiday, a gap in
        # the history -- the anchor these rules hang from does not exist, and acting on it
        # would be acting on a session nobody traded.
        breakout_withheld = _unlocatable_breakout(management) if payload.get("breakout_date") is not None else "breakout_date_not_declared"
        breakout_declared = breakout_withheld is None
        if _status_word(twenty) == "below":
            if breakout_declared:
                actions.append({"action": "REVIEW", "doctrine_id": _TWENTY_DAY, "binds": doctrine.binds(_TWENTY_DAY), "reason": "close_below_20_day_average", "evidence": twenty})
            else:
                # Withheld, and said so: a reader must be able to see that the measurement is
                # below the average and that the rule about it has not been applied.
                management_evidence["twenty_day_average"] = {**twenty, "action_withheld_reason": breakout_withheld}
        largest = _mapping(management.get("largest_decline_since_stage2_start"))
        daily = _mapping(largest.get("daily"))
        weekly = _mapping(largest.get("weekly"))
        if daily.get("last_session_is_largest") is True or weekly.get("latest_completed_week_is_largest") is True:
            # The source says "in most cases" and names no formula for overwhelming volume,
            # so this is the chart's question, with the measurement beside it.
            actions.append(
                {
                    "action": "REVIEW",
                    "doctrine_id": _LARGEST_DECLINE,
                    "binds": doctrine.binds(_LARGEST_DECLINE),
                    "reason": "largest_decline_since_stage2_start",
                    "needs_chart": True,
                    "evidence": {"stage2_start": largest.get("stage2_start"), "daily": daily, "weekly": weekly},
                }
            )
        base_extension = _mapping(management.get("base_extension"))
        inside_pause_zone = _mapping(base_extension.get("band")).get("state") == "within_source_range"
        if inside_pause_zone and not breakout_declared:
            # An extension over the base top is measurable the moment the top is declared, but
            # the pause it describes is one a stock takes after it has broken out. Ordering a
            # review off it without a declared breakout reads post-breakout doctrine into an
            # entry that has not broken out yet, the same leak the 20-day rule had.
            management_evidence["base_extension"] = {**base_extension, "action_withheld_reason": breakout_withheld}
        elif inside_pause_zone:
            # Inside the zone the source describes is where the pause is likely and where a
            # swing trader may take some or all off; past it the stock has continued.
            actions.append({"action": "REVIEW", "doctrine_id": _PAUSE_ZONE, "binds": doctrine.binds(_PAUSE_ZONE), "source": "[TL]", "reason": "base_extension_pause_zone", "evidence": base_extension})
        failed_volume = _mapping(management.get("failed_volume_confirmation"))
        if failed_volume.get("selling_volume_exceeded_breakout_volume") is True:
            # The source says "sell or at least reduce", so the action names both and chooses
            # neither. What the bars settled is only that the selling session traded heavier
            # than the breakout session against one baseline; whether either was "low" or
            # "high" volume is a boundary the source never drew, so the action carries both
            # unresolved qualities and asks for the chart rather than claiming the sentence.
            # What the bars settled is the comparison and nothing else: this selling session
            # traded heavier than the breakout session against one baseline. The source's
            # pattern is a low-volume breakout followed by high-volume selling, and neither
            # "low" nor "high" has a boundary anywhere in the corpus -- so the action is
            # named after the comparison it made, and does not borrow the source's "sell or
            # at least reduce" for a pattern the evidence beside it says was not established.
            actions.append({"action": "REVIEW", "doctrine_id": _FAILED_VOLUME, "binds": doctrine.binds(_FAILED_VOLUME), "reason": "selling_volume_exceeded_breakout_volume", "needs_chart": True, "unresolved_criteria": failed_volume.get("qualitative_conditions_unresolved"), "evidence": failed_volume})
        defense = _mapping(management_evidence.get("market_defense"))
        tightened = _mapping(defense.get("difficult_market_band")).get("state")
        if defense.get("market_state") in _DIFFICULT_MARKET and defense.get("tighten_to_is_placeable") and tightened == "above_source_range":
            # The source's answer to a difficult tape is a tighter stop and smaller targets,
            # not a sale: "I don't usually sell everything on my opinion of the market."
            # A stop already inside the tightened range needs nothing, and this can never sell.
            actions.append(
                {
                    "action": "RAISE_STOP",
                    "doctrine_id": _MARKET_DEFENSE,
                    "binds": doctrine.binds(_MARKET_DEFENSE),
                    "reason": "market_defense_tightens_stops",
                    "to_at_least": defense["tighten_to"],
                    "evidence": defense,
                }
            )
        earnings = _mapping(management_evidence.get("earnings"))
        if earnings.get("ahead") is True or earnings.get("due_on_as_of") is True:
            actions.append(
                {
                    "action": "REVIEW",
                    "doctrine_id": _EARNINGS,
                    "binds": doctrine.binds(_EARNINGS),
                    "reason": "earnings_ahead" if earnings.get("ahead") else "earnings_due_on_as_of",
                    "evidence": earnings,
                }
            )
        # Reference points for selling into strength. The source names the trader's own
        # average gain and R multiples and gives neither a multiple nor a fraction, so this
        # reports distances and prescribes nothing.
        average_gain = _number(payload.get("average_gain_pct"))
        return_pct = (current - entry) / entry * 100 if current is not None and entry is not None else None
        max_return_pct = (max_high - entry) / entry * 100 if max_high is not None and entry is not None else None
        management_evidence["strength_references"] = {
            "doctrine_id": _STRENGTH_REFERENCES,
            "binds": doctrine.binds(_STRENGTH_REFERENCES),
            "return_pct": _reported(return_pct),
            "max_return_pct": _reported(max_return_pct),
            "r_multiple": _reported((current - entry) / initial_risk if current is not None and entry is not None and initial_risk else None),
            "max_r_multiple": _reported((max_high - entry) / initial_risk if max_high is not None and entry is not None and initial_risk else None),
            "average_gain_pct": average_gain,
            "distance_to_average_gain_pct": _reported(return_pct - average_gain if return_pct is not None and average_gain is not None else None),
        }
    return {
        "mode": "active",
        "verdict": verdict,
        "risk_controls": controls,
        "base_count_context": _base_count_context(payload),
        "management_actions": actions,
        # The measurements are keyed to a position the request never established -- windows
        # from an entry date that is missing, impossible, or unaudited. Every INCOMPLETE
        # drops them, not only the one the anchors caught. A SELL keeps its evidence,
        # because there the position was real and the structure explains the exit.
        "management_evidence": {} if verdict == "INCOMPLETE" else management_evidence,
        "completed_price_path": completed_price_path or None,
        "failed": reasons,
        "missing": missing,
        "waiting": [],
    }


def reduce_risk(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Return the only final verdict: prospective or active, from evidence objects."""

    payload = _mapping(evidence)
    return _active(payload) if payload.get("mode") == "active" else _prospective(payload)
