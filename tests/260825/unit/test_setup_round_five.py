"""Round five: a provenance that was a string, a rule that cut in the wrong place, and a
failure the source separates into two kinds.

The completeness source was the worst of the three. I closed a self-certification hole by
requiring an independent segmentation to vouch for the caller's chain, and then published
the words "independent segmentation" as a command-line flag. A supplier's name typed by the
supplier is not provenance. The public surface is closed until something can actually
produce that comparison, which means the standard route genuinely stops at wait.
"""

from __future__ import annotations

import unittest

import pandas as pd

from scripts.minervini.capabilities import CAPABILITIES
from scripts.minervini.contracts import RequestError
from scripts.minervini.operations import Runtime, execute
from scripts.minervini.setup import evaluate_setup
from scripts.minervini.setup_evidence import build_setup_evidence
from scripts.minervini.setup_structure import bars_fingerprint
from tests.readings import detected
from tests.series import anchor_dates, base_series, borrowed_contraction_series, hidden_turn_series


READ = {"right_side_development": "constructive", "entry_proximity": "at_pivot"}
def vouched(frame, chain, **overrides):
    """Every reading satisfied, over the bars named. The detector runs on those same bars.

    `frame` is the frame the evidence is built over, not the one the base was drawn from: a
    reading names the picture it was read from, so a test that adds sessions re-reads here the
    way an analyst re-reads a chart.
    """

    pivot = float(frame.loc[chain[-1], "High"])
    return {
        "right_side_development": "constructive",
        "chain_completeness": "complete",
        "approved_bars": bars_fingerprint(frame),
        "entry_proximity": "at_pivot",
        "entry_price": pivot * 1.001,
        **overrides,
    }


def tail(frame: pd.DataFrame, sessions: int, *, close: float, volume: float) -> pd.DataFrame:
    added = pd.DataFrame(
        {"Open": close, "High": close * 1.005, "Low": close * 0.995, "Close": close, "Volume": volume},
        index=pd.bdate_range(start=frame.index[-1] + pd.Timedelta(days=1), periods=sessions),
    )
    return pd.concat([frame, added])


def signal(result, identifier):
    return next(item for item in result["signals"] if item["id"] == identifier)


class CompletenessSourceIsNotACallerStringTests(unittest.TestCase):
    def test_the_request_surface_does_not_publish_a_way_to_claim_independence(self) -> None:
        self.assertNotIn("completeness_source", CAPABILITIES["ticker.setup"].inputs)

    def test_a_request_naming_it_anyway_is_refused_rather_than_believed(self) -> None:
        frame, anchors = base_series()
        runtime = Runtime(price_history=lambda ticker, requested: _snapshot(frame))

        with self.assertRaises(RequestError):
            execute(
                "ticker.setup",
                {
                    "ticker": "TEST",
                    "as_of": frame.index[-1].date().isoformat(),
                    "swing": anchor_dates(frame, anchors),
                    "completeness_source": "independent_segmentation",
                    "no_cache": True,
                },
                runtime=runtime,
            )

    def test_a_fully_read_setup_over_a_segmentation_the_harness_produced_is_ready(self) -> None:
        """The lock slice two left, opened by the detector rather than by a caller's word."""

        frame, anchors = base_series()
        runtime = Runtime(price_history=lambda ticker, requested: _snapshot(frame))

        payload = execute(
            "ticker.setup",
            {
                "ticker": "TEST",
                "as_of": frame.index[-1].date().isoformat(),
                "swing": anchor_dates(frame, anchors),
                "right_side_development": "constructive",
                "chain_completeness": "complete",
                "approved_bars": bars_fingerprint(frame),
                "entry_proximity": "at_pivot",
                "entry_price": float(frame["Close"].iloc[-1]),
                "no_cache": True,
            },
            runtime=runtime,
        )

        self.assertEqual(payload["data"]["setup_state"], "ready")
        self.assertEqual(payload["data"]["missing"], [])


