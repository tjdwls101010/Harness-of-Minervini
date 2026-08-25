"""Round three: the boundary between what the bars can check and what a person must.

The sharpest finding was not a wrong number. It was that the engine knew it could not
verify a chain's completeness and issued READY anyway. Declaring a gap and then stepping
over it is worse than not knowing about it, because the verdict looks earned.

So completeness and entry proximity join the right side as declared readings: named inputs
whose absence keeps the setup incomplete, and which the measurements refuse when they can
see the reading is wrong.
"""

from __future__ import annotations

import unittest

import pandas as pd

from scripts.minervini.setup import evaluate_setup
from scripts.minervini.setup_evidence import build_setup_evidence
from tests.readings import full as readings
from tests.series import anchor_dates, base_series





def signal(result, identifier):
    return next(item for item in result["signals"] if item["id"] == identifier)


class DeclaredReadingsTests(unittest.TestCase):
    def test_a_chain_nobody_vouched_for_is_incomplete_rather_than_ready(self) -> None:
        """The engine cannot tell a complete chain from a flattering one, and says so."""

        frame, anchors = base_series()

        result = evaluate_setup(
            build_setup_evidence(frame, anchor_dates(frame, anchors), right_side_development="constructive")
        )

        self.assertEqual(result["setup_state"], "incomplete")
        self.assertIn("setup.declared_chain_completeness", result["missing"])

    def test_an_unjudged_entry_distance_is_incomplete_rather_than_ready(self) -> None:
        frame, anchors = base_series()

        result = evaluate_setup(
            build_setup_evidence(
                frame,
                anchor_dates(frame, anchors),
                right_side_development="constructive",
                chain_completeness="complete",
            )
        )

        self.assertEqual(result["setup_state"], "incomplete")
        self.assertIn("setup.chase_limit_above_pivot", result["missing"])

    def test_all_three_readings_together_reach_ready(self) -> None:
        frame, anchors = base_series()

        self.assertEqual(
            evaluate_setup(build_setup_evidence(frame, anchor_dates(frame, anchors), **readings(frame, anchor_dates(frame, anchors))))["setup_state"],
            "ready",
        )

    def test_an_extended_entry_read_as_chased_stops_short_of_ready(self) -> None:
        """The source gives no number for "a few percentage points", so the reader judges.

        The harness does not invent the boundary and does not pretend the distance is fine
        either: it requires the call and prints the distance, the breakout's own distance,
        and how long ago the breakout was, next to it.
        """

        frame, anchors = base_series()
        tail = pd.DataFrame(
            {"Open": 150.0, "High": 150.5, "Low": 149.5, "Close": 150.0, "Volume": 400_000.0},
            index=pd.bdate_range(start=frame.index[-1] + pd.Timedelta(days=1), periods=40),
        )
        extended = pd.concat([frame, tail])
        chain = anchor_dates(frame, anchors)

        result = evaluate_setup(build_setup_evidence(extended, chain, **readings(frame, chain, entry_proximity="chased")))

        self.assertEqual(result["setup_state"], "wait")
        self.assertIn("setup.chase_limit_above_pivot", result["unsatisfied"])
        reported = signal(result, "setup.chase_limit_above_pivot")["measured"]
        self.assertGreater(reported["latest_close_extension_above_pivot_pct"], 50.0)
        self.assertEqual(reported["sessions_since_breakout"], 40)


class HiddenHighTests(unittest.TestCase):
    def test_a_higher_high_between_the_pivot_and_the_breakout_contradicts_the_pivot(self) -> None:
        """The last anchor's right neighbour is itself, so nothing after it was ever checked.

        This does not need a canonical segmentation: the declared pivot either was the
        highest bar before the breakout or it was not.
        """

        frame, anchors = base_series(breakout=False)
        chain = anchor_dates(frame, anchors)
        hidden = pd.DataFrame(
            {"Open": [98.0, 103.0], "High": [107.35, 104.37], "Low": [97.0, 98.0], "Close": [98.0, 103.38], "Volume": [500_000.0, 3_000_000.0]},
            index=pd.bdate_range(start=frame.index[-1] + pd.Timedelta(days=1), periods=2),
        )

        result = evaluate_setup(build_setup_evidence(pd.concat([frame, hidden]), chain, **readings(frame, chain)))

        self.assertFalse(result["measurements"]["pivot_is_highest_to_breakout"])
        self.assertNotEqual(result["setup_state"], "ready")
        self.assertIn("setup.structural_pivot_and_trigger", result["unsatisfied"])


