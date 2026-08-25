"""What a validated chain and a satisfied evidence list still let through.

An adversarial review ran these against the first version of the engine and every one of
them reached READY. They are not variations on a theme: each is a different seam. A stale
pivot is a time coupling nobody enforced; a dollar-priced invalidation is a relationship
nobody checked; a duplicated signal id is a map built without asking whether the last
writer was allowed to write.
"""

from __future__ import annotations

import unittest

import pandas as pd

from scripts.minervini.setup import evaluate_setup
from scripts.minervini.setup_evidence import build_setup_evidence
from tests.series import anchor_dates, base_series


def flat_tail(frame: pd.DataFrame, sessions: int, *, close: float, volume: float) -> pd.DataFrame:
    tail = pd.DataFrame(
        {"Open": close, "High": close * 1.005, "Low": close * 0.995, "Close": close, "Volume": volume},
        index=pd.bdate_range(start=frame.index[-1] + pd.Timedelta(days=1), periods=sessions),
    )
    return pd.concat([frame, tail])


class StalePivotTests(unittest.TestCase):
    def test_the_breakout_is_located_at_its_own_session_not_at_the_end_of_history(self) -> None:
        frame, anchors = base_series()
        chain = anchor_dates(frame, anchors)
        breakout_session = frame.index[-1].date().isoformat()
        stale = flat_tail(frame, 40, close=103.0, volume=400_000.0)

        result = evaluate_setup(build_setup_evidence(stale, chain))

        self.assertEqual(result["measurements"]["breakout_date"], breakout_session)
        self.assertEqual(result["measurements"]["sessions_since_breakout"], 40)

    def test_a_bar_long_after_the_pivot_cannot_supply_the_breakout_volume(self) -> None:
        """The volume that matters is the volume on the day the stock left the base."""

        frame, anchors = base_series()
        chain = anchor_dates(frame, anchors)
        stale = flat_tail(frame, 40, close=103.0, volume=400_000.0)
        stale.loc[stale.index[-1], "Volume"] = 3_000_000.0

        measurements = build_setup_evidence(stale, chain)["measurements"]

        self.assertEqual(measurements["breakout_date"], frame.index[-1].date().isoformat())
        self.assertLess(measurements["breakout_volume_ratios"][50], 3.0)

    def test_a_breakout_that_gave_the_pivot_back_is_not_a_live_trigger(self) -> None:
        frame, anchors = base_series()
        chain = anchor_dates(frame, anchors)
        failed = flat_tail(frame, 5, close=95.0, volume=800_000.0)

        result = evaluate_setup(build_setup_evidence(failed, chain))

        self.assertNotEqual(result["setup_state"], "ready")


class EarlyEntryRelationshipTests(unittest.TestCase):
    def test_a_later_pivot_below_the_current_price_is_not_a_later_pivot(self) -> None:
        frame, anchors = base_series(breakout=False)

        result = evaluate_setup(
            build_setup_evidence(
                frame,
                anchor_dates(frame, anchors),
                entry_kind="tl_early",
                tactic_opt_in=True,
                entry={
                    "confirmation_debt": ["completed pivot breakout"],
                    "minervini_later_pivot": {"price": 1.0, "condition": "x"},
                    "invalidation": {"price": 1.0, "condition": "x"},
                },
            )
        )

        self.assertNotEqual(result["setup_state"], "ready")
        self.assertIn("minervini_later_pivot", result["missing"])

    def test_an_invalidation_above_the_current_price_is_already_breached(self) -> None:
        frame, anchors = base_series(breakout=False)
        price = float(frame["Close"].iloc[-1])

        result = evaluate_setup(
            build_setup_evidence(
                frame,
                anchor_dates(frame, anchors),
                entry_kind="tl_early",
                tactic_opt_in=True,
                entry={
                    "confirmation_debt": ["completed pivot breakout"],
                    "minervini_later_pivot": {"price": price * 1.05, "condition": "x"},
                    "invalidation": {"price": price * 1.05, "condition": "x"},
                },
            )
        )

        self.assertNotEqual(result["setup_state"], "ready")
        self.assertIn("precise_invalidation", result["missing"])


