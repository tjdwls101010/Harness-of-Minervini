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


FILED_SAFETY_EVIDENCE = {
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

    def test_a_measurement_the_filings_came_up_short_of_is_incomplete_not_a_pass_or_fail(self) -> None:
        # Dilution is computed from the filed share counts, so an absent count is a real gap
        # about this company -- unlike the narrative checks, which are outside what is read.
        evidence = load_fixture("filed_evidence.json")
        for filing in evidence["filings"]:
            for fact in filing["quarterly"]:
                fact.pop("diluted_shares", None)

        result = evaluate_fundamentals(evidence, as_of="2026-05-10")

        self.assertEqual(result["fundamentals_state"], "incomplete")
        self.assertEqual(result["integrity"]["dilution"]["state"], "unavailable")
        self.assertIn("dilution", result["missing"])

    def test_an_integrity_contradiction_still_governs(self) -> None:
        """What the removed waiver test was also covering, kept.

        The Power Play half of it is gone with the argument it tested: five caller-supplied
        fields turned missing growth data into `waived_by_exception` without a price bar being
        read. This is the part that was about the filings.
        """
        unsafe = copy.deepcopy(FILED_SAFETY_EVIDENCE)

        blocked = evaluate_fundamentals(unsafe, as_of="2026-05-10", going_concern="substantial_doubt")

        self.assertEqual(blocked["fundamentals_state"], "does_not_support_convergence")
        self.assertEqual(blocked["integrity"]["going_concern"]["state"], "contradicts")

    def test_rejects_web_narrative_as_numeric_evidence(self) -> None:
        with self.assertRaisesRegex(ValueError, "SEC filed facts"):
            evaluate_fundamentals({"source": "web_narrative", "filings": []}, as_of="2026-05-10")


if __name__ == "__main__":
    unittest.main()
