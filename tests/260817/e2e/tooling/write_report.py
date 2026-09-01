"""Turn one codex run's structured result into the report artifact the acceptance suite reads.

The schema hands back assertions as arrays because an object with caller-chosen keys is not
something a structured-output schema can pin. The stored shape is the dict the suite has
always read, so the conversion happens here rather than changing what the suite expects.

agent_id is the run id rather than anything the model reported: the suite requires three
distinct agents per scenario, and that has to be a fact about which process produced the
file, not a string the process chose for itself.

    python tests/260817/e2e/tooling/write_report.py <scenario_id> <run> <codex_run_id>
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _bridge  # noqa: E402


E2E = pathlib.Path(__file__).resolve().parents[1]
REPORTS = E2E / "reports"


def assertions(rows: list[dict], expected: list[str], where: str) -> dict:
    got = {row["id"]: {"passed": bool(row["passed"]), "evidence": row["evidence"].strip()} for row in rows}
    missing = set(expected) - set(got)
    extra = set(got) - set(expected)
    if missing or extra:
        raise SystemExit(f"{where}: missing={sorted(missing)} extra={sorted(extra)}")
    for name, row in got.items():
        if not row["evidence"]:
            raise SystemExit(f"{where}: {name} has no evidence")
    return got


def main(scenario_id: str, run: int, run_id: str) -> None:
    catalog = json.loads((E2E / "scenarios.json").read_text(encoding="utf-8"))
    scenario = {s["id"]: s for s in catalog["scenarios"]}[scenario_id]
    payload = _bridge.result(run_id)
    body = payload["json"]
    report = {
        "scenario_id": scenario_id,
        "run": run,
        "agent_id": f"codex/{run_id}",
        "model": _bridge.model_of(payload, run_id),
        "expected_skill": scenario["expected_skill"],
        "skill_used": body["skill_used"],
        "commands": body["commands"],
        "final_response": body["final_response"],
        "critical_assertions": assertions(body["critical_assertions"], scenario["critical_assertions"], f"{scenario_id} run {run} critical"),
        "noncritical_assertions": assertions(body["noncritical_assertions"], scenario["noncritical_assertions"], f"{scenario_id} run {run} noncritical"),
        "overall_pass": bool(body["overall_pass"]),
        "limitations": body["limitations"],
    }
    out = REPORTS / scenario_id
    out.mkdir(parents=True, exist_ok=True)
    (out / f"run-{run}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    failed = [n for n, r in report["critical_assertions"].items() if not r["passed"]]
    print(f"wrote {scenario_id}/run-{run}.json  skill={body['skill_used']}  critical_failed={failed or 'none'}")


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]), sys.argv[3])
