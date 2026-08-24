from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import time
import unittest


ROOT = Path(__file__).resolve().parents[3]
CLAUDE = ROOT / "CLAUDE.md"
SKILLS = ROOT / ".claude" / "skills"


class SharedHarnessTopologyTests(unittest.TestCase):
    def test_claude_and_codex_resolve_the_same_harness_files(self) -> None:
        agents_md = ROOT / "AGENTS.md"
        # The Codex CLI resolves its skill catalog from .codex/skills; a .agents/skills
        # link was never read by any host and drifted silently for that reason.
        codex_skills = ROOT / ".codex" / "skills"

        self.assertTrue(agents_md.is_symlink())
        self.assertEqual(agents_md.readlink(), Path("CLAUDE.md"))
        self.assertEqual(agents_md.resolve(), CLAUDE.resolve())
        self.assertTrue(codex_skills.is_symlink())
        self.assertEqual(codex_skills.readlink(), Path("../.claude/skills"))
        self.assertEqual(codex_skills.resolve(), SKILLS.resolve())
        self.assertFalse((ROOT / ".agents").exists())

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

    def test_ticker_analysis_keeps_fixed_evidence_prompts_closed_world(self) -> None:
        text = (SKILLS / "ticker-analysis" / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("closed world", text.casefold())
        self.assertIn("unrelated fixture, live ticker, or web number", text.casefold())
        self.assertIn("Primary Base duration, depth, or all-time-high trigger is not supplied", text)
        self.assertIn("keep it missing", text.casefold())

    def test_ticker_analysis_requires_the_completed_stop_path_for_hold(self) -> None:
        text = (SKILLS / "ticker-analysis" / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("every completed daily low", text.casefold())
        self.assertIn("recovered latest price cannot establish HOLD", text)
        self.assertIn("incomplete path coverage means INCOMPLETE", text)
        self.assertIn("actual effective date", text)

    def test_the_only_hook_is_the_offline_readiness_notice_and_it_cannot_block(self) -> None:
        settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))

        hooks = settings["hooks"]
        self.assertEqual(list(hooks), ["SessionStart"])
        self.assertEqual([group["matcher"] for group in hooks["SessionStart"]], ["startup"])
        handlers = [handler for group in hooks["SessionStart"] for handler in group["hooks"]]
        self.assertEqual(
            [handler["command"] for handler in handlers],
            ["${CLAUDE_PROJECT_DIR}/.claude/hooks/provider-readiness.sh"],
        )
        script = ROOT / ".claude" / "hooks" / "provider-readiness.sh"
        self.assertTrue(os.access(script, os.X_OK))
        # Every session pays for this, so it runs the offline half of health only.
        self.assertIn('"health", "--format", "compact"', script.read_text(encoding="utf-8"))

        started = time.monotonic()
        completed = subprocess.run(
            [str(script)],
            capture_output=True,
            text=True,
            timeout=30,
            env={**os.environ, "CLAUDE_PROJECT_DIR": str(ROOT)},
        )

        # A readiness notice may never be the reason a session fails to start.
        self.assertEqual(completed.returncode, 0)
        self.assertLess(time.monotonic() - started, 20)

    def test_settings_allow_only_the_canonical_runtime_boundary(self) -> None:
        settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))

        allowed = settings["permissions"]["allow"]
        self.assertIn("Bash(scripts/.venv/bin/python scripts/pipeline *)", allowed)
        self.assertIn("Bash(bash scripts/bootstrap.sh)", allowed)
        self.assertFalse(any("scripts/modules" in rule for rule in allowed))


if __name__ == "__main__":
    unittest.main()
