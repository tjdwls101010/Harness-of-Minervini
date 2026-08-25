"""The fundamentals waiver cannot be opened by saying it was opened.

The Power Play exception is the only route in this harness that lets a stock through without
verified fundamentals, which makes the word for it the most valuable word a caller can write.
Today it is one: `--fundamentals-state waived_by_exception` reaches BUY-READY with no
fundamental evidence and no Power Play measured anywhere.
"""

from __future__ import annotations

import unittest

from scripts.minervini.risk import reduce_risk


def prospective(**overrides) -> dict:
    evidence = {
        "mode": "prospective",
        "market": "favorable",
        "eligibility": "eligible",
        "setup": "ready",
        "entry_price": 100.0,
        "stop_price": 94.0,
        "upside_price": 112.0,
        "average_gain_pct": 12.0,
    }
    evidence.update(overrides)
    return reduce_risk(evidence)


class AWaiverIsEarnedNotDeclared(unittest.TestCase):
    def test_declaring_the_exception_does_not_satisfy_fundamentals(self):
        verdict = prospective(fundamentals="waived_by_exception")

        self.assertNotEqual(verdict["verdict"], "BUY-READY")
        self.assertIn("fundamentals", verdict["missing"])

    def test_verified_fundamentals_still_reach_the_top_verdict(self):
        """The route that was always earned is untouched."""

        verdict = prospective(fundamentals="supports_convergence")

        self.assertEqual(verdict["verdict"], "BUY-READY")


if __name__ == "__main__":
    unittest.main()
