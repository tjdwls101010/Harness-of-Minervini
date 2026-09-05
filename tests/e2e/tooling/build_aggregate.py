"""Merge the adversarial pass's judgment with counts read off the artifacts themselves.

The reviewer judges; it does not tally. Every number here is counted from the report files,
because a reviewer that both finds the failures and reports the pass rate can be wrong about
the second in a way that hides the first -- and the acceptance suite reads the rate.

An unsupported critical claim is not merely reported. It flips that assertion to failed in
the artifact it was claimed in, which is what makes the pass rate tell the truth, and the
suite then refuses the release on the count rather than on the reviewer's word for it.

    python3 tests/e2e/tooling/build_aggregate.py <codex_run_id> <reviewed_at>
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _bridge  # noqa: E402


E2E = pathlib.Path(__file__).resolve().parents[1]
REPORTS = E2E / "reports"


def require_full_coverage(review: dict, catalog: dict) -> None:
    """Every family in the catalog must carry a written summary.

    A summary the reviewer omitted is silently filled with an empty string below, so a
    schema-valid review of nothing at all -- no claims, no findings, no summaries -- builds a
    clean aggregate over reports it never opened, and the suite reads the aggregate. Coverage
    is not something a JSON schema can state; it is stated here.
    """

    summaries = review["scenario_summaries"]
    named = [s["scenario_id"] for s in summaries]
    repeated = sorted({name for name in named if named.count(name) > 1})
    if repeated:
        # Keyed by id below, last one wins, so a family written once properly and once as
        # whitespace passes a check that asks only whether some entry was nonempty.
        raise SystemExit(f"the review summarised {', '.join(repeated)} more than once")
    written = {s["scenario_id"] for s in summaries if s["summary"].strip()}
    absent = sorted({s["id"] for s in catalog["scenarios"]} - written)
    if absent:
        raise SystemExit(f"the review summarised no family named {', '.join(absent)}")


def apply_demotions(claims: list[dict], reports_root: pathlib.Path) -> tuple[list[str], list[str]]:
    """Flip every unsupported claim to failed in the artifact it was claimed in.

    Validated whole before anything is written. Demoting until a bad claim is reached leaves
    the reports moved and the aggregate not rebuilt, and the suite reads those two rates
    separately -- so both can sit above their floors while disagreeing with each other.

    Returns what was demoted, and the subset that blocks. Which of the two a claim lands in is
    the reviewer's own `criticality`, never a lookup of the assertion id against the catalog:
    `allows_zero_recommendations` is critical in one family and noncritical in another, so a
    name lookup reports a demoted noncritical claim as release-blocking, which is exactly what
    the schema and the round README say it is not.
    """

    reports: dict[pathlib.Path, dict] = {}
    for claim in claims:
        path = reports_root / claim["scenario_id"] / f"run-{claim['run']}.json"
        if not path.is_file():
            raise SystemExit(f"the review names {path}, which does not exist")
        # One loaded report per path, not per claim: two claims against the same run would
        # otherwise each start from their own copy, and the second write would put back the
        # assertion the first had just failed while both were still reported as demoted.
        report = reports.setdefault(path, json.loads(path.read_text(encoding="utf-8")))
        if claim["assertion_id"] not in report[f"{claim['criticality']}_assertions"]:
            raise SystemExit(
                f"the review names {claim['criticality']} assertion {claim['assertion_id']!r} in "
                f"{claim['scenario_id']} run {claim['run']}, which that report does not hold"
            )

    demoted: list[str] = []
    blocking: list[str] = []
    touched: set[pathlib.Path] = set()
    for claim in claims:
        path = reports_root / claim["scenario_id"] / f"run-{claim['run']}.json"
        report = reports[path]
        entry = report[f"{claim['criticality']}_assertions"][claim["assertion_id"]]
        if not entry["passed"]:
            continue
        entry["passed"] = False
        entry["evidence"] = f"{entry['evidence']} [adversarial pass: {claim['why']}]"
        report["overall_pass"] = all(v["passed"] for v in report["critical_assertions"].values())
        touched.add(path)
        line = f"{claim['scenario_id']} run {claim['run']}: {claim['assertion_id']}"
        demoted.append(line)
        if claim["criticality"] == "critical":
            blocking.append(line)
    for path in sorted(touched):
        path.write_text(json.dumps(reports[path], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return demoted, blocking


def main(run_id: str, reviewed_at: str) -> None:
    payload = _bridge.result(run_id)
    review = payload["json"]
    catalog = json.loads((E2E / "scenarios.json").read_text(encoding="utf-8"))
    runs = catalog["required_runs"]

    require_full_coverage(review, catalog)
    demoted, blocking_demotions = apply_demotions(review["unsupported_claims"], REPORTS)

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
    blocking += [f"critical assertion not supported by its own evidence -- {line}" for line in blocking_demotions]
    critical_rate = totals["critical"][0] / totals["critical"][1]
    if critical_rate < 1.0 and not blocking:
        blocking.append("a critical assertion failed in at least one run")

    aggregate = {
        "schema_version": "1.0.0",
        "review_model": payload["model"],
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


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
