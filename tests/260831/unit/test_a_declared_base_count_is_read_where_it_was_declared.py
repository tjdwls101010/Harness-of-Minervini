"""A base count declared for an entry decision has to come back out of that decision.

The registry scopes `basecount.*` to prospective_entry and setup, and the reducer computed
the block only inside management_evidence -- a bundle keyed to a position being managed. So
the one mode the claim is actually about accepted the count, validated it, and published
nothing, and an active request that never established a position dropped it too. An input
taken and dropped is worse than an input refused: the caller has no way to tell the
difference from the answer.
"""

from __future__ import annotations

import unittest

from scripts.minervini.risk import reduce_risk
from tests.attestations import planes


BAND = "basecount.typical_top_after_3_to_5_bases"
DISCLAIMER = "basecount.role_and_disclaimer"


def entry(**extra: object) -> dict:
    return {
        "mode": "prospective",
        **planes(),
        "risk": {"state": "pass", "entry_price": 100.0, "stop_price": 94.0, "upside_price": 112.0, "average_gain_pct": 20.0},
        **extra,
    }


class ABaseCountDeclaredForAnEntryIsReported(unittest.TestCase):
    def test_a_count_inside_the_band_is_published_with_the_source_range(self) -> None:
        result = reduce_risk(entry(base_count=4))

        block = result["base_count_context"]
        self.assertEqual(block["state"], "reported")
        self.assertEqual(block["base_count"], 4)
        self.assertEqual(block["band"]["state"], "within_source_range")
        self.assertEqual(block["band"]["source_range"], [3, 5])
        self.assertEqual(block["doctrine_id"], BAND)
        self.assertEqual(block["disclaimer_doctrine_id"], DISCLAIMER)

    def test_a_late_base_is_reported_past_the_band_and_never_touches_the_verdict(self) -> None:
        result = reduce_risk(entry(base_count=7))

        self.assertEqual(result["verdict"], "BUY-READY")
        self.assertEqual(result["failed"], [])
        self.assertEqual(result["waiting"], [])
        self.assertEqual(result["base_count_context"]["band"]["state"], "above_source_range")

    def test_no_declared_count_is_an_absent_input_and_not_a_missing_gate(self) -> None:
        result = reduce_risk(entry())

        self.assertEqual(result["base_count_context"], {"state": "unavailable", "reason": "base_count_not_declared"})
        self.assertEqual(result["verdict"], "BUY-READY")
        self.assertNotIn("base_count", result["missing"])

    def test_a_verdict_that_could_not_be_reached_still_reports_what_it_was_given(self) -> None:
        """The count is not evidence the verdict rests on, so a gap elsewhere cannot consume it."""

        result = reduce_risk({"mode": "prospective", "base_count": 6})

        self.assertEqual(result["verdict"], "INCOMPLETE")
        self.assertEqual(result["base_count_context"]["base_count"], 6)


class OneModeCannotHaveTheCountAndTheOtherLoseIt(unittest.TestCase):
    """It lived inside management_evidence, which one mode does not build and the other empties."""

    HELD = {
        "mode": "active",
        "as_of": "2026-08-21",
        "entry_price": 100.0,
        "entry_date": "2026-08-10",
        "stop_price": 90.0,
        "current_price": 104.0,
        "completed_price_path": {"state": "clear", "checked_level": 90.0, "from": "2026-08-10", "through": "2026-08-21", "bars_checked": 9},
    }

    def test_a_held_position_publishes_the_count_in_the_same_place_an_entry_does(self) -> None:
        held = reduce_risk({**self.HELD, "base_count": 4})

        self.assertEqual(held["verdict"], "HOLD")
        self.assertEqual(held["base_count_context"], reduce_risk(entry(base_count=4))["base_count_context"])
        self.assertNotIn("base_count_context", held["management_evidence"])

    def test_an_active_request_with_no_position_established_keeps_the_count(self) -> None:
        """INCOMPLETE empties the measurements keyed to a position. The count is not one of them."""

        result = reduce_risk({"mode": "active", "as_of": "2026-08-21", "base_count": 4})

        self.assertEqual(result["verdict"], "INCOMPLETE")
        self.assertEqual(result["management_evidence"], {})
        self.assertEqual(result["base_count_context"]["base_count"], 4)


if __name__ == "__main__":
    unittest.main()
