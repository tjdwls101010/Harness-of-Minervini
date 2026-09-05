"""Fundamentals does not hand out the exception on the strength of being asked for it.

Five booleans -- technical eligibility, price/volume structure, market alignment, risk controls,
and the request itself -- were enough to turn missing growth data into a waiver. Every one of
them is the caller's own word about a control the caller was supposed to have verified
elsewhere, and none of them causes a single price bar to be read.
"""

from __future__ import annotations

import unittest

from scripts.minervini.fundamentals import evaluate_fundamentals


def facts() -> dict:
    """Every safety fact filed and clear; the growth numbers simply are not there.

    That is the only shape the waiver is about -- integrity gaps stop the evaluation before it,
    so a fixture missing those never reaches the branch under test at all.
    """
    return {
        "source": "sec_filed_facts",
        "filings": [
            {
                "filed_at": "2026-07-15",
                "accounting_basis": "US-GAAP",
                "accounting_integrity": {"status": "clear"},
                "going_concern": {"status": "clear"},
                "dilution": {"status": "clear"},
                "leader_category": {"category": "market_leader"},
                "quarterly": [{"period": "2026-Q1"}, {"period": "2026-Q2"}],
                "annual": [],
            }
        ],
    }


class TheExceptionIsNotAnArgument(unittest.TestCase):
    def test_the_evaluator_no_longer_accepts_the_assertion_at_all(self):
        asserted = {
            "detected": True,
            "quality": "textbook",
            "fundamentals_exception": {
                "status": "map_authorized_only_for_this_vcp-qualified_setup",
                "may_omit": ["verified_fundamentals"],
            },
            "technical_eligibility": "pass",
            "price_volume_structure": "pass",
            "market_alignment": "pass",
            "risk_controls": "pass",
        }

        with self.assertRaises(TypeError):
            evaluate_fundamentals(facts(), as_of="2026-08-24", power_play=asserted)

    def test_the_same_facts_without_the_assertion_are_incomplete(self):
        """The control: this is what the missing growth data is worth on its own."""

        result = evaluate_fundamentals(facts(), as_of="2026-08-24")

        self.assertEqual(result["fundamentals_state"], "incomplete")


if __name__ == "__main__":
    unittest.main()
