"""The candidate segmentation, published so a person can look at it before it is used.

Running the detector inside `ticker.setup` closes the forgery, and closing it that way makes
the segmentation invisible: the verdict would rest on a chain nobody saw. This capability is
where it becomes visible, and it deliberately decides nothing -- it proposes, the chart shows,
and the analyst declares back what they approved.
"""

from __future__ import annotations

from datetime import datetime, timezone
import unittest

from scripts.minervini.cli import format_payload
from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot, SnapshotMeta
from tests.series import anchor_dates, base_series


def snapshot(**kwargs):
    frame, anchors = base_series(**kwargs)
    meta = SnapshotMeta(
        provider="fixture-prices",
        retrieved_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        as_of=frame.index[-1].date(),
        coverage={"completed_only": True},
    )
    return ProviderSnapshot(frame, meta), anchor_dates(frame, anchors)


def run(**kwargs) -> dict:
    prices, _ = snapshot(**kwargs)
    runtime = Runtime(price_history=lambda ticker, requested: prices)
    return execute(
        "ticker.swings",
        {"ticker": "TEST", "as_of": prices.meta.as_of.isoformat(), "no_cache": True},
        runtime=runtime,
    )


class ProposesAChainTests(unittest.TestCase):
    def test_the_candidate_chain_is_the_one_setup_will_corroborate_against(self) -> None:
        prices, declared = snapshot()

        payload = run()

        self.assertEqual(payload["status"], "ok")
        self.assertEqual([anchor["date"] for anchor in payload["data"]["anchors"]], declared)

    def test_the_leg_price_is_in_now_is_named_apart_from_the_base(self) -> None:
        payload = run()

        self.assertNotIn(payload["data"]["live_leg"]["date"], [anchor["date"] for anchor in payload["data"]["anchors"]])

    def test_the_parameters_and_the_session_count_travel_with_the_proposal(self) -> None:
        payload = run()

        self.assertIn("retracement_pct", payload["data"]["parameters"])
        self.assertGreater(payload["data"]["sessions"], 0)

    def test_it_points_at_the_chart_next_because_a_proposal_is_not_an_approval(self) -> None:
        payload = run()

        self.assertIn("ticker.chart", payload["next_capabilities"])


class DeclinesToProposeTests(unittest.TestCase):
    def test_a_segmentation_neighbouring_parameters_disagree_with_proposes_nothing(self) -> None:
        payload = run(depths=(25.0, 10.0, 1.2))

        self.assertEqual(payload["data"]["state"], "unstable")
        self.assertEqual(payload["data"]["anchors"], [])
        self.assertTrue(payload["data"]["sensitivity"])

    def test_it_does_not_ask_the_caller_for_something_they_cannot_supply(self) -> None:
        """`needs_input` names a caller who can act. This one cannot.

        The parameters are deliberately not caller inputs, so there is no argument that turns
        an unstable segmentation into a stable one. Saying needs_input sends a reader looking
        for a flag that does not exist and was never going to.
        """

        payload = run(depths=(25.0, 10.0, 1.2))

        self.assertEqual(payload["status"], "unavailable")

    def test_the_reason_names_which_of_the_two_causes_it_was(self) -> None:
        """Parameter disagreement and an unreadable session are different problems."""

        payload = run(depths=(25.0, 10.0, 1.2))

        self.assertEqual([item["reason"] for item in payload["missing"]], ["neighbouring_parameters_disagree"])

    def test_it_does_not_point_at_a_chart_that_would_draw_no_anchors(self) -> None:
        """The chart is where a proposal becomes an approval, and there is no proposal."""

        payload = run(depths=(25.0, 10.0, 1.2))

        self.assertEqual(payload["next_capabilities"], [])


class CompactKeepsTheAnswerTests(unittest.TestCase):
    """Compact is allowed to drop detail. The proposal itself is not detail."""

    def test_the_compact_form_still_carries_the_chain_it_proposed(self) -> None:
        """A blanket omit-by-key-name list deleted this capability's whole answer.

        `anchors` is supporting detail inside a setup's segmentation and is the entire output
        here, so a filter that reads only the key name cannot tell the two apart.
        """

        payload = run()

        compact = format_payload(payload, "compact")

        self.assertEqual(
            [anchor["date"] for anchor in compact["data"]["anchors"]],
            [anchor["date"] for anchor in payload["data"]["anchors"]],
        )

    def test_the_exception_covers_the_answer_and_not_the_detail_under_it(self) -> None:
        """A key name is not a place. `sensitivity` is a list of chains that disagreed, and its
        own anchor lists are exactly the verbose basis compact exists to drop."""

        payload = run(depths=(25.0, 10.0, 1.2))

        compact = format_payload(payload, "compact")

        self.assertTrue(payload["data"]["sensitivity"][0]["anchors"])
        self.assertNotIn("anchors", compact["data"]["sensitivity"][0])
        self.assertIn("anchors", compact["data"])

    def test_compact_and_full_still_mean_the_same_thing(self) -> None:
        payload = run()

        compact = format_payload(payload, "compact")

        for key in ("status", "signals", "missing"):
            with self.subTest(key=key):
                self.assertEqual(compact[key], payload[key])
        self.assertEqual(compact["data"]["state"], payload["data"]["state"])


class DecidesNothingTests(unittest.TestCase):
    def test_the_capability_returns_no_verdict_of_its_own(self) -> None:
        payload = run()

        self.assertNotIn("setup_state", payload["data"])
        self.assertEqual(payload["signals"], [])


if __name__ == "__main__":
    unittest.main()
