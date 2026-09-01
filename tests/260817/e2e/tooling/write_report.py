"""Turn one codex run's structured result into the report artifact the acceptance suite reads.

The schema hands back assertions as arrays because an object with caller-chosen keys is not
something a structured-output schema can pin. The stored shape is the dict the suite has
always read, so the conversion happens here rather than changing what the suite expects.

Three things in the artifact are not the run's to author, and are taken from the bridge or
refused: which process produced it, which schema it was scored against, and that it did not
list commands nobody launched. Everything else is the run's own account of itself, which is
what the adversarial pass exists to read.

    python3 tests/260817/e2e/tooling/write_report.py <scenario_id> <run> <codex_run_id>
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _bridge  # noqa: E402


TOOLING = pathlib.Path(__file__).resolve().parent
E2E = TOOLING.parent
REPORTS = E2E / "reports"
REPORT_SCHEMA = TOOLING / "report.schema.json"


def assertions(rows: list[dict], expected: list[str], where: str) -> dict:
    """The scenario's assertion ids, each answered exactly once with a real boolean.

    A duplicate id is not a merge conflict to resolve by taking the last one: a run that
    answered the same assertion twice, once failed and once passed, has said both things, and
    silently keeping either is the collector deciding which. `bool()` is the same trap in
    miniature -- it turns the string "false" into a pass.
    """

    got: dict[str, dict] = {}
    for row in rows:
        if row["id"] in got:
            raise SystemExit(f"{where}: {row['id']} was answered more than once")
        if not isinstance(row["passed"], bool):
            raise SystemExit(f"{where}: {row['id']} reports passed={row['passed']!r}, which is not a boolean")
        got[row["id"]] = {"passed": row["passed"], "evidence": row["evidence"].strip()}
    missing = set(expected) - set(got)
    extra = set(got) - set(expected)
    if missing or extra:
        raise SystemExit(f"{where}: missing={sorted(missing)} extra={sorted(extra)}")
    for name, row in got.items():
        if not row["evidence"]:
            raise SystemExit(f"{where}: {name} has no evidence")
    return got


def build_report(scenario: dict, payload: dict, run: int) -> dict:
    """The artifact, from the run's structured output and the bridge's own record of the run.

    `agent_id` is the run id the bridge resolved rather than the string the caller passed: a
    label, a full id and a thread id all address one run and are three different strings, and
    the suite's "three independent agents" check reads strings.
    """

    scenario_id = scenario["id"]
    body = payload["json"]
    where = f"{scenario_id} run {run}"

    scored_against = pathlib.Path(payload["schema_path"]).resolve()
    if scored_against.name != REPORT_SCHEMA.name:
        raise SystemExit(f"{where}: scored against {scored_against}, not this round's {REPORT_SCHEMA.name}")

    observed = payload["commands"]
    reported = len(body["commands"])
    if reported > observed:
        raise SystemExit(
            f"{where}: lists {reported} commands where the bridge launched {observed}; "
            "at least one was never run, and the adversarial pass reads this list as evidence"
        )

    critical = assertions(body["critical_assertions"], scenario["critical_assertions"], f"{where} critical")
    return {
        "scenario_id": scenario_id,
        "run": run,
        "agent_id": f"codex/{payload['run_id']}",
        "model": payload["model"],
        "expected_skill": scenario["expected_skill"],
        "skill_used": body["skill_used"],
        "commands": body["commands"],
        "observed_command_count": observed,
        "final_response": body["final_response"],
        "critical_assertions": critical,
        "noncritical_assertions": assertions(body["noncritical_assertions"], scenario["noncritical_assertions"], f"{where} noncritical"),
        # Recomputed, not copied: the suite reads the assertions, so a self-reported
        # `overall_pass` that disagrees with them is a second answer to a settled question.
        "overall_pass": all(entry["passed"] for entry in critical.values()),
        "limitations": body["limitations"],
    }


def main(scenario_id: str, run: int, run_id: str) -> None:
    catalog = json.loads((E2E / "scenarios.json").read_text(encoding="utf-8"))
    scenario = {s["id"]: s for s in catalog["scenarios"]}[scenario_id]
    report = build_report(scenario, _bridge.result(run_id), run)
    out = REPORTS / scenario_id
    out.mkdir(parents=True, exist_ok=True)
    (out / f"run-{run}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    failed = [n for n, r in report["critical_assertions"].items() if not r["passed"]]
    print(f"wrote {scenario_id}/run-{run}.json  skill={report['skill_used']}  critical_failed={failed or 'none'}")


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]), sys.argv[3])
