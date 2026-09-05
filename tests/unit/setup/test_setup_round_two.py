"""The second adversarial round's counterexamples, each run against the seam it exploits.

Five of them reached READY. They share a shape: a number was measured from whatever the
caller declared rather than from what the bars show, or a condition's name promised a check
its code did not make. One of them was a regression I introduced while fixing the round
before -- redefining the breakout as "the run price is in now" turned a failed pivot into a
breakout that could be renamed without anyone declaring a new structure.
"""

from __future__ import annotations

import unittest

import pandas as pd

from scripts.minervini.setup import evaluate_setup
from scripts.minervini.setup_evidence import build_setup_evidence
from tests.readings import full as readings
from tests.series import anchor_dates, base_series





def tail(frame: pd.DataFrame, sessions: int, *, close: float, volume: float) -> pd.DataFrame:
    added = pd.DataFrame(
        {"Open": close, "High": close * 1.005, "Low": close * 0.995, "Close": close, "Volume": volume},
        index=pd.bdate_range(start=frame.index[-1] + pd.Timedelta(days=1), periods=sessions),
    )
    return pd.concat([frame, added])


class BreakoutIsTheFirstCrossingTests(unittest.TestCase):
    """Reverting my own regression: a failed pivot is not renamed by a later rally.

    "A pivot failure can reset and recover" says the stock can come back. It does not say a
    later advance becomes the old pivot's breakout without anybody declaring the new
    structure it built in between.
    """

    def _poked_then_recovered(self):
        frame, anchors = base_series(breakout=False)
        chain = anchor_dates(frame, anchors)
        pivot = float(frame.loc[chain[-1], "High"])
        poked = tail(frame, 1, close=pivot * 1.005, volume=700_000.0)
        fell = tail(poked, 6, close=pivot * 0.97, volume=600_000.0)
        return tail(fell, 3, close=pivot * 1.04, volume=2_500_000.0), chain

    def test_the_breakout_is_the_first_close_above_the_pivot(self) -> None:
        frame, chain = self._poked_then_recovered()

        measurements = build_setup_evidence(frame, chain)["measurements"]

        self.assertEqual(measurements["sessions_since_breakout"], 9)
        self.assertFalse(measurements["breakout_held"])

    def test_a_breakout_that_was_given_back_needs_the_structure_declared_again(self) -> None:
        frame, chain = self._poked_then_recovered()

        self.assertNotEqual(evaluate_setup(build_setup_evidence(frame, chain))["setup_state"], "ready")


class PauseLowHeldTests(unittest.TestCase):
    def test_a_close_below_the_declared_pause_low_contradicts_the_declaration(self) -> None:
        """The last low the caller declared cannot be the last low if a lower one came after it."""

        frame, anchors = base_series(breakout=False)
        chain = anchor_dates(frame, anchors)
        pivot = float(frame.loc[chain[-1], "High"])
        collapsed = tail(frame, 3, close=80.0, volume=2_000_000.0)
        leapt = tail(collapsed, 1, close=pivot * 1.04, volume=3_000_000.0)

        result = evaluate_setup(build_setup_evidence(leapt, chain))

        self.assertFalse(result["measurements"]["pause_low_held_to_breakout"])
        self.assertNotEqual(result["setup_state"], "ready")


class PriceSpikeTests(unittest.TestCase):
    def test_the_second_clause_of_the_volume_sentence_is_about_price_spikes(self) -> None:
        """"a few of the price spikes to the upside should be large, dwarfing the contractions".

        Measuring the largest up-day volume against the largest down-day volume answered a
        sentence the source did not write. A base that drifts up on heavy volume and drops in
        violent single sessions satisfies the volume half and fails the one that matters.
        """

        frame, anchors = base_series(depths=(25.0, 10.0, 5.0), declines=(2, 2, 2), rallies=(20, 20, 20))
        change = frame["Close"].diff()
        frame.loc[change > 0, "Volume"] = 2_000_000.0
        frame.loc[change < 0, "Volume"] = 1_000_000.0

        result = evaluate_setup(build_setup_evidence(frame, anchor_dates(frame, anchors)))

        self.assertGreater(result["measurements"]["largest_down_day_return_pct"], result["measurements"]["largest_up_day_return_pct"])
        self.assertEqual(result["setup_state"], "avoid")