class ChaseIsAJudgementWithItsNumbersPrintedTests(unittest.TestCase):
    """The price being judged is one the tape recorded, and how far is too far is the reader's.

    Two mechanical rules were tried here and both had to go. Comparing the entry with the
    breakout's own extension called a twenty-percent gap that ticked down "at the pivot" and
    refused a one-cent advance the day after a three-percent breakout. Treating a declared
    price as available because it fell inside the latest bar's low-to-high range promoted
    something a daily bar cannot show -- that every price between its extremes traded, and
    that a session which closed fifty percent higher still offers its low.
    """

    def test_the_distance_judged_is_the_latest_completed_close(self) -> None:
        frame, anchors = base_series()
        chain = anchor_dates(frame, anchors)

        result = evaluate_setup(build_setup_evidence(frame, chain, **vouched(frame, chain)))

        chase = signal(result, "setup.chase_limit_above_pivot")
        self.assertAlmostEqual(
            chase["measured"]["latest_close_extension_above_pivot_pct"],
            result["measurements"]["pivot_extension_pct"],
            places=6,
        )

    def test_a_declared_price_is_carried_but_decides_nothing(self) -> None:
        frame, anchors = base_series()
        chain = anchor_dates(frame, anchors)
        outside = float(frame["High"].max()) * 5

        with_price = evaluate_setup(build_setup_evidence(frame, chain, **vouched(frame, chain, entry_price=outside)))
        without = evaluate_setup(build_setup_evidence(frame, chain, **vouched(frame, chain, entry_price=None)))

        chase = signal(with_price, "setup.chase_limit_above_pivot")
        self.assertFalse(chase["measured"]["declared_entry_inside_latest_daily_range"])
        self.assertEqual(chase["state"], signal(without, "setup.chase_limit_above_pivot")["state"])
        self.assertEqual(with_price["setup_state"], without["setup_state"])

    def test_at_pivot_is_refused_on_a_pivot_price_has_not_cleared(self) -> None:
        frame, anchors = base_series(breakout=False)
        chain = anchor_dates(frame, anchors)

        result = evaluate_setup(build_setup_evidence(frame, chain, **vouched(frame, chain)))

        self.assertEqual(signal(result, "setup.chase_limit_above_pivot")["state"], "fail")

    def test_the_distance_is_still_reported_against_the_buffer_the_source_named(self) -> None:
        frame, anchors = base_series()
        chain = anchor_dates(frame, anchors)

        evidence = build_setup_evidence(frame, chain, **vouched(frame, chain))

        buffer_signal = next(item for item in evidence["signals"] if "minervini_5_to_20_cents" in item["id"])
        self.assertEqual(buffer_signal["role"], "band")
        self.assertEqual(buffer_signal["state"], "within_source_range")