class SignalMapTests(unittest.TestCase):
    def _evidence(self):
        frame, anchors = base_series()
        return build_setup_evidence(frame, anchor_dates(frame, anchors))

    def test_a_non_binding_signal_cannot_stand_in_for_a_required_one(self) -> None:
        evidence = self._evidence()
        smuggled = {**evidence, "signals": [
            item for item in evidence["signals"] if item["id"] != "setup.demand_supply_volume_asymmetry"
        ] + [{"id": "setup.demand_supply_volume_asymmetry", "state": "pass", "binds": False}]}

        result = evaluate_setup(smuggled)

        self.assertNotEqual(result["setup_state"], "ready")
        self.assertIn("setup.demand_supply_volume_asymmetry", result["missing"])

    def test_two_signals_claiming_the_same_id_are_a_contradiction_not_a_last_writer_win(self) -> None:
        evidence = self._evidence()
        duplicated = {**evidence, "signals": [*evidence["signals"], {"id": "setup.demand_supply_volume_asymmetry", "state": "pass", "binds": True}]}

        result = evaluate_setup(duplicated)

        self.assertNotEqual(result["setup_state"], "ready")


class RightSideDevelopmentTests(unittest.TestCase):
    def test_a_right_side_with_no_pause_at_all_cannot_be_ready(self) -> None:
        """The source's second named form of time compression, and it needs no ratio."""

        frame, anchors = base_series(depths=(25.0,), rallies=(3,))

        result = evaluate_setup(build_setup_evidence(frame, anchor_dates(frame, anchors)))

        self.assertNotEqual(result["setup_state"], "ready")


class CheatRouteTests(unittest.TestCase):
    def test_a_cheat_entry_cannot_borrow_the_pivot_breakout_evidence_set(self) -> None:
        frame, anchors = base_series()

        result = evaluate_setup(build_setup_evidence(frame, anchor_dates(frame, anchors), entry_kind="vcp_cheat"))

        self.assertEqual(result["setup_state"], "incomplete")
        self.assertIn("cheat_geometry", result["missing"])


class VolumeAsymmetryTests(unittest.TestCase):
    def test_the_gate_reads_both_halves_of_the_sentence_it_cites(self) -> None:
        """"much bigger on up days" and "a few of the price spikes to the upside should be large"."""

        frame, anchors = base_series()
        # Totals still favour the up days, but no up day ever prints a large spike.
        change = frame["Close"].diff()
        frame.loc[change > 0, "Volume"] = 1_100_000.0
        frame.loc[change < 0, "Volume"] = 900_000.0
        frame.loc[frame.index[len(frame) // 3], "Volume"] = 5_000_000.0

        result = evaluate_setup(build_setup_evidence(frame, anchor_dates(frame, anchors)))

        self.assertEqual(result["setup_state"], "avoid")


class NormalisationTests(unittest.TestCase):
    def test_bars_out_of_order_are_normalised_once_for_both_validation_and_measurement(self) -> None:
        frame, anchors = base_series()
        chain = anchor_dates(frame, anchors)

        forward = evaluate_setup(build_setup_evidence(frame, chain))
        reversed_ = evaluate_setup(build_setup_evidence(frame.iloc[::-1], chain))

        self.assertEqual(reversed_["setup_state"], forward["setup_state"])

    def test_numeric_strings_are_read_the_same_way_by_both_halves(self) -> None:
        frame, anchors = base_series()
        chain = anchor_dates(frame, anchors)
        as_text = frame.astype(str)

        result = evaluate_setup(build_setup_evidence(as_text, chain))

        self.assertEqual(result["setup_state"], "ready")


if __name__ == "__main__":
    unittest.main()


class BaseDepthTests(unittest.TestCase):
    def test_a_base_deeper_than_the_source_calls_survivable_cannot_be_ready(self) -> None:
        """"A correction of more than 50 percent is generally too much" -- a limit with a number.

        The evidence list had four conditions and none of them looked at how deep the base
        was, so a stock that had halved and more measured as a clean VCP inside its own ruin.
        """

        frame, anchors = base_series(depths=(55.0, 10.0, 5.0))

        result = evaluate_setup(build_setup_evidence(frame, anchor_dates(frame, anchors)))

        self.assertNotEqual(result["setup_state"], "ready")
        self.assertIn("market.correction_depth_healthy_leader.correction_failure_threshold", result["unsatisfied"])

    def test_base_depth_and_duration_are_reported_against_the_ranges_the_source_gave(self) -> None:
        frame, anchors = base_series()

        signals = {item["id"]: item for item in build_setup_evidence(frame, anchor_dates(frame, anchors))["signals"]}

        depth = signals["market.correction_depth_healthy_leader.healthy_correction_range"]
        duration = signals["setup.consolidation_footprint_3_to_60_weeks.consolidation_footprint_duration_weeks"]
        self.assertEqual(depth["role"], "band")
        self.assertEqual(duration["role"], "band")
