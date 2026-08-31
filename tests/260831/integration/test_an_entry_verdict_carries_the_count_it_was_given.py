"""`--base-count` on a prospective request reached the envelope and left no trace.

The CLI accepts the flag in either mode and `operations` validates it in either mode, so a
caller who declared a fifth base got the same envelope as one who declared nothing. The
registry scopes the claims to prospective_entry and setup, which makes this the mode they
were written for -- and the constitution asks for the count to be reported against the
three-to-five band with the source's own disclaimer beside it.
"""

from __future__ import annotations

import unittest

from scripts.minervini.operations import Runtime, execute


BAND = "basecount.typical_top_after_3_to_5_bases"
DISCLAIMER = "basecount.role_and_disclaimer"

ENTRY = {
    "ticker": "AAPL",
    "as_of": "2026-08-28",
    "market_state": "favorable",
    "eligibility_state": "eligible",
    "setup_state": "ready",
    "fundamentals_state": "supports_convergence",
    "entry_price": 100.0,
    "stop_price": 94.0,
    "upside_price": 112.0,
    "average_gain_pct": 20.0,
}


def entry(**request) -> dict:
    return execute("ticker.risk", {**ENTRY, **request}, runtime=Runtime())


class AnEntryVerdictCarriesTheCountItWasGiven(unittest.TestCase):
    def test_a_declared_count_is_published_with_its_band_and_its_disclaimer(self) -> None:
        payload = entry(base_count=5)

        block = payload["data"]["base_count_context"]
        self.assertEqual(block["state"], "reported")
        self.assertEqual(block["base_count"], 5)
        self.assertEqual(block["band"]["source_range"], [3, 5])
        self.assertIn(BAND, payload["doctrine_ids"])
        self.assertIn(DISCLAIMER, payload["doctrine_ids"])

    def test_a_count_past_the_band_is_reported_and_the_verdict_is_unmoved(self) -> None:
        """A band never carries a verdict; a late base is perspective, not a rejection."""

        late = entry(base_count=8)

        self.assertEqual(late["data"]["base_count_context"]["band"]["state"], "above_source_range")
        self.assertEqual(late["data"]["verdict"], entry(base_count=3)["data"]["verdict"])
        self.assertEqual(late["signals"], [])

    def test_an_undeclared_count_names_itself_absent_rather_than_vanishing(self) -> None:
        payload = entry()

        self.assertEqual(payload["data"]["base_count_context"], {"state": "unavailable", "reason": "base_count_not_declared"})
        self.assertNotIn(BAND, payload["doctrine_ids"])


if __name__ == "__main__":
    unittest.main()
