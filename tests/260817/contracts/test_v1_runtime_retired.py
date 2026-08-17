from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]


class V1RuntimeRetirementTests(unittest.TestCase):
    def test_legacy_runtime_and_live_looking_v1_docs_are_absent(self) -> None:
        retired = (
            "scripts/modules",
            "scripts/tests",
            "scripts/pipeline/_commands.py",
            "scripts/pipeline/_gates.py",
            "scripts/pipeline/_runner.py",
            "docs/wiki",
            "docs/plans/implementation-plan.md",
            "docs/plans/post-implementation-review.md",
            "docs/plans/research",
            "legacy",
        )

        for relative in retired:
            self.assertFalse((ROOT / relative).exists(), relative)

    def test_public_runtime_docs_expose_only_the_v2_interface(self) -> None:
        current_surface = (
            "README.md",
            "CONTRIBUTING.md",
            "SECURITY.md",
            "NOTICE.md",
            "scripts/bootstrap.sh",
            "scripts/pipeline/__init__.py",
        )
        retired_terms = (
            "scripts/modules/",
            "pipeline qualify",
            "pipeline discover",
            "trade-review",
            "ticker-scout",
            "/screen",
            ".codex/skills",
        )

        for relative in current_surface:
            text = (ROOT / relative).read_text(encoding="utf-8")
            for term in retired_terms:
                self.assertNotIn(term, text, f"{relative}: {term}")

        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("scripts/pipeline capabilities", readme)
        self.assertIn("describe <capability>", readme)
        self.assertIn("--help", readme)

    def test_v1_is_preserved_only_as_a_compact_baseline_and_git_history(self) -> None:
        self.assertTrue((ROOT / "tests/260817/baselines/v1/manifest.json").is_file())
        self.assertTrue((ROOT / "docs/plans/260817/harness-v2-greenfield-plan.md").is_file())
        self.assertIn(".tmp/", (ROOT / ".gitignore").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
