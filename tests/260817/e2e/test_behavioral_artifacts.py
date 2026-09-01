from __future__ import annotations

import json
from pathlib import Path
import unittest


E2E_ROOT = Path(__file__).resolve().parent
SCENARIOS_PATH = E2E_ROOT / "scenarios.json"
REPORTS_ROOT = E2E_ROOT / "reports"
# Pinned rather than derived, because this is the inventory itself: a catalog that lost a
# prompt family would otherwise still agree with a count read out of the same file.
EXPECTED_SCENARIOS = 13


class BehavioralArtifactAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))

    def test_the_catalog_pins_its_decision_distinct_prompt_families(self) -> None:
        scenarios = self.catalog["scenarios"]
        self.assertEqual(self.catalog["required_runs"], 3)
        self.assertEqual(len(scenarios), EXPECTED_SCENARIOS)
        self.assertEqual(len({scenario["id"] for scenario in scenarios}), EXPECTED_SCENARIOS)
        self.assertEqual({scenario["expected_skill"] for scenario in scenarios}, {"market-scan", "ticker-analysis"})

    def test_at_least_one_family_asks_whether_the_harness_can_say_yes(self) -> None:
        """Ten of these tested a refusal, and a harness that always refuses passes all ten.

        A behavioral suite made only of things the analyst must not do measures caution and
        nothing else. At least one prompt has to be one where the evidence converges and
        withholding is the wrong answer.
        """

        approving = [
            scenario
            for scenario in self.catalog["scenarios"]
            if any(assertion.startswith("reaches_buy_ready") for assertion in scenario["critical_assertions"])
        ]
        self.assertTrue(approving, "no scenario requires the harness to reach a verdict in the affirmative")

    def test_every_scenario_has_three_independent_codex_reports(self) -> None:
        for scenario in self.catalog["scenarios"]:
            reports = [self._load_report(scenario["id"], run) for run in range(1, 4)]
            self.assertEqual(len({report["agent_id"] for report in reports}), 3, scenario["id"])
            # One scenario is scored by one model. Its three runs are independent of each
            # other and not of the standard they were judged against, so a family whose runs
            # came from two models is three reports rather than three comparable ones.
            self.assertEqual(len({report["model"] for report in reports}), 1, scenario["id"])
            for run, report in enumerate(reports, start=1):
                self.assertEqual(report["scenario_id"], scenario["id"])
                self.assertEqual(report["run"], run)
                self.assertIn(report["model"], self.catalog["scoring_models"])
                self.assertEqual(report["expected_skill"], scenario["expected_skill"])
                self.assertTrue(report["final_response"].strip())

    def test_all_critical_assertions_pass_in_all_three_runs(self) -> None:
        failures: list[str] = []
        for scenario in self.catalog["scenarios"]:
            expected = set(scenario["critical_assertions"])
            for run in range(1, 4):
                report = self._load_report(scenario["id"], run)
                actual = report["critical_assertions"]
                self.assertEqual(set(actual), expected, f"{scenario['id']} run {run}")
                for assertion_id, result in actual.items():
                    self.assertTrue(result["evidence"].strip(), f"{scenario['id']} run {run}: {assertion_id}")
                    if not result["passed"]:
                        failures.append(f"{scenario['id']} run {run}: {assertion_id}")
        self.assertEqual(failures, [])

    def test_noncritical_assertions_score_at_least_ninety_percent(self) -> None:
        passed = 0
        total = 0
        for scenario in self.catalog["scenarios"]:
            expected = set(scenario["noncritical_assertions"])
            for run in range(1, 4):
                report = self._load_report(scenario["id"], run)
                actual = report["noncritical_assertions"]
                self.assertEqual(set(actual), expected, f"{scenario['id']} run {run}")
                for result in actual.values():
                    self.assertTrue(result["evidence"].strip())
                    total += 1
                    passed += bool(result["passed"])
        self.assertGreaterEqual(passed / total, 0.90)

    def test_final_adversarial_synthesis_approves_the_artifacts(self) -> None:
        aggregate = json.loads((E2E_ROOT / "aggregate.json").read_text(encoding="utf-8"))
        self.assertEqual(aggregate["reviewed_reports"], EXPECTED_SCENARIOS * self.catalog["required_runs"])
        self.assertEqual(aggregate["critical_pass_rate"], 1.0)
        self.assertGreaterEqual(aggregate["noncritical_pass_rate"], 0.90)
        self.assertEqual(aggregate["release_blocking_findings"], [])
        self.assertEqual(aggregate["review_model"], "gpt-5.6-sol")

    def _load_report(self, scenario_id: str, run: int) -> dict:
        path = REPORTS_ROOT / scenario_id / f"run-{run}.json"
        self.assertTrue(path.is_file(), path)
        return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
