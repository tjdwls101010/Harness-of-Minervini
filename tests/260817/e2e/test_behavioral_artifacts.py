from __future__ import annotations

import json
from pathlib import Path
import unittest


E2E_ROOT = Path(__file__).resolve().parent
SCENARIOS_PATH = E2E_ROOT / "scenarios.json"
REPORTS_ROOT = E2E_ROOT / "reports"


class BehavioralArtifactAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))

    def test_catalog_has_ten_decision_distinct_prompt_families(self) -> None:
        scenarios = self.catalog["scenarios"]
        self.assertEqual(self.catalog["required_runs"], 3)
        self.assertEqual(len(scenarios), 10)
        self.assertEqual(len({scenario["id"] for scenario in scenarios}), 10)
        self.assertEqual({scenario["expected_skill"] for scenario in scenarios}, {"market-scan", "ticker-analysis"})

    def test_every_scenario_has_three_independent_codex_reports(self) -> None:
        for scenario in self.catalog["scenarios"]:
            reports = [self._load_report(scenario["id"], run) for run in range(1, 4)]
            self.assertEqual(len({report["agent_id"] for report in reports}), 3, scenario["id"])
            for run, report in enumerate(reports, start=1):
                self.assertEqual(report["scenario_id"], scenario["id"])
                self.assertEqual(report["run"], run)
                self.assertEqual(report["model"], "gpt-5.6-terra")
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
        self.assertEqual(aggregate["reviewed_reports"], 30)
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
