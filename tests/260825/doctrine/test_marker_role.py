"""A value the source named for comparison but never stated as a filter.

The registry had three roles and needed a fourth. "each successive contraction
contained to about half (plus or minus a reasonable amount)" names 0.5 and then
refuses to draw a boundary around it, so 0.5 is not a gate. It is one number, not a
range, so it is not a band. And it is compared against this ticker's measured ratio,
which is exactly what a reference must never be. What the reader needs is the
measurement, the value the source named, and the distance between them.
"""

from __future__ import annotations

import contextlib
import copy
import json
import pathlib
import unittest

from scripts.minervini import doctrine


REGISTRY = pathlib.Path(__file__).resolve().parents[3] / "doctrine" / "claims.json"


@contextlib.contextmanager
def threshold_replaced(claim_id: str, name: str, specification: dict):
    """Substitute one threshold in memory so role behaviour is testable without content."""

    edited = copy.deepcopy(json.loads(REGISTRY.read_text(encoding="utf-8")))
    record = next(item for item in edited["claims"] if item["id"] == claim_id)
    record["thresholds"][name] = specification
    loader = doctrine._load_registry
    doctrine._load_registry = lambda: edited
    try:
        yield
    finally:
        doctrine._load_registry = loader


MARKER = {
    "role": "marker",
    "value": 0.5,
    "unit": "ratio",
    "exact": False,
    "quote_index": 0,
}


class MarkerReportsDistanceAndNeverAVerdictTests(unittest.TestCase):
    def test_a_marker_reports_the_measurement_the_named_value_and_the_distance(self) -> None:
        with threshold_replaced("setup.vcp_supply_contraction", "successive_depth_ratio", MARKER):
            signal = doctrine.evaluate_marker("setup.vcp_supply_contraction", "successive_depth_ratio", 0.46)

        self.assertEqual(signal["role"], "marker")
        self.assertEqual(signal["measured"], 0.46)
        self.assertEqual(signal["source_value"], 0.5)
        self.assertAlmostEqual(signal["distance"], -0.04)

    def test_a_marker_never_reports_a_state_a_verdict_could_consume(self) -> None:
        """A marker that could say "pass" would be a gate the source declined to draw."""

        with threshold_replaced("setup.vcp_supply_contraction", "successive_depth_ratio", MARKER):
            far = doctrine.evaluate_marker("setup.vcp_supply_contraction", "successive_depth_ratio", 9.0)
            near = doctrine.evaluate_marker("setup.vcp_supply_contraction", "successive_depth_ratio", 0.5)

        self.assertEqual(far["state"], "reported")
        self.assertEqual(near["state"], "reported")

    def test_an_absent_measurement_stays_unavailable_rather_than_distance_zero(self) -> None:
        with threshold_replaced("setup.vcp_supply_contraction", "successive_depth_ratio", MARKER):
            signal = doctrine.evaluate_marker("setup.vcp_supply_contraction", "successive_depth_ratio", None)

        self.assertEqual(signal["state"], "unavailable")
        self.assertIsNone(signal["distance"])

    def test_reading_a_marker_as_a_gate_raises_rather_than_deciding(self) -> None:
        with threshold_replaced("setup.vcp_supply_contraction", "successive_depth_ratio", MARKER):
            with self.assertRaises(ValueError):
                doctrine.evaluate_gate("setup.vcp_supply_contraction", "successive_depth_ratio", 0.46)

    def test_a_marker_carrying_a_comparator_is_a_gate_in_disguise_and_is_rejected(self) -> None:
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        record = next(item for item in registry["claims"] if item["id"] == "setup.vcp_supply_contraction")
        record["thresholds"]["successive_depth_ratio"] = {**MARKER, "comparator": "<="}

        self.assertFalse(doctrine.validate(registry)["valid"])


if __name__ == "__main__":
    unittest.main()