class TimezoneTests(unittest.TestCase):
    def test_a_timezone_aware_frame_reads_the_same_as_a_naive_one(self) -> None:
        """The production provider returns the exchange's own index; the unit fixtures do not."""

        frame, anchors = base_series()
        chain = anchor_dates(frame, anchors)
        aware = frame.copy()
        aware.index = aware.index.tz_localize("America/New_York")

        naive_result = evaluate_setup(build_setup_evidence(frame, chain, **readings(frame, chain)))
        aware_result = evaluate_setup(build_setup_evidence(aware, chain, **readings(frame, chain)))

        self.assertEqual(aware_result["setup_state"], naive_result["setup_state"])


class GiveBackIsNotPermanentTests(unittest.TestCase):
    def test_a_breakout_that_gave_the_pivot_back_waits_rather_than_failing_forever(self) -> None:
        """The claim says a pivot failure can reset; the code said it disqualified the base."""

        frame, anchors = base_series()
        chain = anchor_dates(frame, anchors)
        pivot = float(frame.loc[chain[-1], "High"])
        given_back = pd.DataFrame(
            {"Open": pivot * 0.97, "High": pivot * 0.98, "Low": pivot * 0.96, "Close": pivot * 0.97, "Volume": 600_000.0},
            index=pd.bdate_range(start=frame.index[-1] + pd.Timedelta(days=1), periods=4),
        )

        result = evaluate_setup(build_setup_evidence(pd.concat([frame, given_back]), chain, **readings(frame, chain)))

        self.assertEqual(signal(result, "setup.structural_pivot_and_trigger")["state"], "not_triggered")
        self.assertNotIn("setup.structural_pivot_and_trigger", result["failed"])
        self.assertNotEqual(result["setup_state"], "ready")

    def test_a_close_exactly_at_the_pivot_is_not_a_close_below_it(self) -> None:
        frame, anchors = base_series()
        chain = anchor_dates(frame, anchors)
        pivot = float(frame.loc[chain[-1], "High"])
        flat = pd.DataFrame(
            {"Open": pivot, "High": pivot * 1.001, "Low": pivot * 0.999, "Close": pivot, "Volume": 600_000.0},
            index=pd.bdate_range(start=frame.index[-1] + pd.Timedelta(days=1), periods=2),
        )

        measurements = build_setup_evidence(pd.concat([frame, flat]), chain, **readings(frame, chain))["measurements"]

        self.assertTrue(measurements["breakout_held"])


class SpikePluralityTests(unittest.TestCase):
    def test_one_large_advance_does_not_answer_a_clause_about_a_few_of_them(self) -> None:
        """"a few of the price spikes ... dwarfing the contractions" is plural and comparative.

        A single maximum beating a single maximum is neither, so the clause reports what it
        counted instead of passing on an answer it cannot give.
        """

        frame, anchors = base_series(depths=(25.0, 10.0, 5.0), declines=(20, 20, 20), rallies=(1, 20, 20))

        evidence = build_setup_evidence(frame, anchor_dates(frame, anchors), **readings(frame, anchor_dates(frame, anchors)))

        spikes = next(item for item in evidence["signals"] if item["id"] == "setup.upside_spikes_dwarf_contractions")
        self.assertEqual(spikes["state"], "reported")
        self.assertEqual(spikes["measured"]["up_days_exceeding_largest_decline"], 1)

    def test_the_clause_never_stands_between_a_setup_and_ready(self) -> None:
        frame, anchors = base_series(depths=(25.0, 10.0, 5.0), declines=(20, 20, 20), rallies=(1, 20, 20))

        result = evaluate_setup(build_setup_evidence(frame, anchor_dates(frame, anchors), **readings(frame, anchor_dates(frame, anchors))))

        self.assertNotIn("setup.upside_spikes_dwarf_contractions", result["required_evidence"])


if __name__ == "__main__":
    unittest.main()
