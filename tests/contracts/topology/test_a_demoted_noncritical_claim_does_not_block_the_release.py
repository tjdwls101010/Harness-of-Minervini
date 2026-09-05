"""Whether a demoted claim blocks the release is the reviewer's word, not a name lookup.

`build_aggregate` decided it by testing the assertion id against the union of every critical
name in the catalog -- and `allows_zero_recommendations` is critical in one family and
noncritical in another. Demoted where it is noncritical, it would have been reported as a
release-blocking finding, which `synthesis.schema.json` and the round README both say an
unsupported noncritical claim is not. The reviewer states `criticality` per claim; that is the
answer, and re-deriving it across the whole catalog is what introduced a second one.

The artifacts are written to a temporary tree rather than the repository's, because a test that
demotes an assertion in place would leave the committed reports and the aggregate disagreeing.
"""

from __future__ import annotations

from tests.paths import ROOT

import importlib.util
import json
import pathlib
import tempfile
import unittest


_TOOLING = ROOT / "tests/e2e/tooling"


def _aggregate_module():
    spec = importlib.util.spec_from_file_location("build_aggregate", _TOOLING / "build_aggregate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _report(scenario_id: str, run: int) -> dict:
    return {
        "scenario_id": scenario_id,
        "run": run,
        "agent_id": f"codex/{scenario_id}-{run}",
        "model": "gpt-5.6-sol",
        "expected_skill": "market-scan",
        "skill_used": "market-scan",
        "commands": ["scripts/.venv/bin/python scripts/pipeline capabilities"],
        "final_response": "...",
        "critical_assertions": {"routes_market_scan": {"passed": True, "evidence": "routed"}},
        "noncritical_assertions": {"allows_zero_recommendations": {"passed": True, "evidence": "named none"}},
        "overall_pass": True,
        "limitations": [],
    }


class DemotionCriticalityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = _aggregate_module()
        self.root = pathlib.Path(tempfile.mkdtemp())
        for run in (1, 2, 3):
            path = self.root / "weak_market_zero_candidates" / f"run-{run}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(_report("weak_market_zero_candidates", run)), encoding="utf-8")

    def _claim(self, criticality: str, assertion_id: str) -> dict:
        return {
            "scenario_id": "weak_market_zero_candidates",
            "run": 1,
            "assertion_id": assertion_id,
            "criticality": criticality,
            "why": "the quoted sentence does not say it",
        }

    def test_a_noncritical_demotion_is_recorded_and_does_not_block(self) -> None:
        demoted, blocking = self.module.apply_demotions(
            [self._claim("noncritical", "allows_zero_recommendations")], self.root
        )
        self.assertEqual(len(demoted), 1)
        self.assertEqual(blocking, [])

    def test_a_critical_demotion_blocks(self) -> None:
        demoted, blocking = self.module.apply_demotions(
            [self._claim("critical", "routes_market_scan")], self.root
        )
        self.assertEqual(len(demoted), 1)
        self.assertEqual(len(blocking), 1)

    def test_a_demotion_flips_the_artifact_and_says_why(self) -> None:
        self.module.apply_demotions([self._claim("critical", "routes_market_scan")], self.root)
        report = json.loads((self.root / "weak_market_zero_candidates/run-1.json").read_text(encoding="utf-8"))
        entry = report["critical_assertions"]["routes_market_scan"]
        self.assertFalse(entry["passed"])
        self.assertIn("the quoted sentence does not say it", entry["evidence"])
        self.assertFalse(report["overall_pass"])

    def test_a_noncritical_demotion_leaves_overall_pass_alone(self) -> None:
        """`overall_pass` is the suite's critical-only reading; a noncritical failure is not one."""

        self.module.apply_demotions([self._claim("noncritical", "allows_zero_recommendations")], self.root)
        report = json.loads((self.root / "weak_market_zero_candidates/run-1.json").read_text(encoding="utf-8"))
        self.assertFalse(report["noncritical_assertions"]["allows_zero_recommendations"]["passed"])
        self.assertTrue(report["overall_pass"])

    def test_demoting_an_already_failed_claim_is_not_counted_twice(self) -> None:
        claim = self._claim("critical", "routes_market_scan")
        self.module.apply_demotions([claim], self.root)
        demoted, blocking = self.module.apply_demotions([claim], self.root)
        self.assertEqual(demoted, [])
        self.assertEqual(blocking, [])

    def test_two_demotions_against_one_report_both_survive(self) -> None:
        """Loading the report per claim gives each claim its own copy of the file, so the second
        write puts back the assertion the first had just failed -- and both are still reported
        as demoted, which is the shape that leaves the aggregate's rate above the artifacts."""

        demoted, _ = self.module.apply_demotions(
            [self._claim("critical", "routes_market_scan"), self._claim("noncritical", "allows_zero_recommendations")],
            self.root,
        )
        self.assertEqual(len(demoted), 2)
        report = json.loads((self.root / "weak_market_zero_candidates/run-1.json").read_text(encoding="utf-8"))
        self.assertFalse(report["critical_assertions"]["routes_market_scan"]["passed"])
        self.assertFalse(report["noncritical_assertions"]["allows_zero_recommendations"]["passed"])

    def test_a_family_summarised_twice_does_not_launder_a_blank_summary(self) -> None:
        """The builder keys summaries by scenario id and keeps the last, so a family written
        once properly and once as whitespace passes a coverage check that asks only whether
        some entry was nonempty, and lands in the aggregate blank."""

        catalog = {"scenarios": [{"id": "a"}, {"id": "b"}], "required_runs": 3}
        review = {"scenario_summaries": [
            {"scenario_id": "a", "summary": "real"},
            {"scenario_id": "a", "summary": "   "},
            {"scenario_id": "b", "summary": "real"},
        ]}
        with self.assertRaises(SystemExit):
            self.module.require_full_coverage(review, catalog)

    def test_a_bad_claim_stops_the_run_before_any_artifact_is_touched(self) -> None:
        """Validation is a pass of its own, ahead of every write. Demoting until the bad claim
        is reached leaves the reports moved and the aggregate not rebuilt, and the suite reads
        the two rates separately, so both can stay above their floors while disagreeing."""

        good = self._claim("noncritical", "allows_zero_recommendations")
        with self.assertRaises(SystemExit):
            self.module.apply_demotions([good, self._claim("critical", "no_such_assertion")], self.root)
        report = json.loads((self.root / "weak_market_zero_candidates/run-1.json").read_text(encoding="utf-8"))
        self.assertTrue(report["noncritical_assertions"]["allows_zero_recommendations"]["passed"])

    def test_a_review_that_summarised_only_some_families_is_refused(self) -> None:
        """`build_aggregate` substitutes an empty string for a family the reviewer skipped, so
        a schema-valid review of nothing at all produces a clean aggregate over 57 reports it
        never opened. Coverage is not something the schema can state; it is stated here."""

        catalog = {"scenarios": [{"id": "a"}, {"id": "b"}], "required_runs": 3}
        with self.assertRaises(SystemExit):
            self.module.require_full_coverage({"scenario_summaries": [{"scenario_id": "a", "summary": "s"}]}, catalog)
        with self.assertRaises(SystemExit):
            self.module.require_full_coverage({"scenario_summaries": []}, catalog)

    def test_a_review_that_summarised_every_family_is_accepted(self) -> None:
        catalog = {"scenarios": [{"id": "a"}, {"id": "b"}], "required_runs": 3}
        review = {"scenario_summaries": [{"scenario_id": "a", "summary": "s"}, {"scenario_id": "b", "summary": "t"}]}
        self.module.require_full_coverage(review, catalog)

    def test_a_summary_left_empty_does_not_count_as_coverage(self) -> None:
        catalog = {"scenarios": [{"id": "a"}], "required_runs": 3}
        with self.assertRaises(SystemExit):
            self.module.require_full_coverage({"scenario_summaries": [{"scenario_id": "a", "summary": "  "}]}, catalog)

    def test_a_claim_naming_an_assertion_no_report_holds_is_refused(self) -> None:
        """A reviewer that invents an id must stop the aggregate rather than be skipped: the
        pass rate would then be computed over artifacts nobody demoted, and read as clean."""

        with self.assertRaises(SystemExit):
            self.module.apply_demotions([self._claim("critical", "no_such_assertion")], self.root)


if __name__ == "__main__":
    unittest.main()
