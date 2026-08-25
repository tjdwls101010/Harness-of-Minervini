"""Round four: two readings that were flags again, and a sentence I read backwards.

The correction window was the worse mistake. I argued that a decline the stock had fully
recovered from belonged to the previous base, because the rally back had worked off its
overhead supply. The passage says the opposite in its own next clause: a stock that fell
more than half "could fail as it reaches or slightly surpasses a new high. This is due to
excessive overhead supply created by the steep price decline." The recovery is when the
danger arrives, not when it leaves.

The other blocker is about which declarations a caller may make. A reading that the bars
cannot contradict, made by the same person who supplied the thing being read, is the flag
this rewrite removed wearing a longer description.
"""

from __future__ import annotations

import unittest

import pandas as pd

from scripts.minervini.setup import evaluate_setup
from scripts.minervini.setup_evidence import build_setup_evidence
from tests.readings import full as readings
from tests.series import anchor_dates, base_series


READ = {"right_side_development": "constructive", "entry_proximity": "at_pivot"}


def tail(frame: pd.DataFrame, sessions: int, *, close: float, volume: float) -> pd.DataFrame:
    added = pd.DataFrame(
        {"Open": close, "High": close * 1.005, "Low": close * 0.995, "Close": close, "Volume": volume},
        index=pd.bdate_range(start=frame.index[-1] + pd.Timedelta(days=1), periods=sessions),
    )
    return pd.concat([frame, added])


def signal(result, identifier):
    return next(item for item in result["signals"] if item["id"] == identifier)


class CorrectionRunsFromTheRealPeakTests(unittest.TestCase):
    def test_a_peak_the_stock_never_recovered_still_sets_the_correction(self) -> None:
        frame, anchors = base_series()
        older = pd.DataFrame(
            {"Open": [199.0], "High": [200.0], "Low": [198.0], "Close": [199.0], "Volume": [1_000_000.0]},
            index=pd.DatetimeIndex([pd.Timestamp("2024-06-03")]),
        )

        result = evaluate_setup(build_setup_evidence(pd.concat([older, frame]), anchor_dates(frame, anchors), **readings(frame, anchor_dates(frame, anchors))))

        self.assertGreater(result["measurements"]["peak_to_low_correction_pct"], 50.0)
        self.assertIn("market.correction_depth_healthy_leader.correction_failure_threshold", result["unsatisfied"])

    def test_a_chain_declared_after_a_collapse_is_measured_from_before_it(self) -> None:
        """The danger the passage describes arrives at the old high, so recovery does not clear it."""

        frame, anchors = base_series(depths=(60.0, 10.0, 5.0))
        late = anchor_dates(frame, anchors)[2:]

        measurements = build_setup_evidence(frame, late, **readings(frame, anchor_dates(frame, anchors)))["measurements"]

        self.assertGreater(measurements["peak_to_low_correction_pct"], 50.0)


class CompletenessCannotBeSelfCertifiedTests(unittest.TestCase):
    def test_the_caller_cannot_vouch_for_their_own_segmentation(self) -> None:
        """The reading exists to check the chain; the chain's author cannot supply it."""

        frame, anchors = base_series()

        result = evaluate_setup(
            build_setup_evidence(frame, anchor_dates(frame, anchors), **readings(frame, anchor_dates(frame, anchors), chain_completeness=None))
        )

        self.assertEqual(result["setup_state"], "incomplete")
        self.assertIn("setup.declared_chain_completeness", result["missing"])

    def test_a_caller_may_still_say_their_chain_is_partial(self) -> None:
        frame, anchors = base_series()

        result = evaluate_setup(
            build_setup_evidence(frame, anchor_dates(frame, anchors), **readings(frame, anchor_dates(frame, anchors), chain_completeness="partial"))
        )

        self.assertEqual(signal(result, "setup.declared_chain_completeness")["state"], "fail")

    def test_a_segmentation_that_found_nothing_extra_is_what_can_vouch(self) -> None:
        """The seam the detector fills: the other segmentation itself, not a word naming one."""

        frame, anchors = base_series()
        chain = anchor_dates(frame, anchors)

        result = evaluate_setup(build_setup_evidence(frame, chain, **readings(frame, chain)))

        self.assertEqual(signal(result, "setup.declared_chain_completeness")["state"], "pass")
        self.assertEqual(result["setup_state"], "ready")


class ProximityIsTheReadersCallTests(unittest.TestCase):
    def test_at_pivot_is_refused_on_a_pivot_price_has_not_cleared(self) -> None:
        """The one refusal the bars support: there is no entry above a pivot nobody reached."""

        frame, anchors = base_series(breakout=False)

        result = evaluate_setup(build_setup_evidence(frame, anchor_dates(frame, anchors), right_side_development="constructive", entry_proximity="at_pivot"))

        self.assertEqual(signal(result, "setup.chase_limit_above_pivot")["state"], "fail")

    def test_at_pivot_holds_on_the_breakout_itself(self) -> None:
        frame, anchors = base_series()

        result = evaluate_setup(build_setup_evidence(frame, anchor_dates(frame, anchors), **readings(frame, anchor_dates(frame, anchors))))

        self.assertEqual(signal(result, "setup.chase_limit_above_pivot")["state"], "pass")


