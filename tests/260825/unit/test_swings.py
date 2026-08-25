"""A deterministic segmentation, so the caller's chart reading has something to check against.

The engine cannot tell an honest swing chain from a flattering one by measuring it -- every
anchor in a chain that skipped a contraction still sits at its own span's extreme. What it can
do is produce its own segmentation and compare.

Every rule here is the harness's, not the source's: the source calls swing reading chart work
and never names a retracement. So the rules are written down rather than left to whatever the
loop happened to do -- when a bar both extends a move and reverses it, which of two equal
extremes wins, and what happens when a neighbouring parameter value would have seen something
different.
"""

from __future__ import annotations

import unittest

import pandas as pd

from scripts.minervini.swings import base_chain, canonical_chain, segment
from tests.series import anchor_dates, base_series, bases_under_an_older_high_series, two_bases_series


class RecoversTheSourcesOwnExampleTests(unittest.TestCase):
    def test_the_turning_points_of_a_twenty_five_ten_five_base_are_found(self) -> None:
        frame, anchors = base_series(depths=(25.0, 10.0, 5.0))

        found = segment(frame, retracement_pct=1.0)

        self.assertEqual([item["date"] for item in base_chain(found["anchors"])], anchor_dates(frame, anchors))

    def test_the_breakout_underway_is_kept_out_of_the_base(self) -> None:
        """A move still in progress is unconfirmed, and a breakout is exactly that move.

        Confirming an extreme means watching price fall away from it. Folding the live leg into
        the chain would put the pivot on the breakout bar, making the level the entry is
        measured against the entry's own session.
        """

        frame, anchors = base_series()

        found = segment(frame, retracement_pct=1.0)

        self.assertEqual(base_chain(found["anchors"])[-1]["date"], anchor_dates(frame, anchors)[-1])
        self.assertEqual(found["live_leg"]["date"], frame.index[-1].date().isoformat())


class DeterministicRulesTests(unittest.TestCase):
    def test_an_extreme_is_never_confirmed_by_its_own_bar(self) -> None:
        """A daily bar does not say whether its high came before its low.

        A session that both prints a new high and falls far enough to reverse could have done
        either first, so confirming inside it would be a guess about intraday order dressed as
        a measurement.
        """

        index = pd.bdate_range(end="2026-08-21", periods=4)
        frame = pd.DataFrame(
            {"Open": [10.0, 10.0, 10.0, 9.0], "High": [10.0, 20.0, 12.0, 9.5],
             "Low": [9.9, 9.0, 9.5, 8.5], "Close": [10.0, 9.5, 10.0, 9.0], "Volume": [1e6] * 4},
            index=index,
        )

        found = segment(frame, retracement_pct=10.0)

        self.assertIn(index[1].date().isoformat(), found["ambiguous_sessions"])

    def test_the_first_of_two_equal_extremes_is_the_one_named(self) -> None:
        index = pd.bdate_range(end="2026-08-21", periods=6)
        frame = pd.DataFrame(
            {"Open": [10.0] * 6, "High": [10.0, 12.0, 12.0, 11.0, 10.0, 9.0],
             "Low": [9.5, 11.0, 11.0, 10.5, 9.5, 8.5], "Close": [10.0, 12.0, 12.0, 11.0, 10.0, 9.0],
             "Volume": [1e6] * 6},
            index=index,
        )

        found = segment(frame, retracement_pct=10.0)

        self.assertEqual(found["anchors"][0]["date"], index[1].date().isoformat())


class CanonicalChainTests(unittest.TestCase):
    """What `ticker.setup` compares a declared chain against, chosen by the harness alone.

    If the caller could pick the parameter, the start date, or which tail of the chain counted,
    the segmentation gaming this exists to stop would come straight back in through the choice.
    """

    def test_the_canonical_chain_is_the_base_the_last_confirmed_high_tops(self) -> None:
        frame, anchors = base_series()

        chain = canonical_chain(frame)

        self.assertEqual([item["date"] for item in chain["anchors"]], anchor_dates(frame, anchors))
        self.assertEqual(chain["state"], "resolved")

    def test_a_segmentation_neighbouring_values_disagree_with_vouches_for_nothing(self) -> None:
        """Knowing the chain moves with the parameter and passing one of them anyway is the
        same failure as issuing READY over a gap the engine knows about."""

        frame, _ = base_series(depths=(25.0, 10.0, 1.2))

        chain = canonical_chain(frame)

        self.assertEqual(chain["state"], "unstable")
        self.assertEqual(chain["anchors"], [])
        self.assertTrue(chain["sensitivity"])

    def test_the_bars_it_was_cut_from_travel_with_the_answer(self) -> None:
        """Which of two things moved, when a declaration that used to match stops matching.

        The setup capability re-runs the detector and refuses a chain it did not produce, so a
        mismatch is loud. What it does not say is whether the rules changed or the data did.
        Same fingerprint and a mismatch means the rules moved; a different fingerprint means
        the provider handed back different bars.
        """

        frame, _ = base_series()

        chain = canonical_chain(frame)
        moved = canonical_chain(frame.assign(Close=frame["Close"] * 1.01))

        self.assertEqual(len(chain["bars_fingerprint"]), 64)
        self.assertNotEqual(chain["bars_fingerprint"], moved["bars_fingerprint"])

    def test_a_neighbour_that_finds_an_extra_contraction_is_a_disagreement(self) -> None:
        """The engine cannot both refuse a finer chain and vouch for one.

        Downstream, a declared chain that adds anchors between the same endpoints is refused by
        name, because an unfavourable contraction re-cut into smaller ones disappears from the
        sequence without an endpoint moving. Accepting exactly that from a neighbouring
        parameter value, on the grounds that every primary anchor is still present, waves
        through the case the refusal exists for.
        """

        prices = [80, 90, 100, 95, 90, 90.675, 90, 80, 75, 85, 99, 95, 89, 94, 98, 95, 93, 96, 97, 95]
        index = pd.bdate_range("2026-01-02", periods=len(prices))
        frame = pd.DataFrame(
            {"Open": prices, "High": prices, "Low": prices, "Close": prices, "Volume": [1e6] * len(prices)},
            index=index,
        )

        finer = base_chain(segment(frame, retracement_pct=0.5)["anchors"], frame["Close"], frame["Low"])
        primary = base_chain(segment(frame, retracement_pct=1.0)["anchors"], frame["Close"], frame["Low"])
        self.assertGreater(len(finer), len(primary))

        chain = canonical_chain(frame)

        self.assertEqual(chain["state"], "unstable")
        self.assertTrue(chain["sensitivity"])

    def test_the_parameters_it_used_travel_with_the_answer(self) -> None:
        frame, _ = base_series()

        chain = canonical_chain(frame)

        self.assertIn("retracement_pct", chain["parameters"])
        self.assertIn("sensitivity_offsets_pct", chain["parameters"])
        self.assertEqual(chain["sessions"], len(frame))