class BaseFailureIsNotAPivotFailureTests(unittest.TestCase):
    """"a base failure, which requires building a whole new base ... and a pivot failure,
    which can reset and recover within a small number of days." Two kinds, one counter."""

    def test_breaking_the_base_low_kills_the_structure_rather_than_counting_an_attempt(self) -> None:
        frame, anchors = base_series()
        chain = anchor_dates(frame, anchors)
        pivot = float(frame.loc[chain[-1], "High"])
        # Under the base's own low, which is what the source calls a base failure.
        collapsed = tail(frame, 2, close=float(frame.loc[chain[5], "Low"]) * 0.7, volume=2_000_000.0)
        recovered = tail(collapsed, 1, close=pivot * 1.02, volume=3_000_000.0)

        result = evaluate_setup(build_setup_evidence(recovered, chain, **vouched(recovered, chain, pivot_reset="prompt_reset")))

        self.assertTrue(result["measurements"]["base_failed_after_pivot"])
        self.assertEqual(signal(result, "setup.failure_reset_types")["state"], "fail")
        self.assertNotEqual(result["setup_state"], "ready")

    def test_a_shallow_slip_above_the_base_low_is_the_recoverable_kind(self) -> None:
        frame, anchors = base_series()
        chain = anchor_dates(frame, anchors)
        pivot = float(frame.loc[chain[-1], "High"])
        slipped = tail(frame, 3, close=pivot * 0.97, volume=600_000.0)
        recovered = tail(slipped, 2, close=pivot * 1.03, volume=1_800_000.0)
        available = float(recovered["Close"].iloc[-1])
        # The base, not the detector's chain over the extended frame: appending five flat
        # sessions at one price makes turns of its own at a scale finer than these bars, and the
        # subject here is which kind of failure a slip below the pivot is.
        chain = anchor_dates(frame, anchors)

        result = evaluate_setup(
            build_setup_evidence(recovered, chain, **vouched(recovered, chain, pivot_reset="prompt_reset", entry_price=available))
        )

        self.assertFalse(result["measurements"]["base_failed_after_pivot"])
        self.assertEqual(result["measurements"]["sessions_below_pivot_after_breakout"], 3)
        self.assertEqual(signal(result, "setup.failure_reset_types")["state"], "pass")
        self.assertNotIn("setup.failure_reset_types", result["failed"])

    def test_how_long_the_stock_spent_below_the_pivot_travels_with_the_verdict(self) -> None:
        """"Within a small number of days" has no number, so the count is what gets printed."""

        frame, anchors = base_series()
        chain = anchor_dates(frame, anchors)
        pivot = float(frame.loc[chain[-1], "High"])
        long_slip = tail(frame, 60, close=pivot * 0.97, volume=600_000.0)
        recovered = tail(long_slip, 2, close=pivot * 1.03, volume=1_800_000.0)

        result = evaluate_setup(build_setup_evidence(recovered, chain, **vouched(recovered, chain, pivot_reset="prompt_reset")))

        self.assertEqual(signal(result, "setup.failure_reset_types")["measured"]["sessions_below_pivot_after_breakout"], 60)


def _snapshot(frame):
    from datetime import datetime, timezone

    from scripts.minervini.providers import ProviderSnapshot, SnapshotMeta

    return ProviderSnapshot(
        frame,
        SnapshotMeta(
            provider="fixture-prices",
            retrieved_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            as_of=frame.index[-1].date(),
            coverage={"completed_only": True},
        ),
    )




class LongResetNeedsJudgingTests(unittest.TestCase):
    def test_sixty_sessions_under_water_is_not_a_prompt_reset_by_default(self) -> None:
        """Reporting the count and passing anyway answers "a small number of days" silently."""

        frame, anchors = base_series()
        chain = anchor_dates(frame, anchors)
        pivot = float(frame.loc[chain[-1], "High"])
        under = tail(frame, 60, close=pivot * 0.97, volume=600_000.0)
        recovered = tail(under, 2, close=pivot * 1.03, volume=1_800_000.0)

        result = evaluate_setup(build_setup_evidence(recovered, chain, **vouched(recovered, chain)))

        reset = signal(result, "setup.failure_reset_types")
        self.assertEqual(reset["state"], "needs_chart")
        self.assertEqual(reset["measured"]["longest_spell_below_pivot"], 60)
        self.assertNotEqual(result["setup_state"], "ready")

    def test_a_reader_who_calls_it_stale_stops_it(self) -> None:
        frame, anchors = base_series()
        chain = anchor_dates(frame, anchors)
        pivot = float(frame.loc[chain[-1], "High"])
        under = tail(frame, 60, close=pivot * 0.97, volume=600_000.0)
        recovered = tail(under, 2, close=pivot * 1.03, volume=1_800_000.0)

        result = evaluate_setup(build_setup_evidence(recovered, chain, **vouched(recovered, chain, pivot_reset="stale_reset")))

        self.assertEqual(signal(result, "setup.failure_reset_types")["state"], "fail")

    def test_a_base_that_never_failed_needs_no_reading_at_all(self) -> None:
        frame, anchors = base_series()
        chain = anchor_dates(frame, anchors)

        result = evaluate_setup(build_setup_evidence(frame, chain, **vouched(frame, chain)))

        self.assertEqual(signal(result, "setup.failure_reset_types")["state"], "pass")
        self.assertEqual(result["setup_state"], "ready")