class EarlyEntryHasNoTriggerYetTests(unittest.TestCase):
    def test_an_early_entry_cannot_be_ready_on_the_base_evidence_alone(self) -> None:
        """The named early tactics are not measured yet, so nothing has triggered.

        Dropping the pivot from the required list left the early route with no trigger at
        all, which made "taken before the pivot" indistinguishable from "taken for no stated
        reason".
        """

        frame, anchors = base_series(breakout=False)
        price = float(frame["Close"].iloc[-1])

        result = evaluate_setup(
            build_setup_evidence(
                frame,
                anchor_dates(frame, anchors),
                entry_kind="oops_reversal",
                tactic_opt_in=True,
                entry={
                    "confirmation_debt": ["completed pivot breakout"],
                    "minervini_later_pivot": {"price": price * 1.05, "condition": "x"},
                    "invalidation": {"price": price * 0.95, "condition": "x"},
                },
            )
        )

        self.assertEqual(result["setup_state"], "incomplete")
        self.assertIn("tactic.oops_reversal.gap_below_prior_low", result["missing"])


class RightSideJudgementTests(unittest.TestCase):
    """One named form of time compression is measurable; the other is genuinely visual.

    "V-shaped price action or the absence of proper right-side development" -- the absence is
    an absence and needs no ratio. The V is a shape, and the source gives no ratio for it, so
    a right side that did develop pauses is unresolved rather than cleared.
    """

    def test_a_right_side_with_pauses_is_unresolved_until_the_chart_is_read(self) -> None:
        frame, anchors = base_series()

        result = evaluate_setup(build_setup_evidence(frame, anchor_dates(frame, anchors)))

        self.assertEqual(result["setup_state"], "incomplete")
        self.assertIn("setup.time_compression_hazard", result["missing"])

    def test_a_constructive_reading_resolves_it(self) -> None:
        frame, anchors = base_series()

        result = evaluate_setup(
            build_setup_evidence(frame, anchor_dates(frame, anchors), **readings(frame, anchor_dates(frame, anchors)))
        )

        self.assertEqual(result["setup_state"], "ready")

    def test_a_compressed_reading_is_a_known_failure(self) -> None:
        frame, anchors = base_series()

        result = evaluate_setup(
            build_setup_evidence(frame, anchor_dates(frame, anchors), right_side_development="compressed")
        )

        self.assertNotEqual(result["setup_state"], "ready")

    def test_a_constructive_reading_is_refused_when_the_bars_contradict_it(self) -> None:
        """A right side with no pause at all cannot be read as constructive."""

        frame, anchors = base_series(depths=(25.0,), rallies=(3,))

        result = evaluate_setup(
            build_setup_evidence(frame, anchor_dates(frame, anchors), **readings(frame, anchor_dates(frame, anchors)))
        )

        compression = next(item for item in result["signals"] if item["id"] == "setup.time_compression_hazard")
        self.assertEqual(compression["state"], "fail")
        self.assertEqual(result["measurements"]["right_side_contraction_count"], 0)
        self.assertNotEqual(result["setup_state"], "ready")


class SignalOwnershipTests(unittest.TestCase):
    def test_a_signal_with_no_binding_flag_at_all_cannot_answer_a_required_condition(self) -> None:
        frame, anchors = base_series()
        evidence = build_setup_evidence(frame, anchor_dates(frame, anchors), **readings(frame, anchor_dates(frame, anchors)))
        smuggled = {**evidence, "signals": [
            item for item in evidence["signals"] if item["id"] != "setup.demand_supply_volume_asymmetry"
        ] + [{"id": "setup.demand_supply_volume_asymmetry", "state": "pass", "doctrine_id": "practitioners.x"}]}

        result = evaluate_setup(smuggled)

        self.assertNotEqual(result["setup_state"], "ready")
        self.assertIn("setup.demand_supply_volume_asymmetry", result["missing"])

    def test_a_signal_whose_doctrine_id_is_not_the_claim_it_answers_is_refused(self) -> None:
        frame, anchors = base_series()
        evidence = build_setup_evidence(frame, anchor_dates(frame, anchors), **readings(frame, anchor_dates(frame, anchors)))
        smuggled = {**evidence, "signals": [
            item for item in evidence["signals"] if item["id"] != "setup.demand_supply_volume_asymmetry"
        ] + [{"id": "setup.demand_supply_volume_asymmetry", "state": "pass", "binds": True, "doctrine_id": "setup.closing_range_formula"}]}

        self.assertNotEqual(evaluate_setup(smuggled)["setup_state"], "ready")


