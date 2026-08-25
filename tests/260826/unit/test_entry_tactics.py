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


class ADeclaredConditionIsAnsweredRatherThanRenamed(unittest.TestCase):
    """Naming the conditions is only half of it if none of them can ever be met.

    The route this replaced was a dead end: an early entry always came back owing a trigger
    nothing could supply. Splitting that into five named dead ends would rename the problem and
    keep it. What the source describes are things a trader reads off the chart, so the caller
    declares them and the declaration is listed back beside the verdict.
    """

    def test_declaring_every_condition_answers_them(self) -> None:
        result = verdict(
            "oops_reversal",
            prior_day_low={"price": 98.0, "condition": "yesterday's low"},
            gap_below_prior_low={"observed": True, "condition": "opened below 98.0"},
        )

        self.assertEqual([item for item in result["missing"] if item.startswith("tactic.")], [])

    def test_what_the_caller_said_is_listed_back(self) -> None:
        result = verdict(
            "oops_reversal",
            prior_day_low={"price": 98.0, "condition": "yesterday's low"},
            gap_below_prior_low={"observed": True, "condition": "opened below 98.0"},
        )

        self.assertIn("tactic.oops_reversal.prior_day_low", result["declared_readings"])

    def test_another_tactic_s_conditions_answer_nothing_here(self) -> None:
        result = verdict(
            "oops_reversal",
            respected_moving_average={"price": 98.0, "condition": "the 21 ema"},
            pullback_volume={"observed": True, "condition": "below average"},
        )

        self.assertIn("tactic.oops_reversal.prior_day_low", result["missing"])
        self.assertIn("tactic.oops_reversal.gap_below_prior_low", result["missing"])


class DeclaringATacticIsNotTheSameAsDenyingIt(unittest.TestCase):
    """A declaration that says the condition did not happen is evidence against, not evidence for.

    Counting any non-empty answer as satisfaction makes "the stock never gapped below yesterday's
    low" and "it gapped below and reclaimed it" the same input. The registry calls a contradicted
    practice claim a matter for review rather than a rejection, because TraderLion is read for
    contrast; what it must never be is a pass.
    """

    def test_a_condition_the_caller_says_did_not_happen_does_not_satisfy_it(self) -> None:
        result = verdict(
            "oops_reversal",
            prior_day_low={"price": 98.0, "condition": "yesterday's low"},
            gap_below_prior_low={"state": "fail", "condition": "the stock opened above 98.0"},
        )

        self.assertNotEqual(result["setup_state"], "ready")
        self.assertIn("tactic.oops_reversal.gap_below_prior_low", result["unsatisfied"])
        self.assertNotIn("tactic.oops_reversal.gap_below_prior_low", result["missing"])


class EveryTacticCanActuallyBeCompleted(unittest.TestCase):
    """The positive case, five times.

    Without it, "each tactic names what it owes" is satisfied just as well by a route that can
    never be paid, which is the route this slice replaced.
    """

    ANSWERS = {
        "key_support_level_reclaim": {
            "undercut_support_level": {"price": 96.0, "condition": "the 50-day average"},
            "prior_basing_weeks": {"weeks": 7, "condition": "consolidating since May"},
        },
        "consolidation_pivot_breakout": {
            "consolidation_pivot_level": {"price": 103.0, "condition": "the swing high of 12 June"},
            "traditional_base_pivot": {"price": 104.5, "condition": "the base pivot"},
        },
        "key_moving_average_pullback": {
            "respected_moving_average": {"price": 99.0, "condition": "the 21 ema, respected twice"},
            "pullback_volume": {"state": "pass", "condition": "below the 50-day average"},
            "relative_strength": {"state": "pass", "condition": "higher low against a lower market low"},
        },
        "oops_reversal": {
            "prior_day_low": {"price": 98.0, "condition": "yesterday's low"},
            "gap_below_prior_low": {"state": "pass", "condition": "opened below 98.0 and reclaimed it"},
        },
        "key_support_level_pullback": {
            "prior_pivot_level": {"price": 100.0, "condition": "the prior consolidation pivot"},
            "pullback_volume": {"state": "pass", "condition": "below the 50-day average"},
        },
    }

    def test_a_fully_declared_tactic_owes_nothing_of_its_own(self) -> None:
        for tactic, answers in self.ANSWERS.items():
            with self.subTest(tactic=tactic):
                result = verdict(tactic, **answers)

                self.assertEqual([item for item in result["missing"] if item.startswith("tactic.")], [])
                self.assertEqual([item for item in result["unsatisfied"] if item.startswith("tactic.")], [])

    def test_a_fully_declared_tactic_over_a_sound_base_is_ready(self) -> None:
        for tactic, answers in self.ANSWERS.items():
            with self.subTest(tactic=tactic):
                self.assertEqual(verdict(tactic, **answers)["setup_state"], "ready")


class AWordTheReducerCannotReadIsNotAPass(unittest.TestCase):
    def test_an_unrecognised_state_leaves_the_condition_owed(self) -> None:
        """Defaulting an unknown word to satisfied is how a denial becomes a pass.

        A declaration carrying no state at all is the caller saying what they saw, and it stands.
        A declaration that carries a state word this reducer does not know is a reading nobody
        here can grade, and grading it as the good outcome is the one answer it must not get.
        """
        result = verdict(
            "oops_reversal",
            prior_day_low={"price": 98.0, "condition": "yesterday's low"},
            gap_below_prior_low={"state": "not observed", "condition": "no gap"},
        )

        self.assertNotEqual(result["setup_state"], "ready")
        self.assertIn("tactic.oops_reversal.gap_below_prior_low", result["missing"])


class AShapeNobodyCanReadIsNotADeclaration(unittest.TestCase):
    """The programmatic channel is a trust boundary for content, not for form.

    A caller who declares what they read is taken at their word -- that is what a declared reading
    is. What they cannot do is hand in something with no reading in it and have the absence
    default to the good outcome. A state key present and null is an answer nobody filled in, and a
    number or a list is not an answer at all.
    """

    def test_a_null_state_leaves_the_condition_owed(self) -> None:
        for key in ("state", "status"):
            with self.subTest(key=key):
                result = verdict(
                    "oops_reversal",
                    prior_day_low={"price": 98.0, "condition": "yesterday's low"},
                    gap_below_prior_low={key: None, "condition": "the stock did not gap below it"},
                )

                self.assertIn("tactic.oops_reversal.gap_below_prior_low", result["missing"])
                self.assertNotEqual(result["setup_state"], "ready")

    def test_a_shape_that_carries_no_reading_leaves_it_owed(self) -> None:
        for answer in (0, 1, 3.5, ["no gap"], ("no gap",)):
            with self.subTest(answer=answer):
                result = verdict(
                    "oops_reversal",
                    prior_day_low={"price": 98.0, "condition": "yesterday's low"},
                    gap_below_prior_low=answer,
                )

                self.assertIn("tactic.oops_reversal.gap_below_prior_low", result["missing"])
                self.assertNotEqual(result["setup_state"], "ready")