class DeadBaseHasNoLiveTriggerTests(unittest.TestCase):
    def test_a_base_failure_takes_the_trigger_with_it(self) -> None:
        frame, anchors = base_series()
        chain = anchor_dates(frame, anchors)
        pivot = float(frame.loc[chain[-1], "High"])
        collapsed = tail(frame, 2, close=float(frame.loc[chain[5], "Low"]) * 0.7, volume=2_000_000.0)
        recovered = tail(collapsed, 1, close=pivot * 1.02, volume=3_000_000.0)

        result = evaluate_setup(build_setup_evidence(recovered, chain, **vouched(recovered, chain)))

        self.assertEqual(signal(result, "setup.structural_pivot_and_trigger")["state"], "fail")
        self.assertEqual(signal(result, "setup.failure_reset_types")["state"], "fail")


class SkippedChainAgainstADetectorTests(unittest.TestCase):
    def test_a_chain_missing_a_turning_point_the_detector_found_is_refused(self) -> None:
        """The seam the detector fills, exercised through the seam rather than around it."""

        frame, anchors = base_series(depths=(30.0, 5.0, 10.0, 2.0))
        detected = anchor_dates(frame, anchors)
        skipped = [detected[index] for index in (0, 1, 2, 5, 6, 7, 8)]

        result = evaluate_setup(
            build_setup_evidence(frame, skipped, **vouched(frame, skipped))
        )

        completeness = signal(result, "setup.declared_chain_completeness")
        self.assertEqual(completeness["state"], "fail")
        self.assertTrue(completeness["measured"]["differs"]["detected_only"])
        self.assertNotEqual(result["setup_state"], "ready")




class OnlyTheSegmentationThatVouchedIsMeasuredTests(unittest.TestCase):
    """Allowing a finer caller chain looked harmless and was not.

    Everything downstream measures the declared chain, so a caller who keeps every detected
    date and cuts one unfavourable contraction into four smaller ones skips nothing, moves no
    endpoint, and still deletes the contraction from the sequence that gets judged. A
    segmentation can vouch for the segmentation it produced and no other.
    """

    def test_a_chain_the_detector_did_not_produce_is_not_the_chain_that_was_vouched_for(self) -> None:
        """Any difference, in either direction: an omitted turn hides a contraction and an
        added one splits it, and both leave the sequence that gets judged unlike the one the
        segmentation vouched for."""

        frame, chain, finer = hidden_turn_series()
        # The chain has to survive the structure resolver to reach the comparison at all. An
        # earlier version inserted an out-of-order date, so the resolver rejected it first and
        # the test passed without the equality rule existing.
        self.assertEqual(detected(frame), chain)

        result = evaluate_setup(build_setup_evidence(frame, finer, **vouched(frame, finer)))

        completeness = signal(result, "setup.declared_chain_completeness")
        self.assertEqual(completeness["state"], "fail")
        self.assertEqual(completeness["measured"]["differs"]["declared_only"], finer[1:3])
        self.assertNotEqual(result["setup_state"], "ready")

    def test_the_chain_the_detector_produced_is_the_one_that_passes(self) -> None:
        frame, anchors = base_series()
        chain = anchor_dates(frame, anchors)

        result = evaluate_setup(build_setup_evidence(frame, chain, **vouched(frame, chain)))

        self.assertEqual(signal(result, "setup.declared_chain_completeness")["state"], "pass")
        self.assertEqual(result["setup_state"], "ready")


class ADeepBaseIsStillOneBaseTests(unittest.TestCase):
    """Contractions that contract the whole way describe one structure, however deep it is."""

    def test_a_forty_percent_base_whose_depths_contract_is_read_as_one(self) -> None:
        frame, left_behind, current = borrowed_contraction_series()
        chain = detected(frame)

        result = evaluate_setup(build_setup_evidence(frame, chain, **vouched(frame, chain)))

        self.assertEqual(chain, [*left_behind, *current])
        depths = result["measurements"]["contraction_depths_pct"]
        self.assertEqual([round(depth) for depth in depths], [40, 15, 7])
        self.assertEqual(signal(result, "setup.contractions_must_contract")["state"], "pass")

    def test_its_depth_is_reported_against_the_source_range_it_sits_outside(self) -> None:
        """Forty percent clears the fifty percent gate and sits past the healthy band. Both are
        said, because the gate is what decides and the band is what a reader weighs."""

        frame, _, _ = borrowed_contraction_series()
        chain = detected(frame)

        result = evaluate_setup(build_setup_evidence(frame, chain, **vouched(frame, chain)))

        self.assertEqual(signal(result, "market.correction_depth_healthy_leader.correction_failure_threshold")["state"], "pass")
        band = signal(result, "market.correction_depth_healthy_leader.healthy_correction_range")
        self.assertEqual(band["state"], "beyond_source_range")


