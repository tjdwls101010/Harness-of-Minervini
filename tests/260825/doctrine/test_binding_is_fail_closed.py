"""Binding must be something a claim says, not something it gets by staying silent.

The first version derived binding from `layer == "canonical" and attributed_to in (None,
"Minervini")`. Attribution was optional, so deleting one line from Ryan's claim made his
standard bind on a harness that follows Minervini's, and the registry validated. Silence
now means the registry is incomplete rather than the house voice speaking.
"""

from __future__ import annotations

from tests.paths import registry

import unittest

from scripts.minervini import doctrine


class AttributionIsRequiredWhereItCanBindTests(unittest.TestCase):
    def test_deleting_an_attribution_is_an_error_rather_than_a_promotion(self) -> None:
        broken = registry()
        record = next(item for item in broken["claims"] if item.get("attributed_to") == "Ryan")
        record.pop("attributed_to")

        result = doctrine.validate(broken)

        self.assertFalse(result["valid"])
        self.assertTrue(any("attributed_to" in error for error in result["errors"]), result["errors"])

    def test_every_canonical_claim_names_the_voice_it_speaks_with(self) -> None:
        for record in registry()["claims"]:
            if record["layer"] == "canonical":
                with self.subTest(claim=record["id"]):
                    self.assertIsInstance(record.get("attributed_to"), str)


class RawValueSeamTests(unittest.TestCase):
    def test_a_marker_value_cannot_be_taken_raw_and_compared_by_hand(self) -> None:
        """`evaluate_marker` exists so the distance travels with the number; this closes the shortcut."""

        with self.assertRaises(ValueError):
            doctrine.threshold("eligibility.ipo_youthfulness_10yr_window", "typical_max_years_since_ipo")

    def test_a_non_binding_gate_value_cannot_be_taken_raw_either(self) -> None:
        with self.assertRaises(ValueError):
            doctrine.threshold("practitioners.breakout_volume.ryan_25pct_min_100_200pct_ideal", "breakout_volume_increase_min")

    def test_a_binding_gate_value_is_still_readable(self) -> None:
        self.assertEqual(doctrine.threshold("risk.initial_stop_and_reward", "initial_stop_ceiling_pct"), 10)

    def test_a_reference_on_a_non_binding_claim_is_readable_because_nothing_compares_it(self) -> None:
        """A window length selects which series to compute; it cannot decide anything."""

        self.assertEqual(doctrine.threshold("setup.volume_state_convention", "swing_baseline_sessions"), 20)


class ContrastGateCannotRejectTests(unittest.TestCase):
    def test_a_non_binding_claim_declaring_rejection_is_invalid(self) -> None:
        broken = registry()
        record = next(item for item in broken["claims"] if item.get("attributed_to") == "Zanger" and item["thresholds"])
        record["failure"]["effect"] = "reject"

        result = doctrine.validate(broken)

        self.assertFalse(result["valid"])
        self.assertTrue(any("reject" in error for error in result["errors"]), result["errors"])


class ReducerManifestTests(unittest.TestCase):
    def test_the_declared_reducer_manifest_cannot_name_a_marker(self) -> None:
        """A marker read as a threshold is a signed distance one comparison away from a verdict.

        This checks the declaration. A reducer that called `evaluate_marker` directly and
        read the sign of `distance` would be past this and past `threshold()` too; what
        stops that being an accident is that the marker's state is never a verdict word.
        """

        manifest = doctrine.REQUIRED_THRESHOLDS
        self.assertTrue(all(role != "marker" for _claim, _name, role in manifest))
        with self.assertRaises(ValueError):
            doctrine._assert_manifest_roles((("eligibility.ipo_youthfulness_10yr_window", "typical_max_years_since_ipo", "marker"),))


class PublicSurfaceTests(unittest.TestCase):
    def test_every_evaluator_a_caller_is_meant_to_reach_is_exported(self) -> None:
        """Not "every evaluator a reducer calls": no reducer reads a marker yet, and the
        seam is still public because reporting one is what the response standard asks for."""

        for name in ("threshold", "evaluate_gate", "evaluate_band", "evaluate_marker", "validate", "get_claim"):
            with self.subTest(name=name):
                self.assertIn(name, doctrine.__all__)


if __name__ == "__main__":
    unittest.main()


class AttributionMustNameSomeoneTests(unittest.TestCase):
    def test_a_blank_attribution_does_not_satisfy_naming_the_voice(self) -> None:
        broken = registry()
        record = next(item for item in broken["claims"] if item["id"] == "eligibility.standard_trend_template")
        record["attributed_to"] = "   "

        result = doctrine.validate(broken)

        self.assertFalse(result["valid"])
        self.assertTrue(any("attributed_to" in error for error in result["errors"]), result["errors"])


class BandValueSeamTests(unittest.TestCase):
    def test_a_band_range_cannot_be_taken_raw_and_compared_by_hand(self) -> None:
        """A band's meaning is where the measurement sits, which only `evaluate_band` reports."""

        with self.assertRaises(ValueError):
            doctrine.threshold("risk.initial_stop_and_reward", "ordinary_loss_target_pct")

    def test_a_reference_is_still_readable_because_nothing_compares_it(self) -> None:
        self.assertEqual(doctrine.threshold("risk.initial_stop_and_reward", "reward_to_risk_preferred"), 3)
