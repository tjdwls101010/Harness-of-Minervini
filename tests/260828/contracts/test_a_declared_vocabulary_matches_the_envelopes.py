"""A declaration nobody checks against the code is the drift it was written to stop.

The schema now refuses a `data` key nobody declared. That closes one direction and opens
another: a vocabulary is a second place the key list lives, and the failure mode of a second
place is that it stops agreeing with the first. Silently -- a declaration is prose to the
interpreter, and the envelope that no longer matches it is published anyway.

So the envelopes are read back against it. Every capability is run here, in both formats,
and validated against its own published schema. The `--format compact` half is not
redundant: the shared filter strips top-level keys by name -- `measurements` from a setup,
`quarterly` from a fundamentals reading -- so a key declared as core that compact removes
would make the harness's own compact output invalid against its own schema.

What this does not catch is a declared key no capability can emit, which leaves the schema
more permissive than it needs to be and refuses nothing real. The direction that costs
something is the other one, and it is the one measured here.
"""

from __future__ import annotations

import hashlib
import pathlib
import tempfile
import unittest
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd

from scripts.minervini.capabilities import CAPABILITIES
from scripts.minervini.cli import format_payload
from scripts.minervini.clock import resolve_as_of
from scripts.minervini.ledger import Ledger
from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot, ProviderUnavailable, SnapshotMeta
from scripts.minervini.providers.sec import normalize_filed_facts
from scripts.minervini.providers.nasdaq import SecurityRecord

from tests.attestations import envelopes as component_envelopes
from tests.schemas import validator

from ..integration.test_the_live_path_reaches_a_verdict import AS_OF as FILING_AS_OF, CIK, bars as filing_bars, company_facts, submissions


AS_OF = "2025-12-31"
TICKER = "TEST"


def _meta(provider: str, **coverage: object) -> SnapshotMeta:
    return SnapshotMeta(provider=provider, retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc), as_of=date.fromisoformat(AS_OF), coverage=coverage or {"completed_only": True})


