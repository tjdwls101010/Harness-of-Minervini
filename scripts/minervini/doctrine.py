"""Read the normalized doctrine registry without exposing source prose as runtime rules."""

from __future__ import annotations

import builtins
import json
import math
import re
from collections.abc import Iterable, Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any


_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "doctrine" / "claims.json"
_CLAIM_FIELDS = (
    "id",
    "title",
    "kind",
    "layer",
    "status",
    "context",
    "required_inputs",
    "rule",
    "thresholds",
    "computability",
    "failure",
    "missing",
    "precedence",
    "quarantine",
    "consumers",
)
# Present only where they mean something, and dropped from the runtime claim when absent.
_OPTIONAL_CLAIM_FIELDS = ("attributed_to", "out_of_scope", "unquantified", "disagrees_with", "parameters")
_REQUIRED_FIELDS = frozenset((*_CLAIM_FIELDS, "provenance", "tests"))
_VALID_COMPUTABILITY = frozenset({"deterministic", "chart_assisted", "judgment_only"})
_VALID_OUT_OF_SCOPE = frozenset({"position_sizing"})
_VALID_DIRECTIONS = frozenset({"lower_is_better", "higher_is_better", "inside_is_better"})
# Enough places to strip binary-float noise from a reported figure and far too many to
# soften any limit the registry states.
_REPORTED_PRECISION = 10
# Fractional places in the widest decimal expansion a binary64 has: the smallest subnormal's.
_WIDEST_DECIMAL_EXPANSION = 1074
# Every threshold a reducer reads by name. A registry that no longer supplies one of
# these validates cleanly today and raises KeyError mid-verdict tomorrow, so the
# dependency is declared here where validation can see it.
REQUIRED_THRESHOLDS = (
    ("eligibility.standard_trend_template", "sma_200_rising_minimum_months", "gate"),
    ("eligibility.standard_trend_template", "minimum_pct_above_52_week_low", "gate"),
    ("eligibility.standard_trend_template", "maximum_pct_below_52_week_high", "gate"),
    ("eligibility.standard_trend_template", "relative_strength_minimum", "gate"),
    ("eligibility.recent_ipo_primary_base", "minimum_trading_history_sessions", "gate"),
    ("eligibility.recent_ipo_primary_base", "minimum_base_duration_sessions", "gate"),
    ("eligibility.recent_ipo_primary_base", "three_week_base_depth_pct", "gate"),
    ("eligibility.recent_ipo_primary_base", "three_to_five_week_base_depth_pct", "band"),
    ("eligibility.recent_ipo_primary_base", "base_depth_ceiling_pct", "gate"),
    ("eligibility.recent_ipo_primary_base", "year_long_correction_depth_pct", "gate"),
    ("eligibility.recent_ipo_primary_base", "year_long_exception_minimum_duration_sessions", "gate"),
    ("risk.initial_stop_and_reward", "initial_stop_ceiling_pct", "gate"),
    ("risk.initial_stop_and_reward", "ordinary_loss_target_pct", "band"),
    ("risk.initial_stop_and_reward", "half_average_gain_multiple", "gate"),
    ("risk.initial_stop_and_reward", "reward_to_risk_minimum", "gate"),
    ("risk.initial_stop_and_reward", "reward_to_risk_preferred", "reference"),
    ("risk.profit_protection_at_3r", "breakeven_protection_trigger_r", "gate"),
)
# This module publishes a function named `list`, so the builtin type is shadowed from
# its definition onward. Type checks below reach it through `builtins` on purpose.
_VALID_KINDS = frozenset({"constitution", "hard_gate", "default", "tactic", "interpretation", "exception", "quarantine"})
_VALID_LAYERS = frozenset({"canonical", "practice", "harness"})
_VALID_ROLES = frozenset({"gate", "band", "marker", "reference"})
_COMPARATORS = {
    "<=": lambda measured, limit: measured <= limit,
    ">=": lambda measured, limit: measured >= limit,
    "<": lambda measured, limit: measured < limit,
    ">": lambda measured, limit: measured > limit,
}
_VALID_CORPORA = frozenset({"Minervini", "TraderLion"})
_MINIMUM_QUOTATION_LENGTH = 20
# The one rule whose rejection is about this harness's own request contract rather than a
# market judgment: an early entry without its confirmation debt is a malformed setup, not a
# stock that failed somebody's standard.
_HARNESS_CONTRACT_REJECTIONS = frozenset({"tactic.early_entry_confirmation_debt"})


