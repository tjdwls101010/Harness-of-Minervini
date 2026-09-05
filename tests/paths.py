"""Repository paths independent of the test runner's working directory."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "doctrine" / "claims.json"
FIXTURES = ROOT / "tests" / "260817" / "fixtures"
E2E = ROOT / "tests" / "260817" / "e2e"
