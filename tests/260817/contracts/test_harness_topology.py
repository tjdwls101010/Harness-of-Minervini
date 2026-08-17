from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
CLAUDE = ROOT / "CLAUDE.md"
SKILLS = ROOT / ".claude" / "skills"


class SharedHarnessTopologyTests(unittest.TestCase):
    def test_claude_and_codex_resolve_the_same_harness_files(self) -> None:
        agents_md = ROOT / "AGENTS.md"
        agent_skills = ROOT / ".agents" / "skills"

        self.assertTrue(agents_md.is_symlink())
        self.assertEqual(agents_md.readlink(), Path("CLAUDE.md"))
        self.assertEqual(agents_md.resolve(), CLAUDE.resolve())
        self.assertTrue(agent_skills.is_symlink())
        self.assertEqual(agent_skills.readlink(), Path("../.claude/skills"))
        self.assertEqual(agent_skills.resolve(), SKILLS.resolve())
        self.assertFalse((ROOT / ".codex" / "skills").exists())

    def test_runtime_harness_has_only_two_intent_skills_and_no_fixed_rails(self) -> None:
        self.assertEqual({path.name for path in SKILLS.iterdir()}, {"market-scan", "ticker-analysis"})
        for removed in (ROOT / ".claude" / "agents", ROOT / ".claude" / "rules", ROOT / ".claude" / "workflows"):
            self.assertFalse(removed.exists())
        self.assertFalse((ROOT / ".codex" / "agents").exists())

    def test_root_constitution_is_thin_principle_first_and_interface_driven(self) -> None:
        text = CLAUDE.read_text(encoding="utf-8")

        self.assertLessEqual(len(text.splitlines()), 180)
        self.assertIn("principle", text.casefold())
        self.assertIn("scripts/.venv/bin/python scripts/pipeline capabilities", text)
        self.assertIn("describe <capability>", text)
        self.assertNotIn("scripts/modules/", text)
        self.assertNotIn("trade-review", text)
        self.assertNotIn("/screen", text)

    def test_skills_route_judgment_without_copying_the_cli_catalog(self) -> None:
        for name in ("market-scan", "ticker-analysis"):
            text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("description:", text)
            self.assertIn("describe", text)
            self.assertIn("--help", text)
            self.assertNotIn("scripts/modules/", text)
            self.assertNotIn("/screen", text)
            self.assertNotIn("trade-review", text)
            self.assertNotIn("references/", text)

    def test_settings_have_no_hooks_and_allow_only_the_canonical_runtime_boundary(self) -> None:
        settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))

        self.assertNotIn("hooks", settings)
        allowed = settings["permissions"]["allow"]
        self.assertIn("Bash(scripts/.venv/bin/python scripts/pipeline *)", allowed)
        self.assertIn("Bash(bash scripts/bootstrap.sh)", allowed)
        self.assertFalse(any("scripts/modules" in rule for rule in allowed))


if __name__ == "__main__":
    unittest.main()