@lru_cache(maxsize=1)
def _load_registry() -> dict[str, Any]:
    with _REGISTRY_PATH.open(encoding="utf-8") as registry_file:
        return json.load(registry_file)


def _runtime_claim(record: dict[str, Any]) -> dict[str, Any]:
    claim = {field: record[field] for field in _CLAIM_FIELDS}
    claim.update({field: record[field] for field in _OPTIONAL_CLAIM_FIELDS if field in record})
    return claim


def _result(record: dict[str, Any]) -> dict[str, Any]:
    return {"claim": _runtime_claim(record), "provenance": record["provenance"]}


def has_claim(claim_id: str) -> bool:
    """Whether the registry holds this claim.

    A citation nobody can look up is worse than no citation: it reads as doctrine while
    leading a reader nowhere, and evidence arriving from a caller can name anything.
    """

    return any(record["id"] == claim_id for record in _load_registry()["claims"])


def get_claim(claim_id: str) -> dict[str, Any]:
    """Return one claim and its audit provenance as separate objects.

    Raises:
        KeyError: If ``claim_id`` is not registered.
    """
    for record in _load_registry()["claims"]:
        if record["id"] == claim_id:
            return _result(record)
    raise KeyError(f"unknown doctrine claim: {claim_id}")


def list(
    *,
    context: str | None = None,
    include_quarantined: bool = False,
) -> list[dict[str, Any]]:
    """List runtime claims, optionally narrowed to one analysis context.

    Quarantined records are audit material and are excluded unless explicitly
    requested.  Every returned item keeps the executable claim separate from
    its provenance metadata.
    """
    records: Iterable[dict[str, Any]] = _load_registry()["claims"]
    if context is not None:
        records = (record for record in records if context in record["context"])
    if not include_quarantined:
        records = (record for record in records if not record["quarantine"]["is_quarantined"])
    return [_result(record) for record in records]


def threshold(claim_id: str, name: str) -> Any:
    """Return one registered numeric threshold.

    Reducers read their numbers here rather than holding literals, so the value a
    verdict used and the value the registry cites are the same object. A name the
    registry does not define raises instead of defaulting: a threshold nobody
    registered is a threshold nobody sourced.

    Raises:
        KeyError: If ``claim_id`` is unknown or does not register ``name``.
    """
    claim = get_claim(claim_id)["claim"]
    _readable(claim, claim_id)
    thresholds = claim["thresholds"]
    if name not in thresholds:
        raise KeyError(f"{claim_id} registers no threshold named {name}")
    specification = thresholds[name]
    role = specification["role"]
    # A raw number is one comparison away from a verdict, so the kinds of number whose
    # meaning is positional do not come out of here at all: a band leaves through
    # `evaluate_band` and a marker through `evaluate_marker`, each carrying where the
    # measurement sat. Binding is checked only for gates, because only a gate could decide
    # anything; a reference is never compared with a measurement, so reading one raw is how
    # a window length reaches the code that computes the series it names.
    if role in {"marker", "band"}:
        evaluator = "evaluate_marker" if role == "marker" else "evaluate_band"
        raise ValueError(f"{claim_id}.{name} is a {role}; read it through {evaluator} so where the measurement sits travels with it")
    if role == "gate" and not _binds(claim):
        raise ValueError(f"{claim_id}.{name} is not binding on this harness; read it through evaluate_gate so it is stamped as contrast")
    return specification["value"]