class PivotFailureCanRecoverTests(unittest.TestCase):
    def test_a_pivot_that_failed_and_came_back_can_trigger_again(self) -> None:
        """The claim says a pivot failure resets and recovers; the code said it never did."""

        frame, anchors = base_series()
        chain = anchor_dates(frame, anchors)
        pivot = float(frame.loc[chain[-1], "High"])
        given_back = tail(frame, 3, close=pivot * 0.97, volume=600_000.0)
        recovered = tail(given_back, 3, close=pivot * 1.04, volume=1_500_000.0)

        result = evaluate_setup(build_setup_evidence(recovered, chain, right_side_development="constructive", entry_proximity="chased"))

        self.assertEqual(result["measurements"]["failed_pivot_attempts"], 1)
        self.assertEqual(signal(result, "setup.structural_pivot_and_trigger")["state"], "pass")

    def test_a_pivot_still_given_back_has_not_triggered(self) -> None:
        frame, anchors = base_series()
        chain = anchor_dates(frame, anchors)
        pivot = float(frame.loc[chain[-1], "High"])

        result = evaluate_setup(build_setup_evidence(tail(frame, 3, close=pivot * 0.97, volume=600_000.0), chain, **readings(frame, chain)))

        self.assertEqual(signal(result, "setup.structural_pivot_and_trigger")["state"], "not_triggered")


class QuietingIsReportedNotDecidedTests(unittest.TestCase):
    def test_a_hair_of_tightening_is_not_evidence_that_price_quieted_noticeably(self) -> None:
        """"Quiets down noticeably" has no number, so a strict less-than cannot stand in for it."""

        frame, anchors = base_series()

        result = evaluate_setup(build_setup_evidence(frame, anchor_dates(frame, anchors), **readings(frame, anchor_dates(frame, anchors))))

        supply = signal(result, "setup.overhead_supply_mechanism")
        self.assertEqual(supply["state"], "reported")
        self.assertNotIn("setup.overhead_supply_mechanism", result["required_evidence"])
        self.assertIsNotNone(supply["measured"]["pause_close_change_median_pct"])




class ContractTellsTheTruthTests(unittest.TestCase):
    """`--help` and `describe` read these strings, so a stale one is the interface lying.

    Three of them were stale at once after the last round: the breakout rule, the correction
    window, and the claim that all three readings are refused when the bars disagree.
    """

    def _limitations(self) -> str:
        from scripts.minervini.capabilities import CAPABILITIES

        return " ".join(CAPABILITIES["ticker.setup"].limitations)

    def test_the_breakout_limitation_describes_recovery_the_way_the_code_does(self) -> None:
        limitations = self._limitations()

        self.assertIn("counted beside the trigger", limitations)
        self.assertNotIn("a new structure somebody has to declare", limitations)

    def test_the_readings_limitation_does_not_claim_a_refusal_that_does_not_exist(self) -> None:
        limitations = self._limitations()

        self.assertIn("cannot be self-certified", limitations)
        self.assertNotIn("Each one is refused where the bars can see the reading is wrong", limitations)


class AdversarialDirectionTests(unittest.TestCase):
    """The direction a reviewer had to run by hand because no test ran it.

    Every counterexample below was reported as reaching READY. Asserting only the honest
    direction -- that a caller who admits a gap is stopped -- leaves the dishonest one
    unexercised, which is the direction that matters.
    """

    def test_a_chain_that_skipped_a_contraction_cannot_be_talked_into_ready(self) -> None:
        frame, anchors = base_series(depths=(30.0, 5.0, 10.0, 2.0))
        dates = anchor_dates(frame, anchors)
        skipped = [dates[index] for index in (0, 1, 2, 5, 6, 7, 8)]

        result = evaluate_setup(build_setup_evidence(frame, skipped, **readings(frame, skipped)))

        self.assertNotEqual(result["setup_state"], "ready")
        self.assertIn("setup.declared_chain_completeness", result["unsatisfied"])

    def test_a_fifty_percent_extended_entry_carries_its_distance_where_a_reader_cannot_miss_it(self) -> None:
        """No mechanical rule survived here, so the harness prints the distance instead.

        Comparing the entry with the breakout's own extension called a twenty-percent gap
        that ticked down "at the pivot" and refused a one-cent advance the day after a
        three-percent breakout. The source names the limit and withholds the number.
        """

        frame, anchors = base_series()
        extended = tail(frame, 40, close=150.0, volume=400_000.0)

        chain = anchor_dates(frame, anchors)
        evidence = build_setup_evidence(extended, chain, **readings(frame, chain, entry_price=150.0))

        result = evaluate_setup(evidence)
        chase = signal(result, "setup.chase_limit_above_pivot")
        self.assertGreater(chase["measured"]["latest_close_extension_above_pivot_pct"], 50.0)
        self.assertEqual(chase["measured"]["sessions_since_breakout"], 40)
        buffer_signal = next(item for item in evidence["signals"] if "minervini_5_to_20_cents" in item["id"])
        self.assertEqual(buffer_signal["state"], "beyond_source_range")

    def test_a_base_that_more_than_halved_cannot_be_talked_into_ready_either(self) -> None:
        frame, anchors = base_series()
        older = pd.DataFrame(
            {"Open": [199.0], "High": [200.0], "Low": [198.0], "Close": [199.0], "Volume": [1_000_000.0]},
            index=pd.DatetimeIndex([pd.Timestamp("2024-06-03")]),
        )

        result = evaluate_setup(
            build_setup_evidence(
                pd.concat([older, frame]),
                anchor_dates(frame, anchors),
                chain_completeness="complete",
                right_side_development="constructive",
                entry_proximity="at_pivot",
            )
        )

        self.assertNotEqual(result["setup_state"], "ready")
        self.assertIn("market.correction_depth_healthy_leader.correction_failure_threshold", result["unsatisfied"])


if __name__ == "__main__":
    unittest.main()
