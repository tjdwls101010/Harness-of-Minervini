"""A named tactic has to be the tactic it is named after.

The generic early route accepted a promise -- opt in, list your debt, name a later pivot and an
invalidation -- and asked nothing about what the entry actually was. "Taken before the pivot" and
"taken for no stated reason" arrived identically, and the envelope called both of them the same
tactic. The source is not so vague: it says every entry tactic has a pivot that triggers it and a
level it is abandoned at, and it defines five of them by exactly those two things.
"""

from __future__ import annotations

import unittest

from scripts.minervini.setup import evaluate_setup
from scripts.minervini.setup_evidence import build_setup_evidence
from tests.readings import full as readings
from tests.series import anchor_dates, base_series


PROMISE = {
    "confirmation_debt": ["completed Minervini pivot breakout"],
    "minervini_later_pivot": {"price": 104.5, "condition": "completed close above 104.5"},
    "invalidation": {"price": 96.0, "condition": "completed close below 96.0"},
}
TACTICS = (
    "key_support_level_reclaim",
    "consolidation_pivot_breakout",
    "key_moving_average_pullback",
    "oops_reversal",
    "key_support_level_pullback",
)


def verdict(kind, **entry):
    frame, anchors = base_series()
    chain = anchor_dates(frame, anchors)
    return evaluate_setup(
        build_setup_evidence(
            frame,
            chain,
            entry_kind=kind,
            entry={**PROMISE, **entry},
            tactic_opt_in=True,
            **readings(frame, chain),
        )
    )


class TheGenericEarlyRouteIsGone(unittest.TestCase):
    def test_an_early_entry_with_no_tactic_named_is_not_a_route(self) -> None:
        result = verdict("tl_early")

        self.assertNotEqual(result["setup_state"], "ready")
        self.assertIn("named_entry_tactic", result["missing"])


class EachTacticAsksForItsOwnEvidence(unittest.TestCase):
    def test_every_tactic_names_the_evidence_it_is_still_waiting_on(self) -> None:
        for tactic in TACTICS:
            with self.subTest(tactic=tactic):
                result = verdict(tactic)

                self.assertNotEqual(result["setup_state"], "ready")
                self.assertTrue(
                    [item for item in result["missing"] if item.startswith(f"tactic.{tactic}.")],
                    f"{tactic} asked for nothing of its own",
                )

    def test_the_evidence_one_tactic_needs_does_not_satisfy_another(self) -> None:
        """A gap below yesterday's low is an oops reversal and is not a moving average pullback.

        Sharing one bucket of early-entry evidence is how the generic route let any declaration
        stand in for any other. Each tactic's conditions are its own.
        """
        oops = {item for item in verdict("oops_reversal")["missing"] if item.startswith("tactic.")}
        pullback = {item for item in verdict("key_moving_average_pullback")["missing"] if item.startswith("tactic.")}

        self.assertTrue(oops)
        self.assertTrue(pullback)
        self.assertEqual(oops & pullback, set())


class TheDoctrineTravelsWithTheVerdict(unittest.TestCase):
    def test_the_declared_tactic_names_its_claim(self) -> None:
        for tactic in TACTICS:
            with self.subTest(tactic=tactic):
                self.assertIn(f"tactic.{tactic}", verdict(tactic)["doctrine_ids"])


class OptingInIsStillRequired(unittest.TestCase):
    def test_a_named_tactic_without_opt_in_is_still_unresolved(self) -> None:
        frame, anchors = base_series()
        chain = anchor_dates(frame, anchors)
        result = evaluate_setup(
            build_setup_evidence(
                frame, chain, entry_kind="oops_reversal", entry=PROMISE, **readings(frame, chain)
            )
        )

        self.assertIn("tl_early_opt_in", result["missing"])
