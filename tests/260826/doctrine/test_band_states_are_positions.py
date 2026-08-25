"""A band's state says where the measurement sat; `direction` says which edge is the good one.

Those are two different facts and the state was carrying both. A measurement past the good edge --
a base shallower than a depth range, a company growing faster than a growth range -- came back
`within_source_range`, which is a false sentence about a number that is not inside the range at
all. The reader loses the finding twice over: the response standard asks for the measured value
and the range it fell in, and there is no honest way to write that from a state claiming it fell
inside a range it never entered.

The good news that state was trying to carry is not lost. `direction` names which edge is good and
`band_position` says how far past it the measurement sits, so a reader can still tell that being
outside is the favourable outcome here.
"""

from __future__ import annotations

import math
import unittest

from scripts.minervini import doctrine

DEPTH = ("eligibility.recent_ipo_primary_base", "three_to_five_week_base_depth_pct")
GROWTH = ("fundamentals.minimum_quarterly_earnings_growth", "minimum_yoy_earnings_growth_percent")
# A percent band whose low edge is a round number, so a float computation can land beside it.
DEPTH_LIKE = ("fundamentals.power_play_exception", "flag_maximum_decline_pct")


def _band(claim_id: str, name: str) -> dict:
    return doctrine.get_claim(claim_id)["claim"]["thresholds"][name]


class WhereTheMeasurementSat(unittest.TestCase):
    def test_the_two_fixtures_really_point_opposite_ways(self) -> None:
        self.assertEqual(_band(*DEPTH)["direction"], "lower_is_better")
        self.assertEqual(_band(*GROWTH)["direction"], "higher_is_better")

    def test_a_base_shallower_than_the_depth_range_is_below_it(self) -> None:
        low, _ = _band(*DEPTH)["range"]
        signal = doctrine.evaluate_band(*DEPTH, low - 8.0)

        self.assertEqual(signal["state"], "below_source_range")
        self.assertLess(signal["band_position"], 0)

    def test_a_company_growing_faster_than_the_growth_range_is_above_it(self) -> None:
        _, high = _band(*GROWTH)["range"]
        signal = doctrine.evaluate_band(*GROWTH, high + 30.0)

        self.assertEqual(signal["state"], "above_source_range")
        self.assertGreater(signal["band_position"], 1)

    def test_and_the_unfavourable_sides_already_read_that_way(self) -> None:
        """The half that always worked. Both edges report the same way, and which one is the bad
        one is `direction`'s to say, not the state's."""
        _, deep = _band(*DEPTH)["range"]
        low, _ = _band(*GROWTH)["range"]

        self.assertEqual(doctrine.evaluate_band(*DEPTH, deep + 8.0)["state"], "above_source_range")
        self.assertEqual(doctrine.evaluate_band(*GROWTH, low - 8.0)["state"], "below_source_range")

    def test_within_the_range_means_inside_the_range(self) -> None:
        for claim_id, name in (DEPTH, GROWTH):
            low, high = _band(claim_id, name)["range"]
            for measured in (low, (low + high) / 2, high):
                with self.subTest(band=f"{claim_id}.{name}", measured=measured):
                    signal = doctrine.evaluate_band(claim_id, name, measured)
                    self.assertEqual(signal["state"], "within_source_range")


