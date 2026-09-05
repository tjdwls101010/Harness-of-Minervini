"""What the collector is allowed to write into an artifact the acceptance suite then reads.

A report is a run's own account of itself, and the suite trusts three things about it that the
run does not get to author: which process produced it, that it was scored against the schema
this round pins, and that it did not claim commands nobody observed. The adversarial pass is
the check on the analysis; this is the check on the bookkeeping around it, and it belongs here
rather than there because none of it is a matter of judgement.

`build_report` is pure so that these cases need no bridge and write nothing: the collector's
only other job is putting the returned dict on disk.
"""

from __future__ import annotations

from tests.paths import ROOT

import importlib.util
import json
import pathlib
import tempfile
import unittest


_E2E = ROOT / "tests/260817/e2e"
_TOOLING = _E2E / "tooling"


def _collector():
    spec = importlib.util.spec_from_file_location("write_report", _TOOLING / "write_report.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCENARIO = {
    "id": "weak_market_zero_candidates",
    "expected_skill": "market-scan",
    "prompt": "...",
    "critical_assertions": ["routes_market_scan"],
    "noncritical_assertions": ["allows_zero_recommendations"],
}


def _payload(**overrides) -> dict:
    payload = {
        "run_id": "20260901-120000-weak_market_zero_candidates-1-abcd",
        "state": "completed",
        "model": "gpt-5.6-sol",
        "schema_path": str(_TOOLING / "report.schema.json"),
        "commands": 2,
        "json": {
            "skill_used": "market-scan",
            "commands": ["scripts/.venv/bin/python scripts/pipeline capabilities", "scripts/.venv/bin/python scripts/pipeline describe market.snapshot"],
            "final_response": "...",
            "critical_assertions": [{"id": "routes_market_scan", "passed": True, "evidence": "routed"}],
            "noncritical_assertions": [{"id": "allows_zero_recommendations", "passed": True, "evidence": "named none"}],
            "overall_pass": True,
            "limitations": [],
        },
    }
    payload.update(overrides)
    return payload


class CollectedReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = _collector()

    def test_the_agent_id_is_the_run_the_bridge_resolved(self) -> None:
        """Three aliases of one run -- a label, a full id, a thread id -- are three distinct
        strings, and the suite's "three independent agents" check reads strings. Only the id
        the bridge resolved says which process actually produced the file."""

        report = self.module.build_report(SCENARIO, _payload(), run=1)
        self.assertEqual(report["agent_id"], "codex/20260901-120000-weak_market_zero_candidates-1-abcd")

    def test_a_report_scored_against_another_schema_is_refused(self) -> None:
        with self.assertRaises(SystemExit):
            self.module.build_report(SCENARIO, _payload(schema_path="/tmp/some_other.schema.json"), run=1)

    def test_a_schema_that_merely_shares_the_name_is_refused(self) -> None:
        """Matching on the file name lets any `report.schema.json` anywhere on disk stand in for
        this round's, and a schema is what decides whether `passed: "false"` was rejected."""

        elsewhere = str(pathlib.Path(tempfile.mkdtemp()) / "report.schema.json")
        with self.assertRaises(SystemExit):
            self.module.build_report(SCENARIO, _payload(schema_path=elsewhere), run=1)

    def test_a_duplicate_assertion_id_is_refused_rather_than_letting_the_last_one_win(self) -> None:
        body = _payload()["json"]
        body["critical_assertions"] = [
            {"id": "routes_market_scan", "passed": False, "evidence": "did not route"},
            {"id": "routes_market_scan", "passed": True, "evidence": "routed"},
        ]
        with self.assertRaises(SystemExit):
            self.module.build_report(SCENARIO, _payload(json=body), run=1)

    def test_a_passed_that_is_not_a_boolean_is_refused_rather_than_coerced(self) -> None:
        body = _payload()["json"]
        body["critical_assertions"] = [{"id": "routes_market_scan", "passed": "false", "evidence": "e"}]
        with self.assertRaises(SystemExit):
            self.module.build_report(SCENARIO, _payload(json=body), run=1)

    def test_overall_pass_is_recomputed_from_the_critical_assertions(self) -> None:
        body = _payload()["json"]
        body["critical_assertions"] = [{"id": "routes_market_scan", "passed": False, "evidence": "did not route"}]
        body["overall_pass"] = True
        report = self.module.build_report(SCENARIO, _payload(json=body), run=1)
        self.assertFalse(report["overall_pass"])

    def test_claiming_more_commands_than_the_run_executed_is_refused(self) -> None:
        """The bridge counts what it launched. A list longer than that count holds at least one
        command nobody ran, and the adversarial pass is told to read this list as evidence."""

        with self.assertRaises(SystemExit):
            self.module.build_report(SCENARIO, _payload(commands=1), run=1)

    def test_the_observed_command_count_is_stored_beside_the_reported_list(self) -> None:
        report = self.module.build_report(SCENARIO, _payload(), run=1)
        self.assertEqual(report["observed_command_count"], 2)

    def test_reporting_fewer_commands_than_observed_is_allowed(self) -> None:
        """Under-reporting is not a false evidence claim, and a shell that composes two
        commands into one invocation makes the two counts disagree honestly."""

        report = self.module.build_report(SCENARIO, _payload(commands=5), run=1)
        self.assertEqual(report["observed_command_count"], 5)

    def test_an_assertion_set_that_is_not_the_scenarios_is_refused(self) -> None:
        body = _payload()["json"]
        body["noncritical_assertions"] = []
        with self.assertRaises(SystemExit):
            self.module.build_report(SCENARIO, _payload(json=body), run=1)


if __name__ == "__main__":
    unittest.main()
