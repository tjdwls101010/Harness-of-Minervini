#!/usr/bin/env bash
# Speak only when the deterministic runtime cannot answer honestly.
#
# The v2 rebuild shipped with three providers dead because nothing checked. This
# runs the offline half of `pipeline health` — no network, so it costs a session
# start nothing — and stays silent unless something is actually wrong. Run
# `pipeline health --probe` by hand when reachability itself is in question.
#
# Every path exits 0: a readiness notice must never be the reason a session
# fails to start. The health call is bounded because importing the runtime pulls
# in the chart stack, which can hang on a broken install.
set -uo pipefail

repo="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
python="$repo/scripts/.venv/bin/python"
[[ -x "$python" ]] || exit 0

"$python" - "$repo" <<'PY' || exit 0
import json
import subprocess
import sys

TIMEOUT_SECONDS = 8
repo = sys.argv[1]

try:
    completed = subprocess.run(
        [f"{repo}/scripts/.venv/bin/python", f"{repo}/scripts/pipeline", "health", "--format", "compact"],
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS,
    )
except (OSError, subprocess.SubprocessError):
    print("Could not run 'pipeline health'; the deterministic runtime may be unusable. Try: bash scripts/bootstrap.sh")
    raise SystemExit(0)

try:
    payload = json.loads(completed.stdout)
    data = payload["data"]
    gaps = payload.get("missing") or []
except (KeyError, ValueError):
    print("'pipeline health' returned no readable envelope; the deterministic runtime may be unusable.")
    raise SystemExit(0)

if data.get("ready") and not gaps:
    raise SystemExit(0)

lines = ["Deterministic runtime is not fully ready; analysis may be degraded:"]
for gap in gaps:
    lines.append(f"- {gap.get('id')}: {gap.get('detail') or gap.get('reason')}")
lines.append("Reachability was not checked. Run 'scripts/.venv/bin/python scripts/pipeline health --probe' to test providers.")
print("\n".join(lines))
PY
