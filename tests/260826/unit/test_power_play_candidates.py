"""A candidate top is a turning point, not any bar that happens to be lower than the last one.

Reading from every descending high was the safe answer to a real problem -- the source names no
size below which a new high stops counting -- but it answered it by taking readings the chart does
not contain. A tick a hundredth of a percent above the last high is not a top anybody would draw;
it is a bar. The detector this harness already owns says which highs are turning points, and
restricting the candidates to those asks the same question of the same bars with the readings that
were never structures removed.
"""

from __future__ import annotations

import unittest

from scripts.minervini.power_play import evaluate_power_play
from scripts.minervini.power_play_evidence import build_power_play_evidence
from tests.series import power_play_series


class OnlyTurningPointsAreRead(unittest.TestCase):
    def test_the_descending_bars_of_a_flag_are_no_longer_readings(self) -> None:
        """Twenty-eight readings on a flag that contains three tops.

        Every session on a flag's way down is lower than the one before it, so a chain that walks
        descending highs reads the flag one bar at a time. Those are not competing readings of the
        structure; they are the structure's own decline, and each one arrived carrying a vote on
        whether the rejection stands.
        """
        pack = build_power_play_evidence(
            power_play_series(flag_sessions=30, flag_depth_pct=8.0, marginal_new_high_at=(-8, -4))
        )

        self.assertEqual(pack["readings"], 3)

    def test_a_genuine_marginal_tick_is_still_a_candidate(self) -> None:
        """And the two ticks stay, because a chart reader would mark them.

        This was the case that first argued for reading every descending high, and restricting to
        turning points does not answer it: price falls away from both ticks by more than the
        retracement, so both are turning points by any standard the detector applies. What answers
        it is still the chain -- all three tops read, and a rejection only where all three agree.
        """
        pack = build_power_play_evidence(
            power_play_series(flag_sessions=30, flag_depth_pct=8.0, marginal_new_high_at=(-8, -4))
        )

        self.assertEqual(pack["peak_identity"], "disputed")

    def test_the_structure_behind_them_is_still_not_rejected(self) -> None:
        pack = build_power_play_evidence(
            power_play_series(flag_sessions=30, flag_depth_pct=8.0, marginal_new_high_at=(-8, -4))
        )

        verdict = evaluate_power_play(pack)

        self.assertEqual(verdict["failed"], [])


class ARealEarlierTopIsStillRead(unittest.TestCase):
    def test_a_turning_point_below_the_peak_remains_a_candidate(self) -> None:
        """Filtering to turning points must not empty the chain.

        The whole reason the chain exists is that the search could have landed on another top. A
        filter that leaves exactly one reading on every history has not made the tops settled, it
        has stopped asking.
        """
        pack = build_power_play_evidence(power_play_series(later_high=21.0 / 0.9 + 0.01))

        self.assertGreaterEqual(pack["readings"], 2)


class TheRuleThatChoseTheTopsIsCited(unittest.TestCase):
    def test_the_segmentation_convention_reaches_the_envelope(self) -> None:
        """A reader auditing which tops were read has to be able to reach the rule that picked them.

        The candidate set is now decided by the same retracement ticker.swings cuts its chain at,
        and a verdict that turns on which highs counted while citing only the distance bound sends
        that reader to a claim that answers a different question.
        """
        from datetime import datetime, timezone

        from scripts.minervini.operations import Runtime, execute
        from scripts.minervini.providers import ProviderSnapshot, SnapshotMeta

        frame = power_play_series()
        prices = ProviderSnapshot(
            frame,
            SnapshotMeta(
                provider="fixture-prices",
                retrieved_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
                as_of=frame.index[-1].date(),
                coverage={"completed_only": True, "corporate_actions": True, "distributions": True},
            ),
        )
        payload = execute(
            "ticker.power-play",
            {"ticker": "TEST", "as_of": prices.meta.as_of.isoformat(), "no_cache": True},
            runtime=Runtime(price_history=lambda ticker, requested: prices),
        )

        self.assertIn("setup.swing_segmentation_convention", payload["doctrine_ids"])
