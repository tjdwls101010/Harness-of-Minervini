"""READY is a set of satisfied conditions, not the absence of failures.

The old reducer produced `ready` whenever nothing was marked failed or missing, which is
how twenty-two drifting bars and two `pass` flags reached the top verdict. Each entry
route now declares the evidence it must positively have, and the state comes from that
list being satisfied. Nothing can back into READY by having no objections.
"""

from __future__ import annotations

import unittest

import pandas as pd

from scripts.minervini.setup import evaluate_setup
from scripts.minervini.setup_evidence import build_setup_evidence
from tests.series import anchor_dates, base_series


def evidence_for(**kwargs):
    chain = kwargs.pop("chain", None)
    entry_kind = kwargs.pop("entry_kind", "completed_pivot")
    frame, anchors = base_series(**kwargs)
    return build_setup_evidence(frame, chain if chain is not None else anchor_dates(frame, anchors), entry_kind=entry_kind)


def state_of(**kwargs) -> str:
    return evaluate_setup(evidence_for(**kwargs))["setup_state"]


def signal(result, identifier):
    return next(item for item in result["signals"] if item["id"] == identifier)


class TextbookSetupTests(unittest.TestCase):
    def test_a_measured_vcp_that_cleared_its_pivot_is_ready(self) -> None:
        self.assertEqual(state_of(depths=(25.0, 10.0, 5.0)), "ready")

    def test_the_verdict_carries_the_measurements_it_rests_on(self) -> None:
        result = evaluate_setup(evidence_for())

        self.assertEqual(result["measurements"]["contraction_count"], 3)
        self.assertEqual([round(value, 4) for value in result["measurements"]["contraction_depths_pct"]], [25.0, 10.0, 5.0])


class KnownFailureTests(unittest.TestCase):
    def test_down_day_volume_outweighing_up_day_volume_is_avoid(self) -> None:
        """Contractions can contract while a stock is being distributed; this is that case."""

        result = evaluate_setup(evidence_for(volume_profile="distribution"))

        self.assertEqual(result["setup_state"], "avoid")
        self.assertIn("setup.demand_supply_volume_asymmetry", result["failed"])

    def test_a_widening_sequence_is_not_ready_and_says_which_condition_it_missed(self) -> None:
        result = evaluate_setup(evidence_for(depths=(5.0, 10.0, 25.0)))

        self.assertNotEqual(result["setup_state"], "ready")
        self.assertEqual(signal(result, "setup.contractions_must_contract")["state"], "fail")

    def test_volume_that_never_contracted_into_the_pivot_is_avoid(self) -> None:
        result = evaluate_setup(evidence_for(volume_profile="rising"))

        self.assertEqual(result["setup_state"], "avoid")
        self.assertIn("setup.pivot_volume_contraction", result["failed"])


class TimingTests(unittest.TestCase):
    def test_a_base_that_has_not_cleared_its_pivot_waits(self) -> None:
        self.assertEqual(state_of(breakout=False), "wait")


class MissingEvidenceTests(unittest.TestCase):
    def test_a_contradicted_chain_is_incomplete_and_surfaces_the_offending_date(self) -> None:
        frame, anchors = base_series()
        dates = anchor_dates(frame, anchors)
        dates[1] = frame.index[anchors[1].position - 1].date().isoformat()

        result = evaluate_setup(build_setup_evidence(frame, dates, entry_kind="completed_pivot"))

        self.assertEqual(result["setup_state"], "incomplete")
        self.assertTrue(any(dates[1] in problem for problem in result["structure"]["problems"]))

    def test_no_declared_structure_is_incomplete_rather_than_an_unqualified_pass(self) -> None:
        result = evaluate_setup(evidence_for(chain=[]))

        self.assertEqual(result["setup_state"], "incomplete")
        self.assertIn("base_structure", result["missing"])

    def test_twenty_two_drifting_bars_cannot_reach_ready(self) -> None:
        """The defect this rewrite exists for: no base, no contraction, and a top verdict."""

        index = pd.bdate_range(end="2026-08-17", periods=22)
        frame = pd.DataFrame(
            {
                "Open": [98.0] * 22,
                "High": [100.0] * 21 + [102.0],
                "Low": [96.0] * 22,
                "Close": [98.0] * 21 + [101.0],
                "Volume": [1_000_000.0] * 21 + [1_600_000.0],
            },
            index=index,
        )

        result = evaluate_setup(build_setup_evidence(frame, [], entry_kind="completed_pivot"))

        self.assertEqual(result["setup_state"], "incomplete")


