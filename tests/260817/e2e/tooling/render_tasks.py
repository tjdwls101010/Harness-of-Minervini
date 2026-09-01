"""Render one round's codex tasks file from the scenario catalog and the run prompt template.

A round is nine or more runs whose prompts differ only in the user's message and the two
assertion lists, and both of those already live in `scenarios.json`. Writing them out by hand
is how a family ends up asking for assertion ids the catalog no longer holds -- which
`write_report.py` refuses, but only after the runs have finished and been paid for.

`--grounding` is the one paragraph a round genuinely adds: the note that this sandbox has no
network, or that a stated threshold has to be checked against the registry before it is
treated as a gate. It is per round rather than per scenario because it describes the
environment the round is run in, not the question being asked.

    python tests/260817/e2e/tooling/render_tasks.py --out /tmp/tasks.jsonl \
        --grounding-file tests/260817/e2e/tooling/grounding/no_network.md scenario_id ...
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Sequence


TOOLING = pathlib.Path(__file__).resolve().parent
E2E = TOOLING.parent
CATALOG_PATH = E2E / "scenarios.json"
TEMPLATE_PATH = TOOLING / "run_prompt.md"


def load_catalog() -> dict:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def load_template() -> str:
    return TEMPLATE_PATH.read_text(encoding="utf-8")


def _bullets(assertion_ids: Sequence[str]) -> str:
    return "\n".join(f"- `{assertion_id}`" for assertion_id in assertion_ids)


def render(scenario: dict, *, grounding: str, template: str) -> str:
    """One run's prompt. Sentinels rather than `str.format` because the template is prose that
    is free to contain a brace, and a template that has to escape itself is one nobody edits."""

    note = grounding.strip()
    body = template.replace("<<GROUNDING>>\n\n", f"{note}\n\n" if note else "")
    body = body.replace("<<USER_PROMPT>>", scenario["prompt"])
    body = body.replace("<<CRITICAL>>", _bullets(scenario["critical_assertions"]))
    body = body.replace("<<NONCRITICAL>>", _bullets(scenario["noncritical_assertions"]))
    return body


def tasks(catalog: dict, scenario_ids: Sequence[str], *, grounding: str, template: str) -> list[dict]:
    """`required_runs` independent tasks per scenario, labelled so a report can name its run.

    The label is what `write_report.py` is told; the run id it stores as `agent_id` comes from
    the bridge, because the suite requires three distinct agents per scenario and that has to
    be a fact about which process produced the file.
    """

    by_id = {scenario["id"]: scenario for scenario in catalog["scenarios"]}
    rows = []
    for scenario_id in scenario_ids:
        scenario = by_id[scenario_id]
        body = render(scenario, grounding=grounding, template=template)
        for run in range(1, catalog["required_runs"] + 1):
            rows.append({"prompt": body, "label": f"{scenario_id}-{run}", "kind": "start"})
    return rows


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("scenario_ids", nargs="+", help="catalog ids to render, e.g. non_stop_sell")
    parser.add_argument("--out", required=True, help="JSONL to write, for `batch start --tasks-file`")
    parser.add_argument("--grounding-file", help="markdown paragraph describing this round's environment")
    args = parser.parse_args(argv)

    grounding = pathlib.Path(args.grounding_file).read_text(encoding="utf-8") if args.grounding_file else ""
    rows = tasks(load_catalog(), args.scenario_ids, grounding=grounding, template=load_template())
    out = pathlib.Path(args.out)
    out.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    print(f"wrote {len(rows)} tasks to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