def _bars(count: int = 260) -> ProviderSnapshot[pd.DataFrame]:
    index = pd.bdate_range(end=AS_OF, periods=count)
    close = pd.Series(np.linspace(40.0, 100.0, count), index=index, dtype=float)
    frame = pd.DataFrame(
        {"Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close, "Volume": np.full(count, 1_000_000)},
        index=index,
    )
    return ProviderSnapshot(frame, _meta("fixture-prices"))


def _withheld(provider: str, operation: str):
    def raise_it(*args: object, **kwargs: object):
        raise ProviderUnavailable(provider, "fixture_withholds_evidence", operation=operation)

    return raise_it


def withholding(ledger: pathlib.Path) -> Runtime:
    """Every boundary refuses, so each capability returns its own incomplete envelope."""

    return Runtime(
        price_history=_withheld("yfinance", "price_history"),
        rs_rating=_withheld("ibd-rs-rating", "rs_rating"),
        security_master=_withheld("nasdaq", "security_master"),
        fundamentals_evidence=_withheld("sec", "fundamentals"),
        sector_ranking=_withheld("ibd-rs-rating", "sector_ranking"),
        industry_ranking=_withheld("ibd-rs-rating", "industry_ranking"),
        market_leaders=_withheld("ibd-rs-rating", "market_leaders"),
        finviz_breadth=_withheld("finviz", "raw_snapshot"),
        current_classification=_withheld("yfinance", "current_classification"),
        earnings_calendar=_withheld("yfinance", "earnings_calendar"),
        industry_top=_withheld("ibd-rs-rating", "industry_top"),
        ledger_factory=lambda: Ledger(ledger),
    )


def measured(ledger: pathlib.Path) -> Runtime:
    """Enough evidence for the price-backed capabilities to reach a measured envelope."""

    return Runtime(
        price_history=lambda ticker, as_of: _bars(),
        rs_rating=lambda ticker, as_of: ProviderSnapshot({"rating": 95, "rating_date": AS_OF}, _meta("ibd-rs-rating")),
        security_master=lambda as_of: ProviderSnapshot(
            [
                SecurityRecord("nasdaq-trader:NASDAQ:TEST", TICKER, "NASDAQ", "Test Common Stock", "common_stock", False, True, None),
                SecurityRecord("nasdaq-trader:NYSE:LEAD", "LEAD", "NYSE", "Lead Common Stock", "common_stock", False, True, None),
            ],
            _meta("nasdaq", kind="current_security_master_only", historical=False),
        ),
        fundamentals_evidence=_withheld("sec", "fundamentals"),
        sector_ranking=lambda as_of: ProviderSnapshot([{"sector": "Technology", "avg_rs": 92.0, "count": 20}], _meta("ibd-rs-rating")),
        industry_ranking=lambda as_of: ProviderSnapshot([{"industry": "Semiconductors", "sector": "Technology", "avg_rs": 95.0, "count": 8}], _meta("ibd-rs-rating")),
        market_leaders=lambda as_of, limit: ProviderSnapshot([{"symbol": TICKER, "rs": 95.0}], _meta("ibd-rs-rating")),
        finviz_breadth=_withheld("finviz", "raw_snapshot"),
        current_classification=lambda symbol: ProviderSnapshot({"symbol": symbol, "sector": "Technology", "industry": "Semiconductors"}, _meta("yfinance", kind="current_classification_only", historical=False)),
        earnings_calendar=_withheld("yfinance", "earnings_calendar"),
        industry_top=lambda industry, as_of, limit: ProviderSnapshot([{"ticker": "LEAD", "rs_rating": 98, "rs_raw": 3.1}], _meta("ibd-rs-rating")),
        ledger_factory=lambda: Ledger(ledger),
    )


def filed() -> Runtime:
    """The SEC fixture the fundamentals suite already keeps, on its own filing session."""

    return Runtime(
        fundamentals_evidence=lambda ticker, as_of, cik: ProviderSnapshot(normalize_filed_facts(company_facts(), submissions(), as_of=FILING_AS_OF), _meta("sec", filed_only=True)),
        price_history=lambda ticker, as_of: ProviderSnapshot(filing_bars("2024-01-02", FILING_AS_OF, 100.0), _meta("yfinance")),
    )


def current() -> Runtime:
    """The peer comparison is refused on a past session, so its fixtures sit on this one.

    Classification and the security master are current-only records, and this capability
    declines to reconstruct a historical taxonomy from them rather than guessing.
    """

    session = resolve_as_of().date.isoformat()
    index = pd.bdate_range(end=session, periods=260)
    close = pd.Series(np.linspace(40.0, 100.0, len(index)), index=index, dtype=float)
    frame = pd.DataFrame({"Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close, "Volume": np.full(len(index), 1_000_000)}, index=index)
    meta = SnapshotMeta(provider="fixture-prices", retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc), as_of=date.fromisoformat(session), coverage={"completed_only": True})
    return Runtime(
        current_classification=lambda symbol: ProviderSnapshot({"symbol": symbol, "sector": "Technology", "industry": "Semiconductors", "industry_id": "yfinance:technology:semiconductors"}, _meta("yfinance", kind="current_classification_only", historical=False)),
        security_master=lambda as_of: ProviderSnapshot(
            [
                SecurityRecord("nasdaq-trader:NASDAQ:TEST", TICKER, "NASDAQ", "Test Common Stock", "common_stock", False, True, None),
                SecurityRecord("nasdaq-trader:NYSE:LEAD", "LEAD", "NYSE", "Lead Common Stock", "common_stock", False, True, None),
            ],
            _meta("nasdaq", kind="current_security_master_only", historical=False),
        ),
        industry_top=lambda industry, as_of, limit: ProviderSnapshot([{"ticker": "LEAD", "rs_rating": 98, "rs_raw": 3.1}], _meta("ibd-rs-rating")),
        rs_rating=lambda ticker, as_of: ProviderSnapshot({"rating": 95, "rating_date": session}, _meta("ibd-rs-rating")),
        price_history=lambda ticker, as_of: ProviderSnapshot(frame, meta),
    )


# Branches the table's two runtimes cannot reach: a capability whose evidence comes from a
# different fixture session, one that answers only about the current one, and the prospective
# half of a reducer that has two.
EXTRA_CASES: list[tuple[str, str, dict[str, object]]] = [
    ("ticker.fundamentals", "filed", {"ticker": TICKER, "cik": CIK, "as_of": FILING_AS_OF}),
    ("ticker.peers", "current", {"ticker": TICKER, "limit": 10}),
    (
        "ticker.risk",
        "prospective",
        {"ticker": TICKER, "as_of": AS_OF, "evidence": component_envelopes(), "entry_price": 200.0, "stop_price": 188.0, "upside_price": 224.0, "average_gain_pct": 24.0},
    ),
]


# One request per capability. Everything reachable without a provider is asked for its real
# answer; the rest are asked twice, once with every boundary refusing and once with fixture
# bars, so both the incomplete branch and a measured one are read back.
REQUESTS: dict[str, dict[str, object]] = {
    "capabilities": {},
    "describe": {"capability": "ticker.risk"},
    "clock": {"as_of": AS_OF},
    "health": {"as_of": AS_OF},
    "doctrine.show": {"claim_id": "risk.initial_stop_and_reward"},
    "market.snapshot": {"as_of": AS_OF, "trade_traction": "supports"},
    "market.candidates": {"as_of": AS_OF},
    "ticker.qualify": {"ticker": TICKER, "as_of": AS_OF},
    "ticker.swings": {"ticker": TICKER, "as_of": AS_OF},
    "ticker.setup": {"ticker": TICKER, "as_of": AS_OF},
    "ticker.power-play": {"ticker": TICKER, "as_of": AS_OF},
    "ticker.fundamentals": {"ticker": TICKER, "as_of": AS_OF},
    "ticker.peers": {"ticker": TICKER, "as_of": AS_OF},
    "ticker.risk": {"ticker": TICKER, "as_of": AS_OF, "mode": "active", "entry_price": 90.0, "entry_date": "2025-11-03", "stop_price": 85.0},
    "ticker.chart": {"ticker": TICKER, "as_of": AS_OF},
    "watchlist.show": {"as_of": AS_OF},
    "watchlist.history": {"ticker": TICKER, "as_of": AS_OF},
    "watchlist.record": {
        "ticker": TICKER,
        "instrument_id": "nasdaq:NASDAQ:TEST",
        "as_of": AS_OF,
        "output_hash": hashlib.sha256(b"fixture-output").hexdigest(),
        "verdict": "WAIT",
        "condition": "completed close above 100",
        "invalidation": "close below 94",
        "doctrine_ids": ["setup.vcp_supply"],
        "evidence_quality": "partial",
        "note": "fixture",
    },
    "watchlist.annotate": {"ticker": TICKER, "as_of": AS_OF, "note": "fixture annotation"},
    "watchlist.export": {"as_of": AS_OF},
}


class EveryCapabilityDeclaresWhatItsDataHolds(unittest.TestCase):
    def test_no_capability_leaves_its_data_field_open(self) -> None:
        """An empty declaration bakes no constraint, so it is the old `data: {}` by another name."""

        undeclared = sorted(name for name, capability in CAPABILITIES.items() if not capability.data_keys)

        self.assertEqual(undeclared, [])

    def test_every_core_key_is_in_the_vocabulary_that_admits_it(self) -> None:
        for name, capability in CAPABILITIES.items():
            with self.subTest(capability=name):
                self.assertLessEqual(capability.data_core, capability.data_keys)

    def test_every_capability_is_asked_for_an_envelope_here(self) -> None:
        """A capability missing from the table is one this sweep silently never validates."""

        self.assertEqual(set(REQUESTS), set(CAPABILITIES))


class AnEnvelopeValidatesAgainstItsOwnPublishedSchema(unittest.TestCase):
    def envelopes(self) -> list[tuple[str, str, str, dict]]:
        produced: list[tuple[str, str, str, dict]] = []
        for label, build in (("withholding", withholding), ("measured", measured)):
            with tempfile.TemporaryDirectory() as temporary:
                ledger = pathlib.Path(temporary) / "ledger.sqlite3"
                runtime = build(ledger)
                for capability, request in REQUESTS.items():
                    # The export destination is a caller-selected path, so it lives with the ledger.
                    payload = execute(capability, {**request, **({"output": str(pathlib.Path(temporary) / "export.csv")} if capability == "watchlist.export" else {})}, runtime=runtime)
                    for mode in ("full", "compact"):
                        produced.append((capability, label, mode, format_payload(payload, mode)))
        for capability, label, request in EXTRA_CASES:
            payload = execute(capability, request, runtime={"filed": filed, "current": current}.get(label, Runtime)())
            for mode in ("full", "compact"):
                produced.append((capability, label, mode, format_payload(payload, mode)))
        return produced

    def test_every_envelope_this_harness_builds_satisfies_its_declaration(self) -> None:
        for capability, label, mode, payload in self.envelopes():
            with self.subTest(capability=capability, providers=label, format=mode):
                validator(capability).validate(payload)


if __name__ == "__main__":
    unittest.main()
