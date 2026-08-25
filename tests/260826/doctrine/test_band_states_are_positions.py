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

import unittest

from scripts.minervini import doctrine

DEPTH = ("eligibility.recent_ipo_primary_base", "three_to_five_week_base_depth_pct")
GROWTH = ("fundamentals.minimum_quarterly_earnings_growth", "minimum_yoy_earnings_growth_percent")


def _band(claim_id: str, name: str) -> dict:
    return doctrine.get_claim(claim_id)["claim"]["thresholds"][name]


class WhereTheMeasurementSat(unittest.TestCase):
    def test_the_two_fixtures_really_point_opposite_ways(self) -> None:
        self.assertEqual(_band(*DEPTH)["direction"], "lower_is_better")
        self.assertEqual(_band(*GROWTH)["direction"], "higher_is_better")

    def test_a_base_shallower_than_the_depth_range_is_below_it(self) -> None:
        low, _ = _band(*DEPTH)["range"]
        signal = doctrine.evaluate_band(*DEPTH, low - 8.0)

        self.assertEqual(signal["state"], "short_of_source_range")
        self.assertLess(signal["band_position"], 0)

    def test_a_company_growing_faster_than_the_growth_range_is_above_it(self) -> None:
        _, high = _band(*GROWTH)["range"]
        signal = doctrine.evaluate_band(*GROWTH, high + 30.0)

        self.assertEqual(signal["state"], "beyond_source_range")
        self.assertGreater(signal["band_position"], 1)

    def test_and_the_unfavourable_sides_already_read_that_way(self) -> None:
        """The half that always worked. Both edges report the same way, and which one is the bad
        one is `direction`'s to say, not the state's."""
        _, deep = _band(*DEPTH)["range"]
        low, _ = _band(*GROWTH)["range"]

        self.assertEqual(doctrine.evaluate_band(*DEPTH, deep + 8.0)["state"], "beyond_source_range")
        self.assertEqual(doctrine.evaluate_band(*GROWTH, low - 8.0)["state"], "short_of_source_range")

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

    def test_below_the_low_edge_is_short_of_the_range(self) -> None:
        for claim_id, name, spec in self.bands:
            low, high = spec["range"]
            with self.subTest(band=f"{claim_id}.{name}", direction=spec["direction"]):
                signal = doctrine.evaluate_band(claim_id, name, low - max(1.0, (high - low) / 2))
                self.assertEqual(signal["state"], "short_of_source_range")
                self.assertLess(signal["band_position"], 0)

    def test_above_the_high_edge_is_beyond_the_range(self) -> None:
        for claim_id, name, spec in self.bands:
            low, high = spec["range"]
            with self.subTest(band=f"{claim_id}.{name}", direction=spec["direction"]):
                signal = doctrine.evaluate_band(claim_id, name, high + max(1.0, (high - low) / 2))
                self.assertEqual(signal["state"], "beyond_source_range")
                self.assertGreater(signal["band_position"], 1)

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


if __name__ == "__main__":
    unittest.main()