class EveryBandTheRegistryCarries(unittest.TestCase):
    """The registry holds bands pointing three ways, and the reading is positional for all of them.

    Sweeping the whole registry rather than two fixtures is what makes this a rule about bands
    instead of a rule about two claims -- a band registered tomorrow, pointing whichever way, is
    covered the day it lands. Out-of-scope claims are skipped because `evaluate_band` refuses to
    read them at all, which is a separate rule with its own tests."""

    def setUp(self) -> None:
        self.readable = [
            record["claim"] for record in doctrine.list() if not record["claim"].get("out_of_scope")
        ]
        self.bands = [
            (claim["id"], name, spec)
            for claim in self.readable
            for name, spec in (claim.get("thresholds") or {}).items()
            if isinstance(spec, dict) and spec.get("role") == "band"
        ]

    def test_the_sweep_finds_bands_of_all_three_directions(self) -> None:
        directions = {spec["direction"] for _, _, spec in self.bands}

        self.assertEqual(directions, {"lower_is_better", "higher_is_better", "inside_is_better"})

    def test_no_band_hides_in_the_parameters_table(self) -> None:
        """`evaluate_band` reads `thresholds` only, so a band parked in `parameters` would slip
        past the sweep above without failing anything. Say so here rather than let it go quiet."""
        hidden = [
            f"{claim['id']}.{name}"
            for claim in self.readable
            for name, spec in (claim.get("parameters") or {}).items()
            if isinstance(spec, dict) and spec.get("role") == "band"
        ]

        self.assertEqual(hidden, [])

    @staticmethod
    def _step(low: float, high: float) -> float:
        """How far outside an edge to probe.

        Capped rather than scaled so the probe stays a measurement someone could actually
        take: half a span outside [3, 60] weeks is a negative duration, and a probe nothing
        could ever measure proves nothing about how a real one is read.

        Whole where the band is whole, so a count band is probed with a count. Half a session
        is not a reading anything can return, and the [1, 2] band for volume-dry-up days has
        exactly one value below its range -- zero of them -- so that is the one to send."""
        if float(low).is_integer() and float(high).is_integer():
            return 1.0
        return min(1.0, (high - low) / 2)

    def test_under_the_low_edge_is_below_the_range(self) -> None:
        for claim_id, name, spec in self.bands:
            low, high = spec["range"]
            with self.subTest(band=f"{claim_id}.{name}", direction=spec["direction"]):
                signal = doctrine.evaluate_band(claim_id, name, low - self._step(low, high))
                self.assertEqual(signal["state"], "below_source_range")
                self.assertLess(signal["band_position"], 0)
                self.assertEqual(signal["direction"], spec["direction"])

    def test_over_the_high_edge_is_above_the_range(self) -> None:
        for claim_id, name, spec in self.bands:
            low, high = spec["range"]
            with self.subTest(band=f"{claim_id}.{name}", direction=spec["direction"]):
                signal = doctrine.evaluate_band(claim_id, name, high + self._step(low, high))
                self.assertEqual(signal["state"], "above_source_range")
                self.assertGreater(signal["band_position"], 1)
                self.assertEqual(signal["direction"], spec["direction"])

    def test_no_probe_leaves_the_domain_its_unit_allows(self) -> None:
        """Guard on the guard: every unit registered here counts something -- weeks, sessions,
        percent, contractions -- and none of them goes negative. A sweep whose probes nobody
        could ever measure is testing arithmetic rather than the harness. Zero is allowed,
        because a window that has not opened is a real reading of one that has not."""
        for claim_id, name, spec in self.bands:
            low, high = spec["range"]
            with self.subTest(band=f"{claim_id}.{name}", unit=spec["unit"]):
                self.assertGreaterEqual(low - self._step(low, high), 0)

    def test_between_the_edges_is_within_the_range(self) -> None:
        for claim_id, name, spec in self.bands:
            low, high = spec["range"]
            for measured in (low, (low + high) / 2, high):
                with self.subTest(band=f"{claim_id}.{name}", measured=measured):
                    signal = doctrine.evaluate_band(claim_id, name, measured)
                    self.assertEqual(signal["state"], "within_source_range")

    def test_the_direction_travels_with_every_reading(self) -> None:
        """Positional states drop which edge is good, so `direction` has to be there to carry it."""
        for claim_id, name, spec in self.bands:
            with self.subTest(band=f"{claim_id}.{name}"):
                low, high = spec["range"]
                signal = doctrine.evaluate_band(claim_id, name, (low + high) / 2)
                self.assertEqual(signal["direction"], spec["direction"])


