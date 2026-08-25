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
VOUCHED = {**READ, "chain_completeness": "complete", "completeness_source": "independent_segmentation"}


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

        result = evaluate_setup(build_setup_evidence(after, anchor_dates(frame, anchors), **VOUCHED))

        self.assertEqual(signal(result, "setup.chase_limit_above_pivot")["state"], "pass")

    def test_the_distance_is_reported_against_the_buffer_the_source_named(self) -> None:
        frame, anchors = base_series()

        evidence = build_setup_evidence(frame, anchor_dates(frame, anchors), **VOUCHED)

        buffer_signal = next(
            item for item in evidence["signals"]
            if item["id"].startswith("practitioners.chase.minervini_5_to_20_cents")
        )
        self.assertEqual(buffer_signal["role"], "band")
        self.assertEqual(buffer_signal["state"], "beyond_source_range")


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

        result = evaluate_setup(build_setup_evidence(recovered, chain, **VOUCHED))

        self.assertTrue(result["measurements"]["base_failed_after_pivot"])
        self.assertEqual(signal(result, "setup.failure_reset_types")["state"], "fail")
        self.assertNotEqual(result["setup_state"], "ready")

    def test_a_shallow_slip_above_the_base_low_is_the_recoverable_kind(self) -> None:
        frame, anchors = base_series()
        chain = anchor_dates(frame, anchors)
        pivot = float(frame.loc[chain[-1], "High"])
        slipped = tail(frame, 3, close=pivot * 0.97, volume=600_000.0)
        recovered = tail(slipped, 2, close=pivot * 1.03, volume=1_800_000.0)

        result = evaluate_setup(build_setup_evidence(recovered, chain, **VOUCHED))

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

        result = evaluate_setup(build_setup_evidence(recovered, chain, **VOUCHED))

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


if __name__ == "__main__":
    unittest.main()
