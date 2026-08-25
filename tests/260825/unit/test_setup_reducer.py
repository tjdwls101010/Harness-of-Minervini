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
    readings = {"right_side_development": "constructive", "chain_completeness": "complete", "entry_proximity": "at_pivot"}
    readings.update({key: kwargs.pop(key) for key in list(readings) if key in kwargs})
    frame, anchors = base_series(**kwargs)
    return build_setup_evidence(
        frame,
        chain if chain is not None else anchor_dates(frame, anchors),
        entry_kind=entry_kind,
        **readings,
    )


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

        result = evaluate_setup(build_setup_evidence(frame, dates, entry_kind="completed_pivot", right_side_development="constructive", chain_completeness="complete", entry_proximity="at_pivot"))

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

        result = evaluate_setup(build_setup_evidence(frame, [], entry_kind="completed_pivot", right_side_development="constructive", chain_completeness="complete", entry_proximity="at_pivot"))

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




TL_EARLY_DECLARATION = {
    "confirmation_debt": ["completed Minervini pivot breakout"],
    "minervini_later_pivot": {"price": 104.5, "condition": "completed close above 104.5"},
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
            right_side_development="constructive",
            chain_completeness="complete",
            entry_proximity="at_pivot",
            **overrides,
        )

    def test_a_declared_early_entry_keeps_its_debt_while_waiting_for_a_trigger_to_be_measured(self) -> None:
        result = evaluate_setup(self._evidence(tactic_opt_in=True))

        self.assertEqual(result["setup_state"], "incomplete")
        self.assertIn("early_trigger", result["missing"])
        self.assertEqual(result["entry"]["tactic"], "[TL-EARLY]")
        self.assertEqual(result["entry"]["confirmation_debt"], ["completed Minervini pivot breakout"])
        self.assertEqual(result["entry"]["minervini_later_pivot"]["price"], 104.5)
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
            right_side_development="constructive", chain_completeness="complete", entry_proximity="at_pivot",
        )

        self.assertEqual(evaluate_setup(evidence)["setup_state"], "avoid")


class UnusableHistoryTests(unittest.TestCase):
    def test_bars_that_are_not_usable_price_history_leave_every_measurement_unavailable(self) -> None:
        frame, anchors = base_series()
        chain = anchor_dates(frame, anchors)

        result = evaluate_setup(build_setup_evidence(frame.drop(columns=["Volume"]), chain, right_side_development="constructive", chain_completeness="complete", entry_proximity="at_pivot"))

        self.assertEqual(result["setup_state"], "incomplete")
        self.assertIn("base_structure", result["missing"])

    def test_a_history_that_is_not_a_frame_at_all_is_incomplete_rather_than_an_error(self) -> None:
        result = evaluate_setup(build_setup_evidence(None, ["2026-03-19", "2026-04-06", "2026-04-20"], right_side_development="constructive", chain_completeness="complete", entry_proximity="at_pivot"))

        self.assertEqual(result["setup_state"], "incomplete")


class GoldenDiscriminationTests(unittest.TestCase):
    """A pattern that measures like a VCP everywhere its numbers are pretty.

    An adversarial review of this design produced it: three contractions narrowing left to
    right, a cleared pivot, and a right side that recovered in three sessions after a decline
    that took sixty. What refuses it is not the shape -- the source describes V-shaped action
    as hazardous and supplies no ratio for it -- but the volume, which arrives almost entirely
    on the down days. The rejection comes from the one rule the source states with "must",
    and the tests below say exactly which condition did the work.
    """

    def _counterexample(self):
        frame, anchors = base_series(
            depths=(30.0, 5.0, 2.5),
            declines=(60, 6, 6),
            rallies=(3, 6, 6),
            volume_profile="distribution",
        )
        return build_setup_evidence(frame, anchor_dates(frame, anchors))

    def test_the_flattering_measurements_really_are_flattering(self) -> None:
        evidence = self._counterexample()
        numbers = evidence["measurements"]

        self.assertEqual(numbers["contraction_count"], 3)
        self.assertTrue(numbers["contractions_contract"])
        self.assertTrue(numbers["pivot_cleared"])
        self.assertEqual([round(ratio, 4) for ratio in numbers["successive_depth_ratios"]], [0.1667, 0.5])

    def test_and_the_setup_is_still_refused(self) -> None:
        result = evaluate_setup(self._counterexample())

        self.assertEqual(result["setup_state"], "avoid")
        self.assertEqual(result["failed"], ["setup.demand_supply_volume_asymmetry"])

    def test_the_compressed_right_side_travels_with_the_verdict_as_a_measured_ratio(self) -> None:
        """This right side did develop two pauses, so the absence form does not apply to it.

        What remains is the V-shape, for which the source supplies no ratio at all. The
        measured left-to-right duration ratio is carried so a reader sees it; nothing here
        turns it into a rejection the source never wrote.
        """

        result = evaluate_setup(self._counterexample())
        compression = signal(result, "setup.time_compression_hazard")

        self.assertEqual(compression["state"], "needs_chart")
        self.assertLess(compression["measured"], 0.5)


class SingleContractionTests(unittest.TestCase):
    def test_one_contraction_cannot_satisfy_the_rule_that_contractions_narrow(self) -> None:  # noqa: D401
        """With nothing to compare, "smaller from left to right" is unobserved, not satisfied.

        A caller who declares only high, low, high gets a sequence with no successive pair
        in it. Reading that as the rule holding would let the shortest possible declaration
        clear the condition the longest one has to earn.
        """

        result = evaluate_setup(evidence_for(depths=(25.0,)))

        self.assertEqual(signal(result, "setup.contractions_must_contract")["state"], "unavailable")
        self.assertEqual(result["setup_state"], "incomplete")
        self.assertIn("setup.contractions_must_contract", result["missing"])


class ChainGamingTests(unittest.TestCase):
    """What a validated chain still cannot stop, reported so the reader sees it.

    Every anchor is checked against the span its neighbours bound, so a misread swing is
    refused. Starting the chain late is not a misread swing -- each anchor in the shortened
    chain is genuinely its span's extreme. What changes is what sits above the entry, and
    that is measurable and named by the source.
    """

    def test_a_chain_started_past_an_older_high_still_reports_the_supply_above_the_entry(self) -> None:
        frame, anchors = base_series()
        late = anchor_dates(frame, anchors)[2:]

        result = evaluate_setup(build_setup_evidence(frame, late, right_side_development="constructive", chain_completeness="complete", entry_proximity="at_pivot"))

        supply = signal(result, "setup.overhead_supply_mechanism")
        self.assertEqual(supply["state"], "reported")
        self.assertGreater(supply["measured"], 0)

    def test_the_distance_the_entry_sits_above_the_pivot_travels_with_the_verdict(self) -> None:
        result = evaluate_setup(evidence_for())

        chase = signal(result, "setup.chase_limit_above_pivot")
        self.assertEqual(chase["state"], "pass")
        self.assertEqual(
            round(chase["measured"]["pivot_extension_pct"], 2),
            round(result["measurements"]["pivot_extension_pct"], 2),
        )


if __name__ == "__main__":
    unittest.main()