class OneBaseAtATimeTests(unittest.TestCase):
    """Which structure the chain describes when the history holds more than one."""

    def test_the_base_proposed_is_the_one_price_is_in_now_not_one_it_left(self) -> None:
        """A base the stock is thirty percent above is a memory, not a proposal.

        Preferring a high price had closed above and held put the pivot on the older base:
        every high of the base the stock had already left qualifies by that test, and the base
        it is actually building does not, because price has not cleared it yet.
        """

        frame, left_behind, current = two_bases_series()

        chain = canonical_chain(frame)

        self.assertEqual([item["date"] for item in chain["anchors"]], current)
        self.assertNotEqual([item["date"] for item in chain["anchors"]], left_behind)

    def test_the_older_structure_is_not_spliced_onto_the_current_one(self) -> None:
        """Two consolidations with a breakout between them are two bases, not one deep one."""

        frame, left_behind, _ = two_bases_series()

        chain = canonical_chain(frame)

        self.assertFalse(set(left_behind) & {item["date"] for item in chain["anchors"]})

    def test_a_breakout_that_stayed_under_an_older_peak_still_ends_the_base_it_left(self) -> None:
        """The rim rule alone only works when the newer rim happens to top everything before it.

        A deep correction, a partial recovery, and a breakout out of that recovery leaves the old
        peak still towering over the base being built. Taking the highest high before the pivot
        then reaches back across a completed structure and reports a forty percent correction for
        an eleven percent base.
        """

        frame, left_behind, current = bases_under_an_older_high_series()

        chain = canonical_chain(frame)

        self.assertEqual([item["date"] for item in chain["anchors"]], current)
        self.assertFalse(set(left_behind) & {item["date"] for item in chain["anchors"]})

    def test_a_breakout_bar_that_opened_under_the_level_still_left_it_behind(self) -> None:
        """Holding starts the session after the one that cleared it.

        A breakout opens under the level and travels through it, so reading the crossing bar's
        own low as a failure to hold made every realistic breakout fail the test -- and, because
        the neighbouring parameters disagreed about it, took the whole segmentation to unstable.
        """

        frame, left_behind, current = bases_under_an_older_high_series(realistic_breakout=True)

        chain = canonical_chain(frame)

        self.assertEqual(chain["state"], "resolved")
        self.assertEqual([item["date"] for item in chain["anchors"]], current)

    def test_a_poke_above_the_pivot_that_gave_it_all_back_did_not_end_the_base(self) -> None:
        """Clearing a level and holding it is leaving; clearing it and falling back is failing.

        Trimming on the close alone would cut a failed breakout out of its own base and hand
        back the rebuild as a fresh structure, which is the opposite of what the source says a
        pivot failure is.
        """

        frame, first, _ = two_bases_series(second_high=99.7)

        chain = canonical_chain(frame)

        self.assertTrue(set(first) <= {item["date"] for item in chain["anchors"]})


class UnusableHistoryTests(unittest.TestCase):
    def test_a_history_with_no_completed_bars_segments_into_nothing(self) -> None:
        frame, _ = base_series()

        self.assertEqual(segment(frame.iloc[:0], retracement_pct=1.0)["anchors"], [])

    def test_a_retracement_that_is_not_a_positive_percentage_is_refused(self) -> None:
        frame, _ = base_series()

        for value in (0.0, -1.0, 100.0):
            with self.subTest(retracement=value):
                with self.assertRaises(ValueError):
                    segment(frame, retracement_pct=value)


if __name__ == "__main__":
    unittest.main()
