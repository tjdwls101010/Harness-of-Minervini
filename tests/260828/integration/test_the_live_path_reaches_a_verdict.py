"""The whole path, from SEC documents to a fundamentals verdict.

The provider's own output shape is the thing under test here: what `normalize_filed_facts`
returns is what the evaluator has to be able to reach a verdict from. Building the fixture
as SEC's two documents rather than as the normalized form is the point -- the previous
fixtures were hand-written in the normalized shape and carried fields the provider has never
emitted, which is how a live path that always came back INCOMPLETE went unnoticed.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import unittest

from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot, SnapshotMeta
from scripts.minervini.providers.sec import normalize_filed_facts


CIK = "0000000042"
AS_OF = "2026-05-08"

_QUARTERS = [
    ("2024-Q1", "2024-01-01", "2024-03-31", 0.50, 100.0, 10.0, 100.0, "0000042-24-000001", "2024-04-25", "10-Q"),
    ("2024-Q2", "2024-04-01", "2024-06-30", 0.55, 110.0, 11.5, 100.0, "0000042-24-000002", "2024-07-25", "10-Q"),
    ("2024-Q3", "2024-07-01", "2024-09-30", 0.60, 120.0, 13.2, 100.0, "0000042-24-000003", "2024-10-25", "10-Q"),
    ("2024-Q4", "2024-10-01", "2024-12-31", 0.65, 130.0, 15.0, 100.0, "0000042-25-000001", "2025-02-20", "10-K"),
    ("2025-Q1", "2025-01-01", "2025-03-31", 0.70, 140.0, 17.0, 100.5, "0000042-25-000002", "2025-04-25", "10-Q"),
    ("2025-Q2", "2025-04-01", "2025-06-30", 0.82, 158.0, 20.5, 100.5, "0000042-25-000003", "2025-07-25", "10-Q"),
    ("2025-Q3", "2025-07-01", "2025-09-30", 0.98, 182.0, 25.5, 101.0, "0000042-25-000004", "2025-10-24", "10-Q"),
    ("2025-Q4", "2025-10-01", "2025-12-31", 1.20, 215.0, 32.5, 101.0, "0000042-26-000001", "2026-02-19", "10-K"),
]

_ANNUALS = [
    ("CY2023", "2023-01-01", "2023-12-31", 1.60, 380.0, "0000042-24-000004", "2024-02-21", "10-K"),
    ("CY2024", "2024-01-01", "2024-12-31", 2.30, 460.0, "0000042-25-000001", "2025-02-20", "10-K"),
    ("CY2025", "2025-01-01", "2025-12-31", 3.70, 695.0, "0000042-26-000001", "2026-02-19", "10-K"),
]


def _unit(rows: list[tuple], value_index: int, *, quarterly: bool) -> list[dict]:
    facts = []
    for row in rows:
        frame = row[0].replace("-", "") if quarterly else row[0]
        facts.append({
            "start": row[1],
            "end": row[2],
            "val": row[value_index],
            "accn": row[-3],
            "filed": row[-2],
            "form": row[-1],
            "fy": int(row[2][:4]),
            "fp": row[0].split("-")[-1] if quarterly else "FY",
            "frame": f"CY{frame}" if quarterly else frame,
        })
    return facts


def company_facts(**overrides) -> dict:
    facts = {
        "EarningsPerShareDiluted": ("USD/shares", _unit(_QUARTERS, 3, quarterly=True) + _unit(_ANNUALS, 3, quarterly=False)),
        "Revenues": ("USD", _unit(_QUARTERS, 4, quarterly=True) + _unit(_ANNUALS, 4, quarterly=False)),
        "NetIncomeLoss": ("USD", _unit(_QUARTERS, 5, quarterly=True)),
        "WeightedAverageNumberOfDilutedSharesOutstanding": ("shares", _unit(_QUARTERS, 6, quarterly=True)),
    }
    return {
        "cik": int(CIK),
        "entityName": "Test Corp",
        "facts": {"us-gaap": {concept: {"label": concept, "units": {unit: rows}} for concept, (unit, rows) in facts.items()}},
        **overrides,
    }


def submissions() -> dict:
    rows = {(row[-3], row[-2], row[-1], row[2]) for row in _QUARTERS} | {(row[-3], row[-2], row[-1], row[2]) for row in _ANNUALS}
    ordered = sorted(rows, key=lambda item: item[1])
    return {
        "cik": int(CIK),
        "filings": {
            "recent": {
                "accessionNumber": [row[0] for row in ordered],
                "filingDate": [row[1] for row in ordered],
                "reportDate": [row[3] for row in ordered],
                "form": [row[2] for row in ordered],
            }
        },
    }


def run(**request) -> dict:
    normalized = normalize_filed_facts(company_facts(), submissions(), as_of=AS_OF)
    snapshot = ProviderSnapshot(normalized, SnapshotMeta(provider="sec", retrieved_at=datetime(2026, 5, 11, tzinfo=timezone.utc), as_of=date.fromisoformat(AS_OF), coverage={"filed_only": True}))
    return execute("ticker.fundamentals", {"ticker": "TEST", "cik": CIK, "as_of": AS_OF, **request}, runtime=Runtime(fundamentals_evidence=lambda ticker, as_of, cik: snapshot))


class TheProviderSendsEnoughToDecide(unittest.TestCase):
    def test_accelerating_filed_facts_support_convergence(self) -> None:
        payload = run()

        self.assertEqual(payload["data"]["fundamentals_state"], "supports_convergence")
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["missing"], [])

    def test_a_declared_going_concern_doubt_still_governs(self) -> None:
        payload = run(going_concern="substantial_doubt")

        self.assertEqual(payload["data"]["fundamentals_state"], "does_not_support_convergence")

    def test_the_narrative_checks_are_named_as_a_boundary_not_as_a_gap(self) -> None:
        payload = run()

        integrity = payload["data"]["integrity"]
        self.assertEqual(integrity["going_concern"]["state"], "not_evaluated")
        self.assertEqual(integrity["accounting_integrity"]["state"], "not_evaluated")
        self.assertEqual([item["id"] for item in payload["missing"]], [])


class TheEnvelopeAdmitsWhatItRead(unittest.TestCase):
    """A fixed list of one claim said far less than the payload used.

    Every reading in this capability now names the claim it came from, and the envelope's
    citation list is the reader's index into them. Leaving it at `scope.data_integrity` meant
    a result citing two dozen claims declared one, which is the same drift in the other
    direction as a list that overstates.
    """

    def test_the_claims_the_payload_names_are_the_claims_the_envelope_cites(self) -> None:
        payload = run(leader_category="turnaround")

        cited = payload["doctrine_ids"]
        self.assertIn("scope.data_integrity", cited)
        self.assertIn("fundamentals.minimum_quarterly_earnings_growth", cited)
        self.assertIn("fundamentals.code_33_triple_acceleration", cited)
        self.assertIn("fundamentals.turnaround_qualifying_criteria", cited)
        self.assertEqual(len(cited), len(set(cited)))
        self.assertEqual(cited[0], "scope.data_integrity")

    def test_a_category_nobody_declared_is_not_cited(self) -> None:
        payload = run()

        self.assertNotIn("fundamentals.turnaround_qualifying_criteria", payload["doctrine_ids"])


if __name__ == "__main__":
    unittest.main()
