"""The command line teaches the five tactics by only accepting them.

A parameter that takes five named values says what the five are every time it is read, in a place
no session can miss and no compaction drops. Leaving "tl_early" spellable would leave the shape
this slice removed reachable from the outside.
"""

from __future__ import annotations

import unittest

from scripts.minervini.cli import build_parser


TACTICS = (
    "key_support_level_reclaim",
    "consolidation_pivot_breakout",
    "key_moving_average_pullback",
    "oops_reversal",
    "key_support_level_pullback",
)


def entry_kind_choices() -> tuple[str, ...]:
    parser = build_parser()
    for action in parser._subparsers._group_actions[0].choices["ticker"]._subparsers._group_actions[0].choices["setup"]._actions:
        if action.dest == "entry_kind":
            return tuple(action.choices)
    raise AssertionError("ticker setup has no --entry-kind")


class TheChoicesAreTheTactics(unittest.TestCase):
    def test_every_defined_tactic_can_be_declared(self) -> None:
        self.assertEqual([name for name in TACTICS if name not in entry_kind_choices()], [])

    def test_the_two_measured_routes_are_still_there(self) -> None:
        choices = entry_kind_choices()
        self.assertIn("completed_pivot", choices)
        self.assertIn("vcp_cheat", choices)

    def test_the_word_that_names_no_tactic_is_not_spellable(self) -> None:
        self.assertNotIn("tl_early", entry_kind_choices())

    def test_the_labels_the_source_only_captioned_are_not_offered(self) -> None:
        choices = entry_kind_choices()
        for label in ("upside_reversal", "range_breakout", "inside_day"):
            with self.subTest(label=label):
                self.assertNotIn(label, choices)

    def test_the_intraday_tactics_are_not_offered(self) -> None:
        choices = entry_kind_choices()
        for label in ("opening_range_breakout", "intraday_base", "high_volume_close_pivot"):
            with self.subTest(label=label):
                self.assertNotIn(label, choices)