class ChaseAfterAGapBreakoutTests(unittest.TestCase):
    """A breakout that gaps twenty percent above the pivot and eases back one percent.

    Nothing here refuses the reading -- the source gives no number and the contract says so
    out loud -- but the distance is in the signal, and this pins the price path so a later
    change cannot quietly stop reporting it. The residual is stated rather than hidden: a
    reader who calls nineteen percent "at the pivot" is doing it in front of the number.
    """

    def _gapped_then_eased(self):
        frame, anchors = base_series(breakout=False)
        chain = anchor_dates(frame, anchors)
        pivot = float(frame.loc[chain[-1], "High"])
        gapped = tail(frame, 1, close=pivot * 1.20, volume=4_000_000.0)
        return tail(gapped, 1, close=pivot * 1.19, volume=1_200_000.0), chain

    def test_the_whole_distance_from_the_pivot_is_in_the_signal(self) -> None:
        eased, chain = self._gapped_then_eased()
        frame, anchors = base_series(breakout=False)

        result = evaluate_setup(build_setup_evidence(eased, chain, **vouched(eased, chain)))

        chase = signal(result, "setup.chase_limit_above_pivot")
        self.assertGreater(chase["measured"]["latest_close_extension_above_pivot_pct"], 18.0)
        self.assertEqual(chase["measured"]["sessions_since_breakout"], 1)

    def test_calling_that_distance_chased_is_what_stops_it(self) -> None:
        eased, chain = self._gapped_then_eased()
        frame, anchors = base_series(breakout=False)

        result = evaluate_setup(build_setup_evidence(eased, chain, **vouched(eased, chain, entry_proximity="chased")))

        self.assertEqual(signal(result, "setup.chase_limit_above_pivot")["state"], "fail")
        self.assertNotEqual(result["setup_state"], "ready")

    def test_and_calling_it_at_the_pivot_is_a_reader_declaring_against_a_printed_number(self) -> None:
        """The accepted trust boundary, pinned so a change to it is a change to this test."""

        eased, _ = self._gapped_then_eased()
        chain = detected(eased)

        result = evaluate_setup(build_setup_evidence(eased, chain, **vouched(eased, chain)))

        self.assertEqual(result["setup_state"], "ready")
        self.assertGreater(signal(result, "setup.chase_limit_above_pivot")["measured"]["latest_close_extension_above_pivot_pct"], 18.0)




class ProximityReadsWherePriceIsNowTests(unittest.TestCase):
    def test_a_pivot_cleared_once_and_since_given_back_is_not_where_price_is_now(self) -> None:
        """`pivot_cleared` records that a breakout happened, not that price is above the pivot.

        Reading it for a signal whose whole subject is the latest close let that signal pass
        while reporting a distance of minus one percent.
        """

        frame, anchors = base_series()
        chain = anchor_dates(frame, anchors)
        pivot = float(frame.loc[chain[-1], "High"])
        back_under = tail(frame, 2, close=pivot * 0.99, volume=700_000.0)

        result = evaluate_setup(build_setup_evidence(back_under, chain, **vouched(back_under, chain, pivot_reset="prompt_reset")))

        chase = signal(result, "setup.chase_limit_above_pivot")
        self.assertLess(chase["measured"]["latest_close_extension_above_pivot_pct"], 0)
        self.assertEqual(chase["state"], "fail")


if __name__ == "__main__":
    unittest.main()
