"""Deterministic technical-eligibility routes for prospective entries.

This module deliberately evaluates only the two technical routes.  Power Play is
a fundamentals-policy exception and is therefore not accepted as an eligibility
route or input.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping


EligibilityState = Literal["eligible", "avoid", "incomplete"]
EligibilityRoute = Literal["standard", "recent_ipo_primary_base"]
HistoryState = Literal["sufficient", "insufficient", "unknown"]

_HARD_GATE_STATES = frozenset({"pass", "fail", "unavailable"})
_QUALITATIVE_STATES = frozenset(
    {
        "supports",
        "contradicts",
        "mixed",
        "observed",
        "unavailable",
        "needs_input",
        "needs_chart",
        "not_applicable",
    }
)


@dataclass(frozen=True)
class EligibilitySignal:
    """One claim's already-measured state; this module does not calculate thresholds."""

    id: str
    state: str
    doctrine_id: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any], *, hard_gate: bool) -> "EligibilitySignal":
        try:
            signal = cls(id=value["id"], state=value["state"], doctrine_id=value["doctrine_id"])
        except KeyError as error:
            raise ValueError(f"eligibility signal is missing {error.args[0]}") from error
        if not all(isinstance(item, str) and item for item in (signal.id, signal.state, signal.doctrine_id)):
            raise ValueError("eligibility signal id, state, and doctrine_id must be non-empty strings")
        allowed_states = _HARD_GATE_STATES if hard_gate else _QUALITATIVE_STATES
        if signal.state not in allowed_states:
            gate_kind = "hard gate" if hard_gate else "qualitative signal"
            raise ValueError(f"unsupported {gate_kind} state: {signal.state}")
        return signal

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "state": self.state, "doctrine_id": self.doctrine_id}


@dataclass(frozen=True)
class PrimaryBaseEvidence:
    """Claim inputs for the recent-IPO route, supplied by its dedicated evaluator."""

    quantitative_claims: tuple[EligibilitySignal, ...]
    quality: EligibilitySignal

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "PrimaryBaseEvidence":
        claims = value.get("quantitative_claims", ())
        if not isinstance(claims, list):
            raise ValueError("primary_base.quantitative_claims must be a list")
        quality = value.get("quality")
        if not isinstance(quality, Mapping):
            raise ValueError("primary_base.quality must be supplied")
        return cls(
            quantitative_claims=tuple(EligibilitySignal.from_mapping(item, hard_gate=True) for item in claims),
            quality=EligibilitySignal.from_mapping(quality, hard_gate=False),
        )


@dataclass(frozen=True)
class EligibilityEvidence:
    """Public input seam for technical eligibility.

    The eight Trend Template and Primary Base claim states are evaluated upstream.
    Keeping them as claim inputs prevents this route reducer from introducing
    unapproved numeric thresholds.
    """

    history_state: HistoryState
    stage_2: EligibilitySignal
    trend_template: tuple[EligibilitySignal, ...]
    primary_base: PrimaryBaseEvidence | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EligibilityEvidence":
        history_state = value.get("history_state")
        if history_state not in {"sufficient", "insufficient", "unknown"}:
            raise ValueError("history_state must be sufficient, insufficient, or unknown")
        stage_2 = value.get("stage_2")
        if not isinstance(stage_2, Mapping):
            raise ValueError("stage_2 must be supplied")
        trend_template = value.get("trend_template")
        if not isinstance(trend_template, list) or len(trend_template) != 8:
            raise ValueError("trend_template must contain exactly eight criteria")
        signals = tuple(EligibilitySignal.from_mapping(item, hard_gate=True) for item in trend_template)
        if len({signal.id for signal in signals}) != 8:
            raise ValueError("trend_template criteria must have unique ids")
        primary_base = value.get("primary_base")
        if primary_base is not None and not isinstance(primary_base, Mapping):
            raise ValueError("primary_base must be an object when supplied")
        return cls(
            history_state=history_state,
            stage_2=EligibilitySignal.from_mapping(stage_2, hard_gate=True),
            trend_template=signals,
            primary_base=PrimaryBaseEvidence.from_mapping(primary_base) if primary_base is not None else None,
        )


@dataclass(frozen=True)
class EligibilityResult:
    route: EligibilityRoute
    eligibility_state: EligibilityState
    signals: tuple[EligibilitySignal, ...]

    @property
    def doctrine_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(signal.doctrine_id for signal in self.signals))

    def to_dict(self) -> dict[str, Any]:
        return {
            "route": self.route,
            "eligibility_state": self.eligibility_state,
            "signals": [signal.to_dict() for signal in self.signals],
            "doctrine_ids": list(self.doctrine_ids),
        }


def evaluate_eligibility(evidence: EligibilityEvidence) -> EligibilityResult:
    """Resolve standard or insufficient-history Primary Base eligibility.

    A known standard failure always wins over missing evidence.  The Primary Base
    route is available only for explicit insufficient history and never erases a
    known standard failure.
    """

    standard_signals = (evidence.stage_2, *evidence.trend_template)
    if any(signal.state == "fail" for signal in standard_signals):
        return EligibilityResult("standard", "avoid", standard_signals)

    if evidence.history_state == "sufficient":
        if all(signal.state == "pass" for signal in standard_signals):
            return EligibilityResult("standard", "eligible", standard_signals)
        return EligibilityResult("standard", "incomplete", standard_signals)

    if evidence.history_state != "insufficient" or evidence.primary_base is None:
        return EligibilityResult("standard", "incomplete", standard_signals)

    primary_base = evidence.primary_base
    route_signals = (*standard_signals, *primary_base.quantitative_claims, primary_base.quality)
    if any(signal.state == "fail" for signal in primary_base.quantitative_claims):
        return EligibilityResult("recent_ipo_primary_base", "avoid", route_signals)
    if not primary_base.quantitative_claims or any(signal.state != "pass" for signal in primary_base.quantitative_claims):
        return EligibilityResult("recent_ipo_primary_base", "incomplete", route_signals)
    if primary_base.quality.state == "supports":
        return EligibilityResult("recent_ipo_primary_base", "eligible", route_signals)
    if primary_base.quality.state == "contradicts":
        return EligibilityResult("recent_ipo_primary_base", "avoid", route_signals)
    return EligibilityResult("recent_ipo_primary_base", "incomplete", route_signals)
