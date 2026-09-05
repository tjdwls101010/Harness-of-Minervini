"""A value the source named for comparison but never stated as a filter.

Three roles could not carry one. "Generally, a superperformance phase occurs when a stock
is relatively young, for example, during the first 10 years after the initial public
offering" names ten years and then says "for example", so ten is not a limit. It is one
number, not a range, so it is not a band. And it is compared with this ticker's age, which
is exactly what a reference must never be. What the reader needs is the measurement, the
value the source named, and the distance between them.

The case that forced the role is the VCP's "each successive contraction contained to about
half (plus or minus a reasonable amount)". That claim registers no thresholds yet; it gets
them in the slice that measures contractions, and this file tests the role on the markers
the registry actually holds today.
"""

from __future__ import annotations

from tests.paths import REGISTRY

import contextlib
import copy
import json
import unittest

from scripts.minervini import doctrine


IPO_AGE = ("eligibility.ipo_youthfulness_10yr_window", "typical_max_years_since_ipo")


@contextlib.contextmanager
def threshold_replaced(claim_id: str, name: str, specification: dict):
    """Substitute one threshold in memory, for the cases the live registry cannot show."""

    edited = copy.deepcopy(json.loads(REGISTRY.read_text(encoding="utf-8")))
    record = next(item for item in edited["claims"] if item["id"] == claim_id)
    record["thresholds"][name] = specification
    loader = doctrine._load_registry
    doctrine._load_registry = lambda: edited
    try:
        yield
    finally:
        doctrine._load_registry = loader


class MarkerReportsDistanceAndNeverAVerdictTests(unittest.TestCase):
    def test_a_marker_reports_the_measurement_the_named_value_and_the_distance(self) -> None:
        signal = doctrine.evaluate_marker(*IPO_AGE, 12.0)

        self.assertEqual(signal["role"], "marker")
        self.assertEqual(signal["measured"], 12.0)
        self.assertEqual(signal["source_value"], 10)
        self.assertEqual(signal["distance"], 2.0)

    def test_the_marker_carries_the_sentence_that_declined_to_draw_a_boundary(self) -> None:
        signal = doctrine.evaluate_marker(*IPO_AGE, 12.0)

        self.assertIn("for example", signal["quotation"])
        self.assertFalse(signal["exact"])

    def test_a_marker_never_reports_a_state_a_verdict_could_consume(self) -> None:
        """A marker that could say "pass" would be a gate the source declined to draw."""

        far = doctrine.evaluate_marker(*IPO_AGE, 40.0)
        near = doctrine.evaluate_marker(*IPO_AGE, 10.0)

        self.assertEqual(far["state"], "reported")
        self.assertEqual(near["state"], "reported")

    def test_an_absent_measurement_stays_unavailable_rather_than_distance_zero(self) -> None:
        signal = doctrine.evaluate_marker(*IPO_AGE, None)

        self.assertEqual(signal["state"], "unavailable")
        self.assertIsNone(signal["distance"])

    def test_reading_a_marker_as_a_gate_raises_rather_than_deciding(self) -> None:
        with self.assertRaises(ValueError):
            doctrine.evaluate_gate(*IPO_AGE, 12.0)

    def test_a_marker_carrying_a_comparator_is_a_gate_in_disguise_and_is_rejected(self) -> None:
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        record = next(item for item in registry["claims"] if item["id"] == IPO_AGE[0])
        record["thresholds"][IPO_AGE[1]]["comparator"] = "<="

        self.assertFalse(doctrine.validate(registry)["valid"])

    def test_a_marker_may_not_cite_a_pair_the_way_a_reference_may(self) -> None:
        """A number given as two numbers is a range, and a range is a band."""

        with threshold_replaced(
            *IPO_AGE,
            {"role": "marker", "value": [10, 12], "unit": "years", "exact": False, "quote_index": 0},
        ):
            self.assertFalse(doctrine.validate(doctrine._load_registry())["valid"])


if __name__ == "__main__":
    unittest.main()