def parameter(claim_id: str, name: str) -> Any:
    """Return one registered algorithm parameter.

    A parameter is not a threshold and this seam is not `threshold()`. A threshold is compared
    with a measurement; a parameter chooses which measurement exists before any comparison
    happens, so none of the four roles fits it and pretending one did would have made the
    registry describe it wrongly. Keeping the two seams apart means neither can answer for the
    other by accident.

    Raises:
        KeyError: If ``claim_id`` is unknown or does not register ``name`` as a parameter.
    """
    claim = get_claim(claim_id)["claim"]
    _readable(claim, claim_id)
    parameters = claim.get("parameters") or {}
    if name not in parameters:
        raise KeyError(f"{claim_id} registers no parameter named {name}")
    return parameters[name]["value"]


def _readable(record: Mapping[str, Any], claim_id: str) -> None:
    """Refuse to hand back a number this harness is not permitted to act on."""

    exclusion = record.get("out_of_scope")
    if exclusion:
        raise ValueError(f"{claim_id} is recorded {exclusion} and is audit material; no capability may read its numbers")


def _specification(claim_id: str, name: str, expected_role: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """One threshold, the claim it belongs to, and the quotation it cites.

    Reading a band as a gate is how a range the source hedged becomes a cliff it never
    drew, so the mismatch raises here rather than producing a plausible verdict. The claim
    travels back with the threshold because whose standard this is decides what the
    evaluation is allowed to say, and looking it up twice invites the two answers to drift.
    """
    record = get_claim(claim_id)
    _readable(record["claim"], claim_id)
    specification = record["claim"]["thresholds"].get(name)
    if specification is None:
        raise KeyError(f"{claim_id} registers no threshold named {name}")
    if specification["role"] != expected_role:
        raise ValueError(f"{claim_id}.{name} is registered as a {specification['role']}, not a {expected_role}")
    return specification, record["claim"], record["provenance"]["quotations"][specification["quote_index"]]


def _measurable(measured: float | None) -> tuple[float | None, str | None]:
    """A non-finite measurement is a measurement nobody made.

    NaN compares false against every limit, so a gate reading it would publish "fail" --
    a verdict word -- for an arithmetic accident, and infinity would publish a real
    failure for a division that ran out of numbers. Both become the unavailable state the
    harness already has for evidence it does not hold, with the reason naming which of the
    two it was so a reader can tell an unmeasured input from a measurement that broke.
    """

    if measured is None:
        return None, None
    if isinstance(measured, bool) or not isinstance(measured, (int, float)):
        return None, "measurement_not_a_number"
    if not math.isfinite(float(measured)):
        return None, "measurement_not_finite"
    return measured, None


def evaluate_gate(claim_id: str, name: str, measured: float | None) -> dict[str, Any]:
    """Compare a measurement with a limit the source states as a filter.

    A gate has no proximity language on purpose. Its whole job is to be unarguable,
    and a stop that is "basically ten percent" is the negotiation the risk spine exists
    to forbid.
    """
    specification, claim, _ = _specification(claim_id, name, "gate")
    measured, unmeasurable = _measurable(measured)
    limit = specification["value"]
    comparator = specification["comparator"]
    binds = _binds(claim)
    signal: dict[str, Any] = {
        "id": f"{claim_id}.{name}",
        "doctrine_id": claim_id,
        "role": "gate",
        "binds": binds,
        "measured": measured,
        "unit": specification["unit"],
        "required": f"{comparator} {limit}",
    }
    attribution = claim.get("attributed_to")
    if attribution is not None:
        signal["attributed_to"] = attribution
    if measured is None:
        signal["state"] = "unavailable"
        if unmeasurable is not None:
            signal["reason"] = unmeasurable
    else:
        passed = _COMPARATORS[comparator](measured, limit)
        # A non-binding gate is a real filter belonging to someone the harness reads for
        # contrast. Reporting it as "pass"/"fail" would let a reducer that scans states
        # generically hand another practitioner's standard a verdict this harness owes to
        # Minervini's, so the contrast words say the same thing in vocabulary no verdict
        # can consume.
        signal["state"] = ("pass" if passed else "fail") if binds else ("contrast_pass" if passed else "contrast_fail")
    return signal


def _binds(record: Mapping[str, Any]) -> bool:
    """Whether this claim's filter is the one the harness itself applies.

    Attribution is required on the canonical layer precisely so this reads a statement
    rather than a silence: an earlier version treated a missing name as the house voice,
    and deleting one line from Ryan's claim made his standard bind.
    """

    layer = record.get("layer")
    if layer == "harness":
        # The harness's own operating rules are this harness's, by definition. What they may
        # not do is reject without being named, which `validate` enforces separately.
        return True
    return layer == "canonical" and record.get("attributed_to") == "Minervini"


def binds(claim_id: str) -> bool:
    """Whether this harness applies the claim, or reads it for contrast.

    Public because reducers and evidence builders both need the answer, and an answer this
    load-bearing must have one owner.
    """
    return _binds(get_claim(claim_id)["claim"])


def evaluate_marker(claim_id: str, name: str, measured: float | None) -> dict[str, Any]:
    """Report a measurement beside a value the source named but never made a filter.

    "About half (plus or minus a reasonable amount)" names 0.5 and then declines to say
    where half stops being half. Compiling that into a comparison would draw the boundary
    the author refused to draw, so this reports the distance and leaves the reading to
    the analyst. Its state word is deliberately outside the pass/fail/wait vocabulary the
    reducers branch on.
    """
    specification, _, quotation = _specification(claim_id, name, "marker")
    measured, unmeasurable = _measurable(measured)
    value = specification["value"]
    signal: dict[str, Any] = {
        "id": f"{claim_id}.{name}",
        "doctrine_id": claim_id,
        "role": "marker",
        "measured": round(measured, _REPORTED_PRECISION) if isinstance(measured, float) else measured,
        "unit": specification["unit"],
        "source_value": value,
        "exact": specification["exact"],
        "quotation": quotation["text"],
        "distance": None,
        "state": "unavailable",
    }
    if measured is not None:
        signal["distance"] = round(measured - value, _REPORTED_PRECISION)
        signal["state"] = "reported"
    elif unmeasurable is not None:
        signal["reason"] = unmeasurable
    return signal


def _band_position(value: float) -> float:
    """Round the position for a reader without moving it somewhere it is not.

    Four places is the right resolution for a person reading where a base sat in its range,
    and it is the wrong resolution near the edges, in both directions. A measurement a
    millionth of a span above the high edge is genuinely above it and rounds to exactly 1.0;
    a stop of 6.0000000001% is genuinely inside 6-7% and rounds to exactly 0.0. Either way
    the position and the state end up saying different things about one number, and reporting
    an edge is the specific claim that the measurement sat on it. Widening the field to ten
    places everywhere would only move the collision inward, so the position instead keeps
    where it actually is and spends extra places only where four would erase the distinction.

    Rounding cannot carry a value across an edge -- rounding a negative never yields a
    positive -- so landing on one is the only way to lose where the value was, and that is
    the whole condition.

    A position that is on an edge is answered before the loop rather than inside it, so every
    value the loop sees is one that some number of places reports off the edges -- every
    finite float has a finite decimal expansion, and the widest a double can have is the
    smallest subnormal's. Bounding the search there rather than looping until convinced costs
    one line and means a later edit to the condition cannot turn this into a hang. Ordinary
    positions pay for one rounding and stop.
    """
    if value in (0.0, 1.0):
        return value
    for places in range(4, _WIDEST_DECIMAL_EXPANSION + 1):
        rounded = round(value, places)
        if rounded not in (0.0, 1.0):
            return rounded
    return value  # unreachable for a finite value, and still the honest answer if reached


def evaluate_band(claim_id: str, name: str, measured: float | None) -> dict[str, Any]:
    """Say where a measurement sat against a range the source gave as a range.

    Where it sat, not whether it belongs: the state is positional and ``direction`` is what
    names the good edge, because a base shallower than its depth range is outside it and
    better for being outside while a company growing slower than its growth range is outside
    it and worse. ``band_position`` exists because 26 and 34.9 are not the same picture even
    though both sit inside 25-35, and a bare pass/fail throws that difference away. Everything
    the signal says about position is computed from the value it publishes rather than the one
    it was handed, so a reader holding only the envelope can check it. The quotation travels
    with the signal so the response can cite what it is reading.
    """
    specification, _, quotation = _specification(claim_id, name, "band")
    measured, unmeasurable = _measurable(measured)
    low, high = specification["range"]
    if high <= low:
        # validate() refuses both of these at registration, so reaching one means a registry
        # nobody ran the validator over. A range with no width has no position to divide into
        # and an inverted one has a negative span, which would silently mirror every reading.
        # Say which band and why rather than letting the arithmetic fail anonymously.
        shape = "has no width" if high == low else "is inverted"
        raise ValueError(
            f"{claim_id}.{name} is a band whose range {shape}; a position in it is undefined"
        )
    signal: dict[str, Any] = {
        "id": f"{claim_id}.{name}",
        "doctrine_id": claim_id,
        "role": "band",
        # Rounded for the reader, exactly as a gate reports -- and every comparison below
        # reads this rounded value rather than the raw one, so the number the envelope shows
        # and the state beside it can never disagree.
        "measured": round(measured, _REPORTED_PRECISION) if isinstance(measured, float) else measured,
        "unit": specification["unit"],
        "source_range": [low, high],
        "exact": specification["exact"],
        "quotation": quotation["text"],
    }
    if measured is None:
        signal["state"] = "unavailable"
        if unmeasurable is not None:
            signal["reason"] = unmeasurable
        return signal
    span = high - low
    # Everything below reads the number the envelope prints, not the one this was handed.
    # A 20% decline computed from 10.10 to 8.08 is 19.999999999999996, which prints as 20.0
    # against a range starting at 20 -- comparing the raw value there emits a signal saying a
    # measurement of 20.0 fell below 20, and a reader who can only see the printed number has
    # no way to tell that is arithmetic rather than a mistake. Ten decimal places is far below
    # any precision price data carries, so agreeing with the print costs nothing real.
    reported = signal["measured"]
    signal["band_position"] = _band_position((reported - low) / span)
    # The state says where the number sat and nothing else. Which edge is the good one is
    # what ``direction`` is for -- a base shallower than its depth range is outside it and
    # better for being outside; a company growing slower than its growth range is outside it
    # and worse. Folding that judgement into the state made the favourable side report
    # ``within_source_range`` about a measurement that never entered the range, which is a
    # sentence the response standard cannot be written from. The words are positional for the
    # same reason: "short of" and "beyond" carry a higher-is-better frame, and half the
    # registered bands point the other way.
    signal["direction"] = specification["direction"]
    if reported > high:
        signal["state"] = "above_source_range"
    elif reported < low:
        signal["state"] = "below_source_range"
    else:
        signal["state"] = "within_source_range"
    return signal


def validate(registry: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Validate the registry's public contract and executable-claim coverage."""
    registry = _load_registry() if registry is None else registry
    errors: list[str] = []
    claim_ids: set[str] = set()
    precedence_order = set(registry.get("precedence_order", []))

    if not isinstance(registry.get("schema_version"), str):
        errors.append("registry.schema_version must be a string")
    if not precedence_order:
        errors.append("registry.precedence_order must not be empty")

    for index, record in enumerate(registry.get("claims", [])):
        label = f"claims[{index}]"
        missing_fields = _REQUIRED_FIELDS.difference(record)
        if missing_fields:
            errors.append(f"{label} missing fields: {', '.join(sorted(missing_fields))}")
            continue
        claim_id = record["id"]
        if not isinstance(claim_id, str) or not claim_id:
            errors.append(f"{label}.id must be a non-empty string")
        elif claim_id in claim_ids:
            errors.append(f"duplicate claim id: {claim_id}")
        else:
            claim_ids.add(claim_id)
        if record["kind"] not in _VALID_KINDS:
            errors.append(f"{label}.kind is invalid")
        if record["precedence"].get("tier") not in precedence_order:
            errors.append(f"{label}.precedence.tier is not registered")
        if record["kind"] == "quarantine" and not record["quarantine"].get("is_quarantined"):
            errors.append(f"{label} quarantine kind must be quarantined")
        if record["quarantine"].get("is_quarantined") and record["status"] != "quarantine":
            errors.append(f"{label} quarantined record must have quarantine status")
        if not record["quarantine"].get("is_quarantined") and not record["consumers"]:
            errors.append(f"{label} executable record requires a consumer")
        if not record["quarantine"].get("is_quarantined") and not record["tests"]:
            errors.append(f"{label} executable record requires a test reference")
        if record["layer"] not in _VALID_LAYERS:
            errors.append(f"{label}.layer is invalid")
        if record["layer"] == "canonical" and not str(record.get("attributed_to") or "").strip():
            # Only the canonical layer can bind, so this is where a missing name would be
            # read as the house voice rather than as an incomplete record.
            errors.append(f"{label} is canonical and must name its attributed_to")
        if record["computability"] not in _VALID_COMPUTABILITY:
            errors.append(f"{label}.computability is invalid")
        out_of_scope = record.get("out_of_scope")
        if out_of_scope is not None:
            if out_of_scope not in _VALID_OUT_OF_SCOPE:
                errors.append(f"{label}.out_of_scope is not a recognised exclusion")
            elif record["consumers"] != ["doctrine audit"]:
                # An out-of-scope record is audit material; wiring it to a capability
                # would put a number the harness may not prescribe into a verdict.
                errors.append(f"{label} is out of scope and cannot name a runtime consumer")
        if record["layer"] in {"practice", "harness"} and record["kind"] == "hard_gate":
            # A harness-layer record has no source; letting it be a hard gate would put an
            # unsourced rejection into the same tier as the eight criteria.
            errors.append(f"{label} {record['layer']}-layer record cannot be a hard gate")
        quotations = record["provenance"].get("quotations")
        if not isinstance(quotations, builtins.list):
            quotations = []
        # A harness-layer record is the harness's own operating rule and has no book to
        # quote; saying so is honest, whereas attaching a borrowed citation would not be.
        needs_quotation = not record["quarantine"].get("is_quarantined") and record["layer"] != "harness"
        if needs_quotation and not quotations:
            errors.append(f"{label} executable record requires at least one source quotation")
        for position, quotation in enumerate(quotations):
            if not isinstance(quotation, Mapping):
                errors.append(f"{label}.provenance.quotations[{position}] must be an object")
                continue
            if quotation.get("corpus") not in _VALID_CORPORA:
                errors.append(f"{label}.provenance.quotations[{position}].corpus is not a known corpus")
            if not isinstance(quotation.get("row"), int) or isinstance(quotation.get("row"), bool):
                errors.append(f"{label}.provenance.quotations[{position}].row must be an integer chapter id")
            text = quotation.get("text")
            # Measured in letters and digits, not characters: forty periods clear a raw
            # length check while quoting nothing at all.
            words = re.sub(r"[^A-Za-z0-9]", "", text) if isinstance(text, str) else ""
            if len(words) < _MINIMUM_QUOTATION_LENGTH:
                errors.append(f"{label}.provenance.quotations[{position}].text must quote the source")
        parameters = record.get("parameters") or {}
        if not isinstance(parameters, Mapping):
            errors.append(f"{label}.parameters must be an object")
            parameters = {}
        for name, specification in parameters.items():
            if not isinstance(specification, Mapping):
                errors.append(f"{label}.parameters.{name} must be an object")
                continue
            value = specification.get("value")
            numeric = _is_number(value) or (
                isinstance(value, builtins.list) and value and all(_is_number(item) for item in value)
            )
            if not numeric:
                errors.append(f"{label}.parameters.{name} must carry a number or a list of numbers")
            if not isinstance(specification.get("unit"), str):
                errors.append(f"{label}.parameters.{name} must name its unit")
            if not isinstance(specification.get("affects_verdict"), bool):
                errors.append(f"{label}.parameters.{name} must say whether it affects the verdict")
            elif specification.get("affects_verdict") and not _binds(record):
                # A parameter that changes what the engine measures changes what it concludes,
                # so it cannot sit on a claim this harness reads for contrast.
                errors.append(f"{label}.parameters.{name} affects the verdict and cannot sit on a claim this harness does not apply")
        thresholds = record["thresholds"]
        if not isinstance(thresholds, Mapping):
            errors.append(f"{label}.thresholds must be an object")
            continue
        if record["failure"].get("effect") == "not_applicable" and any(
            isinstance(specification, Mapping) and specification.get("role") == "gate"
            for specification in thresholds.values()
        ):
            # A gate is an executable pass/fail rule by definition, so a claim holding one
            # and also saying failure does not apply describes itself two ways at once.
            errors.append(f"{label} holds a gate and cannot declare a failure effect of not_applicable")
        if record["missing"].get("effect") == "not_applicable" and any(
            isinstance(specification, Mapping) and specification.get("role") == "gate"
            for specification in thresholds.values()
        ):
            # A filter with no measurement is unanswered, not irrelevant.
            errors.append(f"{label} holds a gate and cannot declare a missing effect of not_applicable")
        if record["failure"].get("effect") == "reject":
            if record["layer"] == "practice" or record.get("attributed_to") not in (None, "Minervini"):
                # A contrast filter reports; the rejection words belong to the standard this
                # harness actually follows.
                errors.append(f"{label} is contrast material and cannot declare a failure effect of reject")
            elif record["layer"] == "harness" and claim_id not in _HARNESS_CONTRACT_REJECTIONS:
                # A harness-layer record has no source, so a rejection written there has to be
                # named rather than inferred from the layer.
                errors.append(f"{label} is a harness rule and cannot declare a failure effect of reject unless it is named")
        for name, specification in thresholds.items():
            if not isinstance(specification, Mapping):
                errors.append(f"{label}.thresholds.{name} must be an object")
                continue
            index = specification.get("quote_index")
            if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(quotations):
                errors.append(f"{label}.thresholds.{name}.quote_index does not point at a quotation")
            if not isinstance(specification.get("unit"), str):
                errors.append(f"{label}.thresholds.{name} must name its unit")
            if not isinstance(specification.get("exact"), bool):
                errors.append(f"{label}.thresholds.{name} must say whether the source states it exactly")
            role = specification.get("role")
            if role not in _VALID_ROLES:
                errors.append(f"{label}.thresholds.{name}.role must be gate, band, marker, or reference")
                continue
            if role == "band":
                span = specification.get("range")
                if not isinstance(span, builtins.list) or len(span) != 2 or not all(_is_number(edge) for edge in span):
                    errors.append(f"{label}.thresholds.{name} is a band and needs a two-number range")
                elif span[0] > span[1]:
                    errors.append(f"{label}.thresholds.{name} range is inverted")
                elif span[0] == span[1]:
                    # A range whose edges meet is one value the source named, which the role
                    # taxonomy already has a word for. Left as a band it has no span to divide
                    # by, so band_position is pinned at 0.0 however far outside the
                    # measurement is, and the position ends up on the far side of the state.
                    errors.append(
                        f"{label}.thresholds.{name} is a band whose range has no width; "
                        "a single value the source named is a marker"
                    )
                if specification.get("direction") not in _VALID_DIRECTIONS:
                    errors.append(f"{label}.thresholds.{name} is a band and must say which direction is better")
            else:
                value = specification.get("value")
                # A reference is never compared against anything, so it may cite a figure
                # the source gave as a pair. A gate is compared, so it may not.
                numeric = _is_number(value) or (
                    role == "reference"
                    and isinstance(value, builtins.list)
                    and len(value) == 2
                    and all(_is_number(edge) for edge in value)
                )
                if not numeric:
                    # A boolean passes `"value" in specification` and then compares as 1,
                    # turning an ordinary stop into a rejection with the registry still green.
                    errors.append(f"{label}.thresholds.{name} must carry a numeric value")
                if role == "gate" and specification.get("comparator") not in _COMPARATORS:
                    errors.append(f"{label}.thresholds.{name} is a gate and needs a comparator")
                if role == "marker" and specification.get("comparator") is not None:
                    # A marker with a comparator is a gate wearing the word the source
                    # used to avoid drawing one.
                    errors.append(f"{label}.thresholds.{name} is a marker and cannot carry a comparator")
                if role == "gate" and record["layer"] == "harness":
                    # A harness-layer record has no source at all, so a filter written there
                    # would be a rejection nobody said. Practice-layer and other-practitioner
                    # filters are real, and `evaluate_gate` marks them as non-binding rather
                    # than the registry pretending they are population statistics.
                    errors.append(f"{label}.thresholds.{name} cannot be a gate on the harness layer")

    _assert_manifest_roles(REQUIRED_THRESHOLDS)
    registered = {record.get("id"): record for record in registry.get("claims", [])}
    for claim_id, name, role in REQUIRED_THRESHOLDS:
        record = registered.get(claim_id)
        if record is None:
            errors.append(f"a reducer reads {claim_id}.{name} but no such claim is registered")
            continue
        specification = record.get("thresholds", {}).get(name)
        if specification is None:
            errors.append(f"a reducer reads {claim_id}.{name} but that threshold is not registered")
        elif specification.get("role") != role:
            # A reducer reads a gate's scalar or a band's pair. Swapping the role keeps
            # the name resolvable and hands the reducer the wrong shape mid-verdict.
            errors.append(f"a reducer reads {claim_id}.{name} as a {role} but it is registered as a {specification.get('role')}")
        if not _binds(record):
            # Non-binding claims may hold real filters now, which is what makes this rule
            # necessary: the registry no longer refuses to record another practitioner's
            # standard, so the place the refusal has to live is the reducers' own manifest.
            errors.append(f"a reducer reads {claim_id}.{name} but that claim is not binding on this harness")

    return {"valid": not errors, "errors": errors, "claim_count": len(registry.get("claims", []))}


def _assert_manifest_roles(manifest: tuple[tuple[str, str, str], ...]) -> None:
    """Refuse a reducer manifest that names a role no reducer may decide with.

    A marker is a signed distance from a value the source declined to bound. Listing one
    here would hand a reducer that distance under a name that reads like a limit.
    """
    named = [f"{claim_id}.{name}" for claim_id, name, role in manifest if role == "marker"]
    if named:
        raise ValueError(f"a reducer may not read a marker: {', '.join(named)}")


def _is_number(value: Any) -> bool:
    # Python's JSON reader accepts NaN and Infinity, and every comparison against NaN is
    # false, so an ordinary stop would silently fail a ceiling the registry calls valid.
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


__all__ = ["binds", "evaluate_band", "evaluate_gate", "evaluate_marker", "get_claim", "list", "parameter", "threshold", "validate"]
