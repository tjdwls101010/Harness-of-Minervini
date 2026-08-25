"""What the Power Play evidence pack says, and what it refuses to conclude.

`qualified` is a positive evidence set, not an absence of objections. Two of the criteria the
source states are questions completed bars cannot answer -- whether volume was *huge* rather
than merely expanded, and whether a flag that is not tight nonetheless shows VCP character --
so a structure that clears every measurable limit is incomplete rather than qualified, and
says which reading it is waiting for.
"""

from __future__ import annotations

import unittest

from scripts.minervini.power_play import evaluate_power_play
from scripts.minervini.power_play_evidence import build_power_play_evidence
from tests.series import power_play_series


def evidence(**kwargs):
    return build_power_play_evidence(power_play_series(**kwargs))


def states(pack) -> dict:
    return {signal["id"]: signal["state"] for signal in pack["signals"]}


class TheMeasurableLimitsDecideWhatTheyCanDecide(unittest.TestCase):
    def test_a_flag_deeper_than_the_source_allows_is_not_a_power_play(self):
        pack = evidence(flag_depth_pct=40.0)

        verdict = evaluate_power_play(pack)

        self.assertEqual(verdict["power_play_state"], "not_qualified")
        self.assertIn(
            "fundamentals.power_play_exception.flag_maximum_decline_gate_pct",
            verdict["failed"],
        )

    def test_a_flag_shorter_than_twelve_sessions_is_not_a_power_play(self):
        pack = evidence(flag_sessions=6)

        verdict = evaluate_power_play(pack)

        self.assertEqual(verdict["power_play_state"], "not_qualified")

    def test_an_advance_under_a_hundred_percent_is_not_a_power_play(self):
        pack = evidence(advance_pct=40.0)

        verdict = evaluate_power_play(pack)

        self.assertEqual(verdict["power_play_state"], "not_qualified")


class WhatTheBarsCannotSettleStaysUnsettled(unittest.TestCase):
    def test_clearing_every_measurable_limit_is_not_yet_qualification(self):
        pack = evidence()

        verdict = evaluate_power_play(pack)

        self.assertEqual(verdict["power_play_state"], "incomplete")
        self.assertEqual(verdict["failed"], [])
        self.assertIn(
            "fundamentals.power_play_exception.launch_volume_character",
            verdict["missing"],
        )

    def test_an_advance_with_no_expansion_anywhere_fails_without_a_chart(self):
        """No magnitude is needed to observe that nothing expanded at all."""

        pack = evidence(advance_volume_multiple=1.0)

        verdict = evaluate_power_play(pack)

        self.assertEqual(verdict["power_play_state"], "not_qualified")
        self.assertIn(
            "fundamentals.power_play_exception.launch_volume_character",
            verdict["failed"],
        )

    def test_a_history_that_cannot_say_whether_a_split_happened_says_so(self):
        pack = evidence()

        verdict = evaluate_power_play(pack)

        self.assertIn("corporate_action_evidence", verdict["missing"])


if __name__ == "__main__":
    unittest.main()
