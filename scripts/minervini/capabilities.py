from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Capability:
    name: str
    summary: str
    inputs: dict[str, Any]
    output: str
    prerequisites: list[str]
    side_effects: list[str]
    errors: list[str]

    @property
    def side_effecting(self) -> bool:
        return bool(self.side_effects)

    @property
    def schema_id(self) -> str:
        return f"https://harness.minervini.dev/schemas/v2/{self.name}.schema.json"

    def listing(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "summary": self.summary,
            "schema_id": self.schema_id,
            "side_effecting": self.side_effecting,
        }

    def description(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "summary": self.summary,
            "schema_id": self.schema_id,
            "inputs": self.inputs,
            "output": self.output,
            "prerequisites": self.prerequisites,
            "side_effects": self.side_effects,
            "errors": self.errors,
        }


def _capability(
    name: str,
    summary: str,
    *,
    inputs: dict[str, Any] | None = None,
    output: str = "v2 JSON envelope",
    prerequisites: list[str] | None = None,
    side_effects: list[str] | None = None,
    errors: list[str] | None = None,
) -> Capability:
    return Capability(
        name=name,
        summary=summary,
        inputs=inputs or {},
        output=output,
        prerequisites=prerequisites or [],
        side_effects=side_effects or [],
        errors=errors or ["invalid_request", "provider_unavailable", "internal_error"],
    )


CAPABILITIES = {
    item.name: item
    for item in [
        _capability("capabilities", "List the composable public surface."),
        _capability("describe", "Describe one capability as machine-readable data.", inputs={"capability": "name"}),
        _capability("health", "Check runtime and provider readiness without making an investment judgment."),
        _capability("clock", "Resolve the last completed US regular session or an explicit as-of date."),
        _capability("doctrine.show", "Return one normalized doctrine claim.", inputs={"claim_id": "string"}),
        _capability("market.snapshot", "Measure regime, breadth, group leadership, and source completeness."),
        _capability("market.candidates", "Return a filtered, paginated candidate universe with discovery origins."),
        _capability("ticker.qualify", "Evaluate the standard or recent-IPO technical eligibility route.", inputs={"ticker": "US symbol"}),
        _capability("ticker.setup", "Measure base, VCP, entry triggers, confirmation debt, and invalidation.", inputs={"ticker": "US symbol"}),
        _capability("ticker.fundamentals", "Evaluate filed growth, quality, integrity, and Power Play policy.", inputs={"ticker": "US symbol"}),
        _capability("ticker.peers", "Compare a ticker with its same-industry leadership set.", inputs={"ticker": "US symbol"}),
        _capability(
            "ticker.risk",
            "Evaluate prospective entry risk or an active position's HOLD/SELL evidence.",
            inputs={
                "ticker": "US symbol",
                "mode": ["prospective", "active"],
                "entry_price": "number for active mode",
                "entry_date": "date for active mode",
                "stop_price": "optional number",
                "average_gain_pct": "optional number",
            },
            prerequisites=["ticker.qualify for prospective entries"],
        ),
        _capability("ticker.chart", "Render deterministic weekly and daily chart artifacts for qualitative review.", inputs={"ticker": "US symbol"}, side_effects=["ignored chart cache artifact"]),
        _capability("watchlist.show", "Read explicitly recorded research items."),
        _capability("watchlist.history", "Read an instrument's recorded verdict history.", inputs={"ticker": "US symbol"}),
        _capability("watchlist.record", "Explicitly record a research snapshot.", side_effects=["local ignored SQLite write"]),
        _capability("watchlist.annotate", "Explicitly append a note to a research item.", side_effects=["local ignored SQLite write"]),
        _capability("watchlist.export", "Explicitly export research ledger data.", side_effects=["caller-selected file write"]),
    ]
}
