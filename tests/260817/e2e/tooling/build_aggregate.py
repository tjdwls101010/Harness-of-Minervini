"""Merge the adversarial pass's judgment with counts read off the artifacts themselves.

The reviewer judges; it does not tally. Every number here is counted from the report files,
because a reviewer that both finds the failures and reports the pass rate can be wrong about
the second in a way that hides the first -- and the acceptance suite reads the rate.

An unsupported critical claim is not merely reported. It flips that assertion to failed in
the artifact it was claimed in, which is what makes the pass rate tell the truth, and the
suite then refuses the release on the count rather than on the reviewer's word for it.

    python tests/260817/e2e/tooling/build_aggregate.py <codex_run_id> <reviewed_at>
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _bridge  # noqa: E402


E2E = pathlib.Path(__file__).resolve().parents[1]
REPORTS = E2E / "reports"


def main(run_id: str, reviewed_at: str) -> None:
    payload = _bridge.result(run_id)
    review = payload["json"]
    catalog = json.loads((E2E / "scenarios.json").read_text(encoding="utf-8"))
    runs = catalog["required_runs"]

    demoted = []
    for claim in review["unsupported_claims"]:
        path = REPORTS / claim["scenario_id"] / f"run-{claim['run']}.json"
        report = json.loads(path.read_text(encoding="utf-8"))
        block = report[f"{claim['criticality']}_assertions"]
        entry = block[claim["assertion_id"]]
        if entry["passed"]:
            entry["passed"] = False
            entry["evidence"] = f"{entry['evidence']} [adversarial pass: {claim['why']}]"
            report["overall_pass"] = all(v["passed"] for v in report["critical_assertions"].values())
            path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            demoted.append(f"{claim['scenario_id']} run {claim['run']}: {claim['assertion_id']}")

    summaries = {s["scenario_id"]: s["summary"] for s in review["scenario_summaries"]}
    scenario_summaries = []
    totals = {"critical": [0, 0], "noncritical": [0, 0]}
    for scenario in catalog["scenarios"]:
        counts = {"critical": [0, 0, []], "noncritical": [0, 0, []]}
        for run in range(1, runs + 1):
            report = json.loads((REPORTS / scenario["id"] / f"run-{run}.json").read_text(encoding="utf-8"))
            for kind in ("critical", "noncritical"):
                for name, entry in report[f"{kind}_assertions"].items():
                    counts[kind][1] += 1
                    if entry["passed"]:
                        counts[kind][0] += 1
                    else:
                        counts[kind][2].append(f"run-{run}:{name}")
        for kind in ("critical", "noncritical"):
            totals[kind][0] += counts[kind][0]
            totals[kind][1] += counts[kind][1]
        scenario_summaries.append({
            "scenario_id": scenario["id"],
            "reviewed_reports": runs,
            "critical": {"passed": counts["critical"][0], "reviewed": counts["critical"][1], "failed": counts["critical"][2]},
            "noncritical": {"passed": counts["noncritical"][0], "reviewed": counts["noncritical"][1], "failed": counts["noncritical"][2]},
            "summary": summaries.get(scenario["id"], ""),
        })

    blocking = list(review["release_blocking_findings"])
    blocking += [f"critical assertion not supported by its own evidence -- {line}" for line in demoted if line.split(": ")[1] in _critical_names(catalog)]
    critical_rate = totals["critical"][0] / totals["critical"][1]
    if critical_rate < 1.0 and not blocking:
        blocking.append("a critical assertion failed in at least one run")

    aggregate = {
        "schema_version": "1.0.0",
        "review_model": _bridge.model_of(payload, run_id),
        "reviewed_at": reviewed_at,
        "verdict": "RELEASE_APPROVED" if not blocking else "RELEASE_BLOCKED",
        "reviewed_reports": len(catalog["scenarios"]) * runs,
        "critical_assertions_reviewed": totals["critical"][1],
        "critical_assertions_passed": totals["critical"][0],
        "critical_pass_rate": critical_rate,
        "noncritical_assertions_reviewed": totals["noncritical"][1],
        "noncritical_assertions_passed": totals["noncritical"][0],
        "noncritical_pass_rate": totals["noncritical"][0] / totals["noncritical"][1],
        "release_blocking_findings": blocking,
        "scenario_summaries": scenario_summaries,
    }
    (E2E / "aggregate.json").write_text(json.dumps(aggregate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in aggregate.items() if k != "scenario_summaries"}, ensure_ascii=False, indent=1))
    print("demoted:", demoted or "none")


def _critical_names(catalog: dict) -> set[str]:
    return {a for s in catalog["scenarios"] for a in s["critical_assertions"]}


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
