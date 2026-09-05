"""Repository paths independent of the test runner's working directory."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "doctrine" / "claims.json"
FIXTURES = ROOT / "tests" / "fixtures"
E2E = ROOT / "tests" / "e2e"


def registry() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))
