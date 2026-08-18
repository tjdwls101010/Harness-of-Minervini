#!/usr/bin/env bash
# Speak only when the deterministic runtime cannot answer honestly.
#
# The v2 rebuild shipped with three providers dead because nothing checked. This
# runs the offline half of `pipeline health` — no network, so it costs a session
# start nothing — and stays silent unless something is actually wrong. Run
# `pipeline health --probe` by hand when reachability itself is in question.
set -uo pipefail

repo="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
python="$repo/scripts/.venv/bin/python"
[[ -x "$python" ]] || exit 0

report="$("$python" "$repo/scripts/pipeline" health --format compact 2>/dev/null)" || exit 0

"$python" - "$report" <<'PY'
import json
import sys

try:
    payload = json.loads(sys.argv[1])
except ValueError:
    raise SystemExit(0)

data = payload.get("data") or {}
gaps = payload.get("missing") or []
if data.get("ready") and not gaps:
    raise SystemExit(0)

lines = ["Deterministic runtime is not fully ready; analysis may be degraded:"]
for gap in gaps:
    detail = gap.get("detail") or gap.get("reason")
    lines.append(f"- {gap.get('id')}: {detail}")
lines.append("Reachability was not checked. Run 'scripts/.venv/bin/python scripts/pipeline health --probe' to test providers.")
print("\n".join(lines))
PY
