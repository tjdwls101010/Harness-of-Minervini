"""A number that selects what gets computed, which none of the four roles could hold.

The retracement a swing detector turns on is compared with a ticker's own moves, so it is not a
reference. It is not a range, a limit the source states as a filter, or a value the source named
at all -- the source never names one. It chooses which series exists before any comparison
happens, and the four roles are all about comparisons.

What it is not is inert. The chain it produces answers a required condition, so the registry
records that it affects the verdict and refuses to let a claim outside this harness's own
doctrine hold one.
"""

from __future__ import annotations

import json
import pathlib
import unittest

from scripts.minervini import doctrine


REGISTRY = pathlib.Path(__file__).resolve().parents[3] / "doctrine" / "claims.json"


def registry() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


class ParameterSeamTests(unittest.TestCase):
    def test_a_registered_parameter_is_readable(self) -> None:
        self.assertGreater(doctrine.parameter("setup.swing_segmentation_convention", "retracement_range_multiple"), 0)

    def test_a_parameter_is_not_a_threshold_and_neither_seam_answers_for_the_other(self) -> None:
        with self.assertRaises(KeyError):
            doctrine.threshold("setup.swing_segmentation_convention", "retracement_range_multiple")
        with self.assertRaises(KeyError):
            doctrine.parameter("risk.initial_stop_and_reward", "initial_stop_ceiling_pct")

    def test_a_parameter_that_affects_the_verdict_cannot_sit_on_a_claim_this_harness_does_not_apply(self) -> None:
        broken = registry()
        record = next(item for item in broken["claims"] if item["id"] == "setup.swing_segmentation_convention")
        record["layer"] = "practice"

        result = doctrine.validate(broken)

        self.assertFalse(result["valid"])
        self.assertTrue(any("parameter" in error for error in result["errors"]), result["errors"])

    def test_a_parameter_must_carry_a_number_or_a_list_of_them(self) -> None:
        broken = registry()
        record = next(item for item in broken["claims"] if item["id"] == "setup.swing_segmentation_convention")
        record["parameters"]["retracement_range_multiple"]["value"] = "two and a half ranges"

        self.assertFalse(doctrine.validate(broken)["valid"])

    def test_every_parameter_says_whether_it_moves_a_verdict(self) -> None:
        for record in registry()["claims"]:
            for name, specification in (record.get("parameters") or {}).items():
                with self.subTest(parameter=f"{record['id']}.{name}"):
                    self.assertIsInstance(specification.get("affects_verdict"), bool)


class TheValuesThemselvesArePinnedTests(unittest.TestCase):
    """Fixtures derived from the registry test the wiring, not the numbers.

    `hidden_bounce` and the neighbour fixture read the multiple and the offsets back so they
    follow the parameter instead of being retuned behind it -- which also means they keep passing
    whatever those values become. Something has to make a change to them deliberate, and this is
    it: the values a whole slice was calibrated against, written down once.
    """

    def test_the_segmentation_runs_at_the_values_this_slice_was_measured_against(self) -> None:
        convention = "setup.swing_segmentation_convention"

        self.assertEqual(doctrine.parameter(convention, "retracement_range_multiple"), 2.5)
        self.assertEqual(doctrine.parameter(convention, "sensitivity_offsets"), [-0.1, 0.1])
        self.assertEqual(doctrine.parameter(convention, "breakout_volume_reference_sessions"), 50)


if __name__ == "__main__":
    unittest.main()