class TheStateAgreesWithThePrintedNumber(unittest.TestCase):
    """A signal is read by whoever gets the envelope, and all they have is what it prints.

    `measured` is reported at a fixed precision. Classifying the raw value instead let the two
    disagree: a 20% decline computed from 10.10 to 8.08 is 19.999999999999996, printed 20.0,
    and against a range starting at 20 the signal said a measurement of 20.0 fell below 20.
    Arithmetic, but nothing in the envelope says so, and a reader cannot tell it from a
    mistake. The rule is stated as a relation between two published fields rather than as a
    rounding step, so it holds whatever the precision is set to."""

    RAW = (
        100.0 * (10.10 - 8.08) / 10.10,  # a real 20% decline, one ulp short of it
        19.999999999999996,
        20.0,
        24.999999999999996,
        25.000000000000004,
        22.5,
        19.99,
        25.01,
        19.9999,        # below the edge by less than band_position's own precision
        25.0001,        # and above it by less
        19.9999985714,  # a cent's difference on a $700,000 high, per round two
        25.0000014286,
        19.9999999999,  # and the last place the printed measurement still distinguishes
        25.0000000001,
        0.0,
        73.0,
    )

    def _signals(self):
        for raw in self.RAW:
            yield raw, doctrine.evaluate_band(*DEPTH_LIKE, raw)

    def test_every_state_matches_what_the_signal_printed(self) -> None:
        for raw, signal in self._signals():
            low, high = signal["source_range"]
            printed = signal["measured"]
            expected = (
                "above_source_range" if printed > high
                else "below_source_range" if printed < low
                else "within_source_range"
            )
            with self.subTest(raw=repr(raw), printed=printed):
                self.assertEqual(signal["state"], expected)

    def test_the_band_position_lands_on_the_same_side_the_state_names(self) -> None:
        """Outside the range means strictly outside in both fields, right up to the edge.

        Four places is a reader's resolution, not the range's: a measurement a ten-millionth
        of a span above the high edge is above it, and a position of exactly 1.0 beside a
        state of above_source_range is two published fields disagreeing about one number.
        Rounding is allowed to cost precision and is not allowed to cost the side."""
        for raw, signal in self._signals():
            position, state = signal["band_position"], signal["state"]
            with self.subTest(raw=repr(raw), state=state, position=repr(position)):
                if state == "below_source_range":
                    self.assertLess(position, 0)
                elif state == "above_source_range":
                    self.assertGreater(position, 1)
                else:
                    self.assertGreaterEqual(position, 0)
                    self.assertLessEqual(position, 1)
                    # Inside the range the position is a true non-negative, never the -0.0 a
                    # raw-value computation leaves behind at the low edge.
                    self.assertGreater(math.copysign(1.0, position), 0)

    def test_an_ordinary_reading_still_comes_back_at_a_readable_resolution(self) -> None:
        """The edge rule must not turn every position into a wall of digits."""
        for measured, expected in ((22.5, 0.5), (19.99, -0.002), (26.0, 1.2)):
            with self.subTest(measured=measured):
                self.assertEqual(doctrine.evaluate_band(*DEPTH_LIKE, measured)["band_position"], expected)

    def test_the_edge_buys_only_the_places_it_needs(self) -> None:
        """Keeping the side is the constraint; the digits are the price, and the price is paid
        one place at a time.

        25.0000014286 against [20, 25] sits at 1.00000028572 of the span. Four, five and six
        places all round that to 1.0 and lose the side; seven is the first that does not.
        Reporting the raw float instead would preserve the side too and hand the reader
        seventeen digits to say the same thing."""
        signal = doctrine.evaluate_band(*DEPTH_LIKE, 25.0000014286)

        self.assertEqual(signal["state"], "above_source_range")
        self.assertEqual(signal["band_position"], 1.0000003)

    def test_a_difference_a_reader_could_see_is_still_a_difference(self) -> None:
        """Agreeing with the print must not become a tolerance wide enough to swallow a real
        measurement.

        Percentages here are computed from prices carrying two decimals of their own, so a
        difference in the third decimal of a percentage point is an ordinary result rather
        than float noise. Coarsening what the envelope prints would quietly widen the
        classification with it -- at two decimals 19.999 prints as 20.0 and the band would
        call it inside a range it is under."""
        for measured in (19.99, 19.999):
            with self.subTest(measured=measured):
                signal = doctrine.evaluate_band(*DEPTH_LIKE, measured)

                self.assertEqual(signal["measured"], measured)
                self.assertEqual(signal["state"], "below_source_range")


if __name__ == "__main__":
    unittest.main()
