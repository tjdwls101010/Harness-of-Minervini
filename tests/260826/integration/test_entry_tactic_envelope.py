"""The declared tactic reaches the envelope, and so does the reason it is not one.

A caller who names a tactic is held to that tactic's evidence and is told which claim they are
being held to. A caller who says only "early" is told the word named nothing -- a different gap
from evidence they could have supplied, and fixed by a different action.
"""

from __future__ import annotations

from datetime import datetime, timezone
import unittest

from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot, SnapshotMeta
from scripts.minervini.setup_structure import bars_fingerprint
from tests.series import anchor_dates, base_series


def run(entry_kind: str, **overrides) -> dict:
    frame, anchors = base_series()
    prices = ProviderSnapshot(
        frame,
        SnapshotMeta(
            provider="fixture-prices",
            retrieved_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            as_of=frame.index[-1].date(),
            coverage={"completed_only": True},
        ),
    )
    price = float(frame["Close"].iloc[-1])
    request = {
        "ticker": "TEST",
        "as_of": prices.meta.as_of.isoformat(),
        "swing": anchor_dates(frame, anchors),
        "right_side_development": "constructive",
        "chain_completeness": "complete",
        "approved_bars": bars_fingerprint(frame),
        "entry_proximity": "at_pivot",
        "entry_price": price,
        "entry_kind": entry_kind,
        "tactic_opt_in": True,
        "confirmation_debt": ["completed Minervini pivot breakout"],
        "later_pivot_price": price * 1.05,
        "later_pivot_condition": "completed close above the base pivot",
        "invalidation_price": price * 0.95,
        "invalidation_condition": "completed close below the reclaimed level",
        "no_cache": True,
        **overrides,
    }
    return execute("ticker.setup", request, runtime=Runtime(price_history=lambda ticker, requested: prices))


class TheTacticTravelsWithTheAnswer(unittest.TestCase):
    def test_the_declared_tactic_is_cited(self) -> None:
        payload = run("key_support_level_reclaim")

        self.assertIn("tactic.key_support_level_reclaim", payload["doctrine_ids"])
        self.assertIn("tactic.early_entry_confirmation_debt", payload["doctrine_ids"])

    def test_the_conditions_it_still_owes_are_named_one_by_one(self) -> None:
        payload = run("oops_reversal")
        owed = {item["id"] for item in payload["missing"]}

        self.assertIn("tactic.oops_reversal.prior_day_low", owed)
        self.assertIn("tactic.oops_reversal.gap_below_prior_low", owed)
        self.assertNotIn("tactic.key_moving_average_pullback.respected_moving_average", owed)


class TheWordEarlyNamesNothing(unittest.TestCase):
    def test_an_unnamed_early_entry_says_so_in_its_own_words(self) -> None:
        payload = run("tl_early")
        reasons = {item["id"]: item["reason"] for item in payload["missing"]}

        self.assertEqual(reasons["named_entry_tactic"], "no_tactic_named")


class TheReservedNamesAreRefusedRatherThanIgnored(unittest.TestCase):
    """Ignored quietly, a caller believes they opted in and reads a gap they cannot explain.

    The request already refuses supplying a segmentation or naming its own completeness source,
    for the same reason: these are contract terms with their own arguments, and a payload that
    restates them is a caller who has misunderstood the seam rather than one making a choice.
    """

    def test_an_entry_that_restates_the_route_is_refused(self) -> None:
        from scripts.minervini.contracts import RequestError

        with self.assertRaises(RequestError) as raised:
            run("oops_reversal", entry={"kind": "completed_pivot"})

        self.assertIn("entry_kind", str(raised.exception))

    def test_an_entry_that_opts_itself_in_is_refused(self) -> None:
        from scripts.minervini.contracts import RequestError

        with self.assertRaises(RequestError) as raised:
            run("oops_reversal", entry={"opt_in": True})

        self.assertIn("tactic_opt_in", str(raised.exception))
