#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
venv_dir="${MINERVINI_VENV:-$repo_root/scripts/.venv}"

if [[ "$venv_dir" != /* ]]; then
  venv_dir="$repo_root/$venv_dir"
fi

if ! python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 12))'; then
  echo "Harness of Minervini v2 requires Python 3.12 or newer." >&2
  exit 1
fi

if [[ ! -x "$venv_dir/bin/python" ]]; then
  python3 -m venv "$venv_dir"
fi

"$venv_dir/bin/python" -m pip install --disable-pip-version-check -r "$repo_root/scripts/requirements.txt"

canonical_python="$repo_root/scripts/.venv/bin/python"
if [[ "$venv_dir/bin/python" != "$canonical_python" ]]; then
  mkdir -p "$(dirname "$canonical_python")"
  ln -sfn "$venv_dir/bin/python" "$canonical_python"
fi

PYTHONPATH="$repo_root/scripts" "$venv_dir/bin/python" - "$repo_root" <<'PY'
import importlib
import pathlib
import pkgutil
import sys

root = pathlib.Path(sys.argv[1])
package = importlib.import_module("minervini")
module_names = [item.name for item in pkgutil.walk_packages(package.__path__, "minervini.")]
pipeline_names = ["pipeline", "pipeline.__main__"]
failures = []

for name in module_names + pipeline_names:
    try:
        importlib.import_module(name)
    except Exception as exc:
        failures.append(f"{name}: {type(exc).__name__}: {exc}")

if failures:
    for failure in failures:
        print(failure, file=sys.stderr)
    raise SystemExit(1)

print(f"Import smoke passed for {len(module_names)} v2 modules and the pipeline package.")
PY

health_report="$(PYTHONPATH="$repo_root/scripts" "$canonical_python" "$repo_root/scripts/pipeline" health --format compact)"
# health exits 0 for a valid `partial` envelope, so read the verdict rather than the code.
PYTHONPATH="$repo_root/scripts" "$canonical_python" - "$health_report" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
gaps = [gap for gap in payload.get("missing") or [] if gap.get("required")]
if payload["data"].get("ready") and not gaps:
    print("Offline v2 health check passed.")
    raise SystemExit(0)
for gap in gaps:
    print(f"health: {gap.get('id')}: {gap.get('detail') or gap.get('reason')}", file=sys.stderr)
raise SystemExit(1)
PY

if [[ -z "${MINERVINI_SEC_USER_AGENT:-}" ]]; then
  echo "Note: export MINERVINI_SEC_USER_AGENT='Your Name you@example.com' before using 'ticker fundamentals'; SEC EDGAR refuses unidentified automated callers." >&2
fi
