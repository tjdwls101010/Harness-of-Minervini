"""The registry must refuse what the contract says it refuses.

Each case here is a registry a reviewer walked through: it validated cleanly and then
either crashed a reducer or produced a plausible false verdict.
"""

from __future__ import annotations

import copy
import json
import pathlib
import unittest

from scripts.minervini import doctrine


REGISTRY = pathlib.Path(__file__).resolve().parents[3] / "doctrine" / "claims.json"


def registry() -> dict:
    return copy.deepcopy(json.loads(REGISTRY.read_text(encoding="utf-8")))


def find(payload: dict, claim_id: str) -> dict:
    return next(item for item in payload["claims"] if item["id"] == claim_id)


class ThresholdShapeTests(unittest.TestCase):
    def test_a_gate_whose_value_is_not_a_number_is_rejected(self) -> None:
        broken = registry()
        find(broken, "risk.initial_stop_and_reward")["thresholds"]["initial_stop_ceiling_pct"]["value"] = True

        result = doctrine.validate(broken)

        self.assertFalse(result["valid"])

    def test_a_threshold_a_reducer_depends_on_cannot_be_removed(self) -> None:
        broken = registry()
        del find(broken, "risk.initial_stop_and_reward")["thresholds"]["initial_stop_ceiling_pct"]

        result = doctrine.validate(broken)

        self.assertFalse(result["valid"])
        self.assertTrue(any("initial_stop_ceiling_pct" in error for error in result["errors"]), result["errors"])

    def test_the_live_registry_supplies_every_threshold_the_reducers_read(self) -> None:
        self.assertTrue(doctrine.validate()["valid"])


class LayerAndAttributionTests(unittest.TestCase):
    def test_a_harness_layer_record_cannot_be_a_hard_gate(self) -> None:
        broken = registry()
        record = find(broken, "scope.data_integrity")
        record["kind"] = "hard_gate"

        result = doctrine.validate(broken)

        self.assertFalse(result["valid"])
        self.assertTrue(any("harness" in error for error in result["errors"]), result["errors"])

    def test_a_gate_attributed_to_another_practitioner_is_evaluated_but_never_binds(self) -> None:
        """Ryan's "at least 25%" is a filter, and calling it a population statistic was a lie.

        The registry now records it as what it is and `evaluate_gate` marks it non-binding,
        so the contrast survives without another practitioner's standard being able to
        reject a candidate this harness judges by Minervini's.
        """

        record = doctrine.get_claim("practitioners.breakout_volume.ryan_25pct_min_100_200pct_ideal")

        self.assertEqual(record["claim"]["attributed_to"], "Ryan")
        signal = doctrine.evaluate_gate(
            "practitioners.breakout_volume.ryan_25pct_min_100_200pct_ideal",
            "breakout_volume_increase_min",
            10.0,
        )

        self.assertFalse(signal["binds"])
        self.assertEqual(signal["state"], "contrast_fail")
        self.assertNotIn(signal["state"], {"fail", "pass"})

    def test_a_harness_layer_record_cannot_hold_a_gate_at_all(self) -> None:
        """A practice-layer filter has a source behind it; a harness-layer one has none."""

        broken = registry()
        record = find(broken, "scope.data_integrity")
        record["thresholds"] = {
            "invented_limit": {"role": "gate", "comparator": "<=", "value": 10, "unit": "percent", "exact": True, "quote_index": 0}
        }

        result = doctrine.validate(broken)

        self.assertFalse(result["valid"])
        self.assertTrue(any("harness layer" in error for error in result["errors"]), result["errors"])


class OutOfScopeTests(unittest.TestCase):
    def test_reading_a_position_sizing_threshold_is_refused_at_the_seam(self) -> None:
        record = next(item for item in registry()["claims"] if item.get("out_of_scope") == "position_sizing" and item["thresholds"])
        name = next(iter(record["thresholds"]))

        with self.assertRaises(ValueError):
            doctrine.threshold(record["id"], name)

    def test_evaluating_a_position_sizing_threshold_is_refused_at_the_seam(self) -> None:
        record = next(item for item in registry()["claims"] if item.get("out_of_scope") == "position_sizing" and item["thresholds"])
        name = next(iter(record["thresholds"]))

        with self.assertRaises(ValueError):
            doctrine.evaluate_gate(record["id"], name, 5)
        with self.assertRaises(ValueError):
            doctrine.evaluate_band(record["id"], name, 5)


class BandDirectionTests(unittest.TestCase):
    def test_a_measurement_under_a_growth_band_is_outside_it(self) -> None:
        growth = next(
            (claim_id, name)
            for claim_id in ("fundamentals.minimum_quarterly_earnings_growth",)
            for name, specification in doctrine.get_claim(claim_id)["claim"]["thresholds"].items()
            if specification["role"] == "band"
        )

        # 10% growth against a 20-25% band is not "within range" by any reading.
        self.assertEqual(doctrine.evaluate_band(*growth, 10.0)["state"], "below_source_range")

    def test_a_depth_tighter_than_its_band_is_outside_it_on_the_good_side(self) -> None:
        """12% against a 25-35% depth range is not inside that range, and saying so is not a
        complaint about the base. `direction` is what says the outside it landed on is the
        favourable one -- the state only reports where it sat."""
        signal = doctrine.evaluate_band("eligibility.recent_ipo_primary_base", "three_to_five_week_base_depth_pct", 12.0)

        self.assertEqual(signal["state"], "below_source_range")
        self.assertEqual(signal["direction"], "lower_is_better")

    def test_every_band_declares_which_direction_is_better(self) -> None:
        undeclared = [
            f"{record['id']}.{name}"
            for record in registry()["claims"]
            for name, specification in record["thresholds"].items()
            if specification["role"] == "band" and specification.get("direction") not in {"lower_is_better", "higher_is_better", "inside_is_better"}
        ]
        self.assertEqual(undeclared, [])


if __name__ == "__main__":
    unittest.main()
