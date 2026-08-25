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
from tests.series import anchor_dates, base_series


READ = {"right_side_development": "constructive", "entry_proximity": "at_pivot"}
READ = {"right_side_development": "constructive", "entry_proximity": "at_pivot", "entry_price": None}


def vouched(frame, chain, **overrides):
    """A chain the detector would have produced, plus an entry at the pivot."""

    pivot = float(frame.loc[chain[-1], "High"])
    return {
        "right_side_development": "constructive",
        "chain_completeness": "complete",
        "detected_chain": chain,
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

    def test_no_request_can_reach_ready_on_the_standard_route_yet(self) -> None:
        """The seam exists for the detector to fill; nothing else can fill it."""

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
                "entry_proximity": "at_pivot",
                "no_cache": True,
            },
            runtime=runtime,
        )

        self.assertEqual(payload["data"]["setup_state"], "incomplete")
        self.assertIn("setup.declared_chain_completeness", {item["id"] for item in payload["missing"]})


class ChaseIsAJudgementWithItsNumbersPrintedTests(unittest.TestCase):
    """Comparing the entry with the breakout's own extension cut in the wrong place.

    It let a twenty-percent gap breakout that ticked down one percent read as "at the pivot",
    and refused a one-cent advance the day after a three-percent breakout. The source names a
    limit and withholds the number, so the call is the reader's; what travels with it is the
    distance, and Minervini's own stated buffer beside it.
    """

    def test_a_normal_follow_through_session_is_not_refused(self) -> None:
        frame, anchors = base_series()
        after = tail(frame, 1, close=float(frame["Close"].iloc[-1]) * 1.0001, volume=800_000.0)

        result = evaluate_setup(build_setup_evidence(after, anchor_dates(frame, anchors), **vouched(frame, anchor_dates(frame, anchors))))

        self.assertEqual(signal(result, "setup.chase_limit_above_pivot")["state"], "pass")

    def test_an_entry_far_above_the_pivot_cannot_be_read_as_at_the_pivot(self) -> None:
        """Refused by the only number the source ever put on this distance, not by a new one."""

        frame, anchors = base_series()
        chain = anchor_dates(frame, anchors)
        far = vouched(frame, chain, entry_price=float(frame["Close"].iloc[-1]))

        result = evaluate_setup(build_setup_evidence(frame, chain, **far))

        buffer_signal = next(item for item in result["signals"] if "minervini_5_to_20_cents" in item["id"])
        self.assertEqual(buffer_signal["role"], "band")
        self.assertEqual(buffer_signal["state"], "beyond_source_range")
        self.assertEqual(signal(result, "setup.chase_limit_above_pivot")["state"], "fail")
        self.assertNotEqual(result["setup_state"], "ready")

    def test_an_entry_inside_that_buffer_reads_as_at_the_pivot(self) -> None:
        frame, anchors = base_series()
        chain = anchor_dates(frame, anchors)

        result = evaluate_setup(build_setup_evidence(frame, chain, **vouched(frame, chain)))

        self.assertEqual(signal(result, "setup.chase_limit_above_pivot")["state"], "pass")

    def test_without_an_entry_price_the_reading_has_nothing_to_be_about(self) -> None:
        frame, anchors = base_series()
        chain = anchor_dates(frame, anchors)

        result = evaluate_setup(build_setup_evidence(frame, chain, **vouched(frame, chain, entry_price=None)))

        self.assertEqual(signal(result, "setup.chase_limit_above_pivot")["state"], "needs_chart")


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

        result = evaluate_setup(build_setup_evidence(recovered, chain, **vouched(frame, chain, pivot_reset="prompt_reset")))

        self.assertTrue(result["measurements"]["base_failed_after_pivot"])
        self.assertEqual(signal(result, "setup.failure_reset_types")["state"], "fail")
        self.assertNotEqual(result["setup_state"], "ready")

    def test_a_shallow_slip_above_the_base_low_is_the_recoverable_kind(self) -> None:
        frame, anchors = base_series()
        chain = anchor_dates(frame, anchors)
        pivot = float(frame.loc[chain[-1], "High"])
        slipped = tail(frame, 3, close=pivot * 0.97, volume=600_000.0)
        recovered = tail(slipped, 2, close=pivot * 1.03, volume=1_800_000.0)

        result = evaluate_setup(build_setup_evidence(recovered, chain, **vouched(frame, chain, pivot_reset="prompt_reset")))

        self.assertFalse(result["measurements"]["base_failed_after_pivot"])
        self.assertEqual(result["measurements"]["sessions_below_pivot_after_breakout"], 3)
        self.assertEqual(result["setup_state"], "ready")

    def test_how_long_the_stock_spent_below_the_pivot_travels_with_the_verdict(self) -> None:
        """"Within a small number of days" has no number, so the count is what gets printed."""

        frame, anchors = base_series()
        chain = anchor_dates(frame, anchors)
        pivot = float(frame.loc[chain[-1], "High"])
        long_slip = tail(frame, 60, close=pivot * 0.97, volume=600_000.0)
        recovered = tail(long_slip, 2, close=pivot * 1.03, volume=1_800_000.0)

        result = evaluate_setup(build_setup_evidence(recovered, chain, **vouched(frame, chain, pivot_reset="prompt_reset")))

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

        result = evaluate_setup(build_setup_evidence(recovered, chain, **vouched(frame, chain)))

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

        result = evaluate_setup(build_setup_evidence(recovered, chain, **vouched(frame, chain, pivot_reset="stale_reset")))

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

        result = evaluate_setup(build_setup_evidence(recovered, chain, **vouched(frame, chain)))

        self.assertEqual(signal(result, "setup.structural_pivot_and_trigger")["state"], "fail")
        self.assertEqual(signal(result, "setup.failure_reset_types")["state"], "fail")


class SkippedChainAgainstADetectorTests(unittest.TestCase):
    def test_a_chain_missing_a_turning_point_the_detector_found_is_refused(self) -> None:
        """The seam the detector fills, exercised through the seam rather than around it."""

        frame, anchors = base_series(depths=(30.0, 5.0, 10.0, 2.0))
        full = anchor_dates(frame, anchors)
        skipped = [full[index] for index in (0, 1, 2, 5, 6, 7, 8)]

        result = evaluate_setup(
            build_setup_evidence(frame, skipped, **vouched(frame, skipped, detected_chain=full))
        )

        completeness = signal(result, "setup.declared_chain_completeness")
        self.assertEqual(completeness["state"], "fail")
        self.assertTrue(completeness["measured"]["omitted"])
        self.assertNotEqual(result["setup_state"], "ready")


if __name__ == "__main__":
    unittest.main()
