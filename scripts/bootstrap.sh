#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
venv_dir="${MINERVINI_VENV:-$repo_root/scripts/.venv}"

if [[ "$venv_dir" != /* ]]; then
  venv_dir="$repo_root/$venv_dir"
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

PYTHONPATH="$repo_root/scripts:$repo_root/scripts/modules" "$venv_dir/bin/python" - "$repo_root" <<'PY'
import importlib
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
module_names = [path.stem for path in sorted((root / "scripts" / "modules").glob("*.py"))]
pipeline_names = [
    "pipeline",
    "pipeline.__main__",
    "pipeline._commands",
    "pipeline._gates",
    "pipeline._runner",
]
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

print(f"Import smoke passed for {len(module_names)} modules and the pipeline package.")
PY