class ExtendedBreakoutTests(unittest.TestCase):
    def test_an_old_and_extended_breakout_carries_both_distances_and_its_age(self) -> None:
        """The source's chase limit is "a few percentage points" and names no number.

        So this reports rather than rejects: how far above the pivot the entry would be now,
        how far it was on the breakout, and how long ago that was.
        """

        frame, anchors = base_series()
        extended = tail(frame, 40, close=150.0, volume=400_000.0)

        measurements = build_setup_evidence(extended, anchor_dates(frame, anchors))["measurements"]

        self.assertEqual(measurements["sessions_since_breakout"], 40)
        self.assertGreater(measurements["pivot_extension_pct"], 50.0)
        self.assertLess(measurements["pivot_extension_at_breakout_pct"], 5.0)




class ContractMatchesImplementationTests(unittest.TestCase):
    def test_the_published_limitations_describe_the_breakout_rule_the_code_uses(self) -> None:
        """The contract said one thing while the code did another, for one whole round.

        `--help` and `describe` both read these strings, so a stale limitation is not an
        internal note: it is the interface telling a caller something false.
        """

        from scripts.minervini.capabilities import CAPABILITIES

        limitations = " ".join(CAPABILITIES["ticker.setup"].limitations)

        self.assertIn("first completed close above the pivot", limitations)
        self.assertNotIn("run price is currently in", limitations)




class SentenceModalityTests(unittest.TestCase):
    """One sentence, two clauses, two different words: "must" and "should".

    "the volume must be much bigger on up days than on down days, and a few of the price
    spikes to the upside should be large, dwarfing the contractions". Binding both to one
    hard gate made a hair's difference between the largest up day and the largest down day
    reject a candidate on a clause the source hedged.
    """

    def _spikes_reversed(self):
        """Every other condition satisfied, so the state comes from this clause alone."""

        frame, anchors = base_series(depths=(25.0, 10.0, 5.0), declines=(2, 2, 2), rallies=(20, 20, 20))
        change = frame["Close"].diff()
        frame.loc[change > 0, "Volume"] = 2_000_000.0
        frame.loc[change < 0, "Volume"] = 1_000_000.0
        # Volume dries into the pivot area so the pivot-volume gate is satisfied too.
        final_high = frame.index.get_loc(anchor_dates(frame, anchors)[-3])
        frame.iloc[final_high:-1, frame.columns.get_loc("Volume")] = 200_000.0
        frame.iloc[-1, frame.columns.get_loc("Volume")] = 6_000_000.0
        return build_setup_evidence(frame, anchor_dates(frame, anchors), **readings(frame, anchor_dates(frame, anchors)))

    def test_the_should_clause_reports_and_never_blocks(self) -> None:
        result = evaluate_setup(self._spikes_reversed())

        self.assertNotIn("setup.upside_spikes_dwarf_contractions", result["failed"])
        self.assertNotIn("setup.upside_spikes_dwarf_contractions", result["unsatisfied"])
        self.assertNotIn("setup.upside_spikes_dwarf_contractions", result["required_evidence"])

    def test_reversing_the_volume_totals_is_what_rejects(self) -> None:
        frame, anchors = base_series(volume_profile="distribution")

        result = evaluate_setup(
            build_setup_evidence(frame, anchor_dates(frame, anchors), **readings(frame, anchor_dates(frame, anchors)))
        )

        self.assertEqual(result["setup_state"], "avoid")
        self.assertEqual(result["failed"], ["setup.demand_supply_volume_asymmetry"])


if __name__ == "__main__":
    unittest.main()
