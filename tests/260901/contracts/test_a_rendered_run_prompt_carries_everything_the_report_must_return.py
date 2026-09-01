"""A rendered run prompt must carry every assertion id the collected report is required to hold.

The catalog and the prompt template are two files that have to agree, and nothing made them.
A template that lost its assertion block still renders, still starts nine codex runs, and only
fails hours later inside `write_report.py`, which refuses a result whose assertion ids are not
exactly the scenario's -- after the tokens are spent. The same goes for the user's message: a
template that stopped interpolating it sends nine runs off to answer nothing at all.

Expected values come from `scenarios.json` rather than from the renderer, so this disagrees
with the template when the template is the thing that moved.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import unittest


_E2E = pathlib.Path(__file__).resolve().parents[3] / "tests/260817/e2e"
_TOOLING = _E2E / "tooling"


def _renderer():
    """Loaded by path: the round tooling sits beside the artifacts it renders, in a directory
    whose name is a date rather than an identifier, so there is no dotted name to import."""

    spec = importlib.util.spec_from_file_location("render_tasks", _TOOLING / "render_tasks.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RenderedRunPromptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.render_tasks = _renderer()
        cls.catalog = json.loads((_E2E / "scenarios.json").read_text(encoding="utf-8"))
        cls.template = cls.render_tasks.load_template()

    def test_every_scenario_in_the_catalog_renders(self) -> None:
        for scenario in self.catalog["scenarios"]:
            with self.subTest(scenario["id"]):
                body = self.render_tasks.render(scenario, grounding="", template=self.template)
                self.assertTrue(body.strip())

    def test_a_rendered_prompt_carries_the_users_message_verbatim(self) -> None:
        for scenario in self.catalog["scenarios"]:
            with self.subTest(scenario["id"]):
                body = self.render_tasks.render(scenario, grounding="", template=self.template)
                self.assertIn(scenario["prompt"], body)

    def test_a_rendered_prompt_names_every_assertion_the_report_must_return(self) -> None:
        for scenario in self.catalog["scenarios"]:
            expected = scenario["critical_assertions"] + scenario["noncritical_assertions"]
            body = self.render_tasks.render(scenario, grounding="", template=self.template)
            for assertion_id in expected:
                with self.subTest(scenario=scenario["id"], assertion=assertion_id):
                    self.assertIn(assertion_id, body)

    def test_no_placeholder_survives_into_a_rendered_prompt(self) -> None:
        """An unreplaced sentinel is the silent half of a template drift: the run reads the
        literal `<<...>>` as if it were instruction and answers something nobody asked."""

        for scenario in self.catalog["scenarios"]:
            with self.subTest(scenario["id"]):
                body = self.render_tasks.render(scenario, grounding="a note", template=self.template)
                self.assertNotIn("<<", body)

    def test_a_round_gets_required_runs_distinctly_labelled_tasks_per_scenario(self) -> None:
        ids = [scenario["id"] for scenario in self.catalog["scenarios"][:2]]
        rows = self.render_tasks.tasks(self.catalog, ids, grounding="", template=self.template)
        self.assertEqual(len(rows), len(ids) * self.catalog["required_runs"])
        self.assertEqual(len({row["label"] for row in rows}), len(rows))
        for row in rows:
            self.assertTrue(row["prompt"].strip())

    def test_an_unknown_scenario_is_refused_rather_than_rendered_empty(self) -> None:
        with self.assertRaises(KeyError):
            self.render_tasks.tasks(self.catalog, ["no_such_family"], grounding="", template=self.template)


if __name__ == "__main__":
    unittest.main()
