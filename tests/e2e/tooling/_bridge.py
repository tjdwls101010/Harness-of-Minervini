"""Where the codex bridge lives, and the two of its records these scripts read.

The bridge is installed per machine rather than per repository, so its path cannot be a
constant here. `CODEX_BRIDGE` overrides; the default is where a user-level skill install puts
it. A missing bridge is reported as itself rather than as a JSON parse error thirty lines on.

`result` and `status` answer different questions and hold different fields: the structured
output and the observed command count come from `result`, and the model that produced them
only from `status`. Both go into the artifact, so both are read here and merged, rather than
each caller learning which record holds which key.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys


BRIDGE = pathlib.Path(
    os.environ.get("CODEX_BRIDGE", pathlib.Path.home() / ".claude/skills/codex/scripts/codex_bridge.py")
)


def _call(*args: str) -> dict:
    if not BRIDGE.is_file():
        raise SystemExit(f"no codex bridge at {BRIDGE}; set CODEX_BRIDGE to its path")
    completed = subprocess.run([sys.executable, str(BRIDGE), *args], capture_output=True, text=True)
    if completed.returncode != 0:
        # The bridge explains a bad selector on stdout -- a label is not one of them, only an
        # id, a prefix of one, or a thread id -- so dropping stdout hides the actionable half.
        said = "\n".join(part for part in (completed.stdout.strip(), completed.stderr.strip()) if part)
        raise SystemExit(f"bridge {' '.join(args)} exited {completed.returncode}\n{said}")
    return json.loads(completed.stdout)


def result(run_id: str) -> dict:
    """One completed run's structured result, with the model the registry recorded for it.

    The model is never defaulted. It is written into the artifact and read back by the
    acceptance suite -- reports against the catalog's `scoring_models`, the aggregate against
    the model the suite names outright -- so a fallback here does not fail loudly, it produces
    an artifact that passes while naming a model nobody confirmed ran it.
    """

    payload = _call("result", "--run", run_id)
    if payload["state"] != "completed":
        raise SystemExit(f"{run_id} is {payload['state']}")

    status = _call("status", "--run", run_id)
    records = status.get("runs", [status])
    resolved = payload["run_id"]
    recorded = next((r for r in records if r.get("run_id") == resolved), None)
    if recorded is None:
        raise SystemExit(f"{resolved}: the registry holds no status record, so its model is unknown")
    if not recorded.get("model"):
        raise SystemExit(f"{resolved}: the registry recorded no model; the artifact would name a guess")
    return {**payload, "model": recorded["model"]}
