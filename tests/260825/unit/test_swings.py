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

from scripts.minervini.setup_structure import bars_fingerprint
from scripts.minervini.swings import _volume_expanded, base_chain, canonical_chain, segment
from tests.series import anchor_dates, base_series, bases_under_an_older_high_series, from_legs, turn_between_neighbours_series, two_bases_series, unstable_series


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
            {"Open": [10.0, 11.5, 11.5, 10.8, 9.8, 8.8], "High": [10.0, 12.0, 12.0, 11.0, 10.0, 9.0],
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

        frame, _ = unstable_series()

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

        frame = turn_between_neighbours_series()

        chain = canonical_chain(frame)

        # The scale is derived from the bars, so the neighbours are read back rather than named.
        parameters = chain["parameters"]
        primary = base_chain(segment(frame, retracement_pct=parameters["retracement_pct"])["anchors"])
        finer = base_chain(
            segment(
                frame,
                retracement_pct=(parameters["retracement_range_multiple"] + min(parameters["sensitivity_offsets"]))
                * parameters["typical_daily_range_pct"],
            )["anchors"]
        )

        self.assertGreater(len(finer), len(primary))
        self.assertEqual(chain["state"], "unstable")
        self.assertTrue(chain["sensitivity"])

    def test_the_parameters_it_used_travel_with_the_answer(self) -> None:
        frame, _ = base_series()

        chain = canonical_chain(frame)

        self.assertIn("retracement_range_multiple", chain["parameters"])
        self.assertIn("sensitivity_offsets", chain["parameters"])
        # The multiple is the rule; the percentage it came out at is a fact about this stock.
        self.assertGreater(chain["parameters"]["typical_daily_range_pct"], 0)
        self.assertAlmostEqual(
            chain["parameters"]["retracement_pct"],
            chain["parameters"]["retracement_range_multiple"] * chain["parameters"]["typical_daily_range_pct"],
            places=3,
        )
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

    def test_a_history_under_one_peak_is_described_whole_not_cut_to_the_flattering_half(self) -> None:
        """Whether a base under an older peak is one structure or two is not in the bars.

        Every rule tried for cutting it deleted evidence a gate reads. Left whole, a history
        that really is two structures shows a contraction that widens at the seam, and
        `setup.contractions_must_contract` rejects it there by name.
        """

        frame, left_behind, current = bases_under_an_older_high_series()

        chain = canonical_chain(frame)
        dates = [item["date"] for item in chain["anchors"]]

        self.assertEqual(chain["state"], "resolved")
        # The pause between the older structure's pivot and the advance is a turning point too,
        # so the chain is both structures plus the low that joins them.
        self.assertEqual(dates[: len(left_behind)], left_behind)
        self.assertEqual(dates[-len(current) :], current)
        self.assertEqual(len(dates), len(left_behind) + len(current) + 1)

    def test_a_final_rally_above_an_earlier_one_is_a_contraction_not_a_departure(self) -> None:
        """Inside a correction, clearing an earlier rally top is what contracting looks like.

        A rule that read it as leaving cut the base down to its last two anchors, and after a
        breakout -- when price holds above every interior high at once -- cut it away entirely.
        """

        frame = from_legs(
            ((55, 100, 55), (100, 80, 20), (80, 90, 10), (90, 85, 10), (85, 89, 9),
             (89, 92, 1), (92, 90.5, 3), (90.5, 95, 1)),
            last=(92.1, 95.2, 91.9, 95.0),
        )

        chain = canonical_chain(frame)

        self.assertEqual([round(item["price"]) for item in chain["anchors"]], [100, 80, 90, 85, 92])

    def test_a_left_edge_only_one_reading_finds_is_vouched_for_by_none(self) -> None:
        """A breakout, a shallow slip, and a quiet recovery, which the readings split on.

        Strict holding never sees the departure, because the slip discards the crossing and a
        recovery has no reason to expand again; reading holding as "out of it since the last
        touch" does see it. Each is defensible, so the chain rests on a call the bars did not
        make, and picking either reached `ready` -- one by borrowing the older structure's
        contraction, the other by deleting the one that widened.
        """

        frame = from_legs(
            ((55, 100.10, 55), (100.10, 59.90, 25), (59.90, 80.10, 20), (80.10, 79.20, 3),
             (79.20, 80.60, 2), (80.60, 79.95, 1), (79.95, 82.0, 3), (82.0, 95.10, 14),
             (95.10, 87.90, 10), (87.90, 94.90, 10), (94.90, 98, 1)),
        )
        frame["Volume"] = 1_000_000.0
        cleared = [position for position, label in enumerate(frame.index)
                   if position > 100 and float(frame.at[label, "Close"]) > 80.10]
        frame.iloc[cleared[0], frame.columns.get_loc("Volume")] = 5_000_000.0

        chain = canonical_chain(frame)

        self.assertTrue(chain["left_edge_disputed"])
        self.assertEqual(chain["anchors"], [])
        self.assertEqual(len(chain["left_edge_readings"]), 3)

    def test_a_seam_between_two_structures_shows_up_as_a_contraction_that_widens(self) -> None:
        """What rejects a spliced history, where the left edge is not itself in dispute.

        The chain is read here at the whole-history reading, because the point is the seam the
        contraction gate sees rather than whether the three left-edge readings agree.
        """

        frame = from_legs(
            ((55, 100, 55), (100, 90, 12), (90, 95, 10), (95, 80, 12), (80, 97, 10), (97, 93, 8),
             (93, 96.8, 8), (96.8, 94, 6), (94, 96.6, 6), (96.6, 94.5, 3), (94.5, 99, 1)),
            last=(96.7, 99.2, 96.5, 99.0),
            wick=0.02,
            start="2025-05-01",
        )

        parameters = canonical_chain(frame)["parameters"]
        whole = base_chain(segment(frame, retracement_pct=parameters["retracement_pct"])["anchors"])
        prices = [item["price"] for item in whole]
        depths = [
            100 * (prices[index] - prices[index + 1]) / prices[index]
            for index in range(0, len(prices) - 1, 2)
        ]

        self.assertEqual(len(whole), 9)
        self.assertTrue(any(later > earlier for earlier, later in zip(depths, depths[1:])), depths)


class UnusableHistoryTests(unittest.TestCase):
    def test_a_history_with_no_completed_bars_segments_into_nothing(self) -> None:
        frame, _ = base_series()

        self.assertEqual(segment(frame.iloc[:0], retracement_pct=1.0)["anchors"], [])

    def test_a_history_with_a_repeated_session_is_unusable_rather_than_fatal(self) -> None:
        """A provider that returns the same date twice is a data problem, not a crash.

        Two rows under one label make a bar lookup return a Series, and reading a price off it
        raised inside the detector -- an internal contract failure where the envelope should
        have carried typed unavailability.
        """

        frame, _ = base_series()
        doubled = pd.concat([frame.iloc[:1], frame])

        chain = canonical_chain(doubled)

        self.assertEqual(chain["state"], "unavailable")
        self.assertEqual(chain["anchors"], [])
        # Which kind of unusable, because a repeated session and a history that simply has no
        # base in it send a reader to different places.
        self.assertEqual(chain["rejection"], "history_repeats_a_session")

    def test_a_session_that_traded_nothing_is_data_rather_than_a_fault(self) -> None:
        """The chart accepts a halted session, so the fingerprint it is approved by must too.

        Refusing zero volume here let a chart render successfully with no input digest at all,
        and an artifact with no digest cannot be the thing a setup approval names.
        """

        frame, _ = base_series()
        halted = frame.copy()
        halted.iloc[10, halted.columns.get_loc("Volume")] = 0.0

        self.assertEqual(canonical_chain(halted)["state"], "resolved")
        self.assertEqual(len(bars_fingerprint(halted)), 64)

    def test_two_stamps_on_one_date_are_a_repeated_session_too(self) -> None:
        """They are not duplicates until the time is dropped, and dropping it is what runs."""

        frame, _ = base_series()
        collided = frame.iloc[:3].copy()
        collided.index = [
            pd.Timestamp("2026-01-02 09:30"), pd.Timestamp("2026-01-02 16:00"), pd.Timestamp("2026-01-05 16:00"),
        ]

        self.assertEqual(canonical_chain(collided)["rejection"], "history_repeats_a_session")

    def test_a_bar_no_chart_would_render_is_not_measured_either(self) -> None:
        """One digest across the chart and the setup means one idea of a valid bar."""

        frame, _ = base_series()
        broken = frame.copy()
        broken.iloc[5, broken.columns.get_loc("Open")] = float(broken["Low"].iloc[5]) * 0.5

        self.assertEqual(canonical_chain(broken)["rejection"], "history_contains_invalid_bar_ranges")

    def test_a_breakout_needs_the_whole_window_behind_it(self) -> None:
        """Two sessions is not "its own fifty-day average", however busy the third one is.

        The guard was written, then lost when the window moved into the registry, and reported
        as done without reading the line back.
        """

        index = pd.bdate_range("2026-01-02", periods=3)

        self.assertFalse(_volume_expanded(pd.Series([100.0, 100.0, 201.0], index=index), index[2]))

    def test_the_neighbouring_multiples_have_to_land_in_the_domain_too(self) -> None:
        """The sweep runs at three multiples, and the upper one leaves the domain first."""

        index = pd.bdate_range("2026-01-02", periods=8)
        frame = pd.DataFrame(
            {"Open": [1.3] * 8, "High": [1.5] * 8, "Low": [1.0] * 8, "Close": [1.2] * 8, "Volume": [1e6] * 8},
            index=index,
        )

        chain = canonical_chain(frame)

        self.assertEqual(chain["state"], "unavailable")
        self.assertEqual(chain["rejection"], "typical_daily_range_leaves_no_usable_retracement")

    def test_a_range_too_wide_to_scale_from_leaves_as_unavailable(self) -> None:
        """A derived retracement outside the segmenter's domain is data, not an exception."""

        index = pd.bdate_range("2026-01-02", periods=8)
        frame = pd.DataFrame(
            {"Open": [1.5] * 8, "High": [2.0] * 8, "Low": [1.0] * 8, "Close": [1.0] * 8, "Volume": [1e6] * 8},
            index=index,
        )

        chain = canonical_chain(frame)

        self.assertEqual(chain["state"], "unavailable")
        self.assertEqual(chain["rejection"], "typical_daily_range_leaves_no_usable_retracement")

    def test_a_retracement_that_is_not_a_positive_percentage_is_refused(self) -> None:
        frame, _ = base_series()

        for value in (0.0, -1.0, 100.0):
            with self.subTest(retracement=value):
                with self.assertRaises(ValueError):
                    segment(frame, retracement_pct=value)


if __name__ == "__main__":
    unittest.main()
