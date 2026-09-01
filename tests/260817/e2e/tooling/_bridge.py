"""Where the codex bridge lives, and the one shape of its result these scripts depend on.

The bridge is installed per machine rather than per repository, so its path cannot be a
constant here. `CODEX_BRIDGE` overrides; the default is where a user-level skill install puts
it. A missing bridge is reported as itself rather than as a JSON parse error thirty lines on.
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


def result(run_id: str) -> dict:
    """One completed run's structured result, or an exit that says which run and what state."""

    if not BRIDGE.is_file():
        raise SystemExit(f"no codex bridge at {BRIDGE}; set CODEX_BRIDGE to its path")
    completed = subprocess.run(
        [sys.executable, str(BRIDGE), "result", "--run", run_id], capture_output=True, text=True
    )
    if completed.returncode != 0:
        raise SystemExit(f"{run_id}: bridge exited {completed.returncode}\n{completed.stderr.strip()}")
    payload = json.loads(completed.stdout)
    if payload["state"] != "completed":
        raise SystemExit(f"{run_id} is {payload['state']}")
    return payload


def model_of(payload: dict, run_id: str) -> str:
    """The model the bridge recorded, never a default.

    A guessed model name would be written into the artifact and then read back by the
    acceptance suite, which checks it against the catalog's `scoring_models` -- so a fallback
    here does not fail loudly, it produces a report that passes while naming a model nobody
    confirmed ran it.
    """

    model = payload.get("model")
    if not model:
        raise SystemExit(f"{run_id}: the bridge reported no model; the artifact would name a guess")
    return model
