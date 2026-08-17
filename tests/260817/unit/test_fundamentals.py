import copy
import json
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

from minervini.fundamentals import evaluate_fundamentals


FIXTURES = ROOT / "tests" / "260817" / "fixtures" / "fundamentals"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


class FundamentalsEvaluatorTests(unittest.TestCase):
    def test_uses_only_facts_filed_by_as_of_and_preserves_sec_basis(self) -> None:
        result = evaluate_fundamentals(load_fixture("filed_evidence.json"), as_of="2026-05-10")

        self.assertEqual(result["accounting_basis"], ["US-GAAP"])
        self.assertEqual(result["quarterly"]["eps"][-1]["period"], "2026-Q1")
        self.assertEqual(result["quarterly"]["eps"][-1]["value"], 1.8)
        self.assertEqual(result["filings_used"], ["2025-05-01", "2026-05-01"])

    def test_reports_own_trend_deceleration_and_never_averages_fmp_conflicts(self) -> None:
        evidence = load_fixture("decelerating_evidence.json")
        fmp = {
            "source": "fmp_enrichment",
            "observed_at": "2026-05-02",
            "quarterly": [{"period": "2025-Q3", "eps": 0.70, "revenue": 131.0}],
        }

        result = evaluate_fundamentals(evidence, as_of="2026-05-10", fmp_enrichment=fmp)

        self.assertEqual(result["accounting_basis"], ["IFRS"])
        self.assertEqual(result["quarterly"]["eps_deceleration"]["state"], "contradicts")
        self.assertEqual(result["fundamentals_state"], "does_not_support_convergence")
        self.assertEqual(result["annual_growth"]["eps_yoy_pct"], 26.7)
        self.assertEqual(result["quarterly"]["eps"][-1]["value"], 0.64)
        self.assertEqual(
            result["discrepancies"],
            [
                {"period": "2025-Q3", "metric": "eps", "sec_value": 0.64, "fmp_value": 0.7, "delta": -0.06},
                {"period": "2025-Q3", "metric": "revenue", "sec_value": 130.0, "fmp_value": 131.0, "delta": -1.0},
            ],
        )

    def test_missing_critical_safety_evidence_is_incomplete_not_a_pass_or_fail(self) -> None:
        evidence = load_fixture("filed_evidence.json")
        evidence["filings"][-2].pop("going_concern")
        evidence["filings"][-2]["quarterly"][-1].pop("diluted_shares")

        result = evaluate_fundamentals(evidence, as_of="2026-05-10")

        self.assertEqual(result["fundamentals_state"], "incomplete")
        self.assertEqual(result["integrity"]["going_concern"]["state"], "unavailable")
        self.assertEqual(result["integrity"]["dilution"]["state"], "unavailable")
        self.assertIn("going_concern", result["missing"])
        self.assertIn("dilution", result["missing"])

    def test_power_play_waives_only_verified_fundamentals_with_full_proof(self) -> None:
        evidence = {
            "source": "sec_filed_facts",
            "filings": [{
                "filed_at": "2026-05-01",
                "accounting_basis": "US-GAAP",
                "accounting_integrity": {"status": "clear"},
                "going_concern": {"status": "clear"},
                "dilution": {"status": "clear"},
                "quarterly": [{"period": "2026-Q1", "end": "2026-03-31", "diluted_shares": 100.0}],
            }],
        }
        proof = {
            "detected": True,
            "quality": "textbook",
            "fundamentals_exception": {
                "status": "map_authorized_only_for_this_vcp-qualified_setup",
                "may_omit": ["verified_fundamentals"],
            },
            "technical_eligibility": "pass",
            "price_volume_structure": "pass",
            "market_alignment": "pass",
            "risk_controls": "pass",
        }

        waived = evaluate_fundamentals(evidence, as_of="2026-05-10", power_play=proof)
        incomplete_proof = copy.deepcopy(proof)
        incomplete_proof.pop("risk_controls")
        unproven = evaluate_fundamentals(evidence, as_of="2026-05-10", power_play=incomplete_proof)
        unsafe = copy.deepcopy(evidence)
        unsafe["filings"][0]["going_concern"] = {"status": "substantial_doubt"}
        blocked = evaluate_fundamentals(unsafe, as_of="2026-05-10", power_play=proof)

        self.assertEqual(waived["fundamentals_state"], "waived_by_exception")
        self.assertEqual(waived["quality"]["state"], "waived_by_exception")
        self.assertEqual(unproven["fundamentals_state"], "incomplete")
        self.assertEqual(blocked["fundamentals_state"], "does_not_support_convergence")
        self.assertEqual(blocked["integrity"]["going_concern"]["state"], "contradicts")

    def test_rejects_web_narrative_as_numeric_evidence(self) -> None:
        with self.assertRaisesRegex(ValueError, "SEC filed facts"):
            evaluate_fundamentals({"source": "web_narrative", "filings": []}, as_of="2026-05-10")


if __name__ == "__main__":
    unittest.main()
