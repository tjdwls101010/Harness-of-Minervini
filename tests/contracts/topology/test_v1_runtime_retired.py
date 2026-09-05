from __future__ import annotations

from tests.paths import ROOT

import json
import unittest


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
        manifest_path = ROOT / "tests/baselines/v1/manifest.json"
        self.assertTrue(manifest_path.is_file())
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["baseline"]["commit_sha"], "a11f1b2bdb9fbf82138ea9537047493e500e7029")
        self.assertEqual(manifest["baseline"]["tag_candidate"], "harness-v1-final")
        self.assertEqual(manifest["baseline"]["tag_status"], "created_pushed_and_released")
        self.assertTrue(manifest["baseline"]["release_url"].endswith("/harness-v1-final"))
        self.assertTrue((ROOT / "docs/plans/260817/harness-v2-greenfield-plan.md").is_file())
        self.assertIn(".tmp/", (ROOT / ".gitignore").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
