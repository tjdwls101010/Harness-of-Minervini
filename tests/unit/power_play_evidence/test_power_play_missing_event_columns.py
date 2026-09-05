"""A history that never said whether an event happened is not a history that said none did.

The split column and the dividend column are read the same way and for the same reason: without
the first, a one-for-two reverse split is indistinguishable from the hundred percent overnight
advance these criteria ask about; without the second, a payout that moved the depth past its limit
is indistinguishable from a stock that fell that far on its own. Either absence leaves the reading
unreadable and issues no key, so nobody is asked to corroborate price action that may never have
happened.
"""

from __future__ import annotations

import unittest

from scripts.minervini.power_play_evidence import build_power_play_evidence, power_play_fingerprint
from tests.series import power_play_series


class EitherColumnMissingLeavesTheReadingUnreadable(unittest.TestCase):
    def setUp(self) -> None:
        self.frame = power_play_series()

    def test_the_control_reads(self) -> None:
        evidence = build_power_play_evidence(self.frame)

        self.assertEqual(evidence["unreadable_readings"], [])
        self.assertIsNotNone(power_play_fingerprint(self.frame))

    def test_without_the_split_column(self) -> None:
        evidence = build_power_play_evidence(self.frame.drop(columns=["Stock Splits"]))

        self.assertEqual(evidence["unreadable_readings"], ["2026-04-30"])
        self.assertEqual(evidence["corporate_action_evidence"], "missing")
        self.assertEqual(evidence["chart_questions"], [])

    def test_without_the_dividend_column(self) -> None:
        """The half that had no reading of its own. Folded in, a payout that decided a criterion
        arrives as a finding about the stock."""
        evidence = build_power_play_evidence(self.frame.drop(columns=["Dividends"]))

        self.assertEqual(evidence["unreadable_readings"], ["2026-04-30"])
        self.assertEqual(evidence["distribution_evidence"], "missing")
        self.assertEqual(evidence["chart_questions"], [])

    def test_neither_column_digests(self) -> None:
        for column in ("Stock Splits", "Dividends"):
            with self.subTest(column=column):
                self.assertIsNone(power_play_fingerprint(self.frame.drop(columns=[column])))

    def test_and_neither_do_no_bars_at_all(self) -> None:
        """An empty frame has no events to digest and no prices either. Digested anyway it would
        hand every empty history one shared key."""
        self.assertIsNone(power_play_fingerprint(self.frame.iloc[0:0]))


if __name__ == "__main__":
    unittest.main()