class ContrastIsolationTests(unittest.TestCase):
    def test_contrast_evidence_is_carried_but_never_reaches_the_verdict(self) -> None:
        """Another practitioner's standard is worth printing and must not move our state."""

        evidence = evidence_for()
        baseline = evaluate_setup(evidence)

        for state in ("contrast_pass", "contrast_fail", "unavailable"):
            with self.subTest(state=state):
                polluted = {**evidence, "contrast": [{"id": "practitioners.x", "state": state, "binds": False}]}
                result = evaluate_setup(polluted)
                self.assertEqual(result["setup_state"], baseline["setup_state"])
                self.assertEqual(result["failed"], baseline["failed"])
                self.assertEqual(result["missing"], baseline["missing"])

    def test_no_binding_signal_carries_a_contrast_state_word(self) -> None:
        result = evaluate_setup(evidence_for())

        for item in result["signals"]:
            with self.subTest(signal=item["id"]):
                self.assertNotIn(item["state"], {"contrast_pass", "contrast_fail"})

    def test_practitioner_breakout_standards_are_reported_side_by_side_as_contrast(self) -> None:
        evidence = evidence_for()

        attributed = {item.get("attributed_to") for item in evidence["contrast"]}

        self.assertTrue({"Ryan", "Zanger"}.issubset(attributed), attributed)


if __name__ == "__main__":
    unittest.main()


TL_EARLY_DECLARATION = {
    "confirmation_debt": ["completed Minervini pivot breakout"],
    "minervini_later_pivot": {"price": 100.2, "condition": "completed close above 100.2"},
    "invalidation": {"price": 96.0, "condition": "completed close below 96.0"},
}


class EarlyEntryTests(unittest.TestCase):
    """The advanced route still owes its confirmation, and now also owes the supply gates.

    Those gates are about the base, not about when the trade is taken, so taking the entry
    early does not excuse them. What the early route drops is the completed trigger, which
    is precisely the confirmation it is promising to pay later.
    """

    def _evidence(self, **overrides):
        frame, anchors = base_series()
        declaration = {**TL_EARLY_DECLARATION, **overrides.pop("entry", {})}
        return build_setup_evidence(
            frame,
            anchor_dates(frame, anchors),
            entry_kind="tl_early",
            entry=declaration,
            **overrides,
        )

    def test_a_declared_early_entry_with_the_measured_base_behind_it_is_ready(self) -> None:
        result = evaluate_setup(self._evidence(tactic_opt_in=True))

        self.assertEqual(result["setup_state"], "ready")
        self.assertEqual(result["entry"]["tactic"], "[TL-EARLY]")
        self.assertEqual(result["entry"]["confirmation_debt"], ["completed Minervini pivot breakout"])
        self.assertEqual(result["entry"]["minervini_later_pivot"]["price"], 100.2)
        self.assertEqual(result["entry"]["invalidation"]["price"], 96.0)

    def test_without_the_caller_opting_in_the_tactic_stays_unresolved(self) -> None:
        result = evaluate_setup(self._evidence())

        self.assertEqual(result["setup_state"], "incomplete")
        self.assertIn("tl_early_opt_in", result["missing"])

    def test_an_early_entry_with_no_precise_invalidation_is_missing_evidence(self) -> None:
        result = evaluate_setup(self._evidence(tactic_opt_in=True, entry={"invalidation": None}))

        self.assertEqual(result["setup_state"], "incomplete")
        self.assertIn("precise_invalidation", result["missing"])

    def test_an_early_entry_over_a_distributing_base_is_still_avoid(self) -> None:
        frame, anchors = base_series(volume_profile="distribution")
        evidence = build_setup_evidence(
            frame,
            anchor_dates(frame, anchors),
            entry_kind="tl_early",
            entry=TL_EARLY_DECLARATION,
            tactic_opt_in=True,
        )

        self.assertEqual(evaluate_setup(evidence)["setup_state"], "avoid")


class UnusableHistoryTests(unittest.TestCase):
    def test_bars_that_are_not_usable_price_history_leave_every_measurement_unavailable(self) -> None:
        frame, anchors = base_series()
        chain = anchor_dates(frame, anchors)

        result = evaluate_setup(build_setup_evidence(frame.drop(columns=["Volume"]), chain))

        self.assertEqual(result["setup_state"], "incomplete")
        self.assertIn("base_structure", result["missing"])

    def test_a_history_that_is_not_a_frame_at_all_is_incomplete_rather_than_an_error(self) -> None:
        result = evaluate_setup(build_setup_evidence(None, ["2026-03-19", "2026-04-06", "2026-04-20"]))

        self.assertEqual(result["setup_state"], "incomplete")
