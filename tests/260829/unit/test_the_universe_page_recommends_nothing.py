"""The discovery universe pages instruments; it does not grade them.

Every row this capability produced carried `recommendation_state: not_recommended` and every
page carried a `recommendation_count` of zero, because nothing in the path ever set anything
else. A constant published as a judgment reads as one -- a name the harness looked at and
declined -- when the truth is that no name here has been looked at yet.
"""

from __future__ import annotations

import unittest

from scripts.minervini.market import build_market_candidates


UNIVERSE = [
    {"instrument_id": "nasdaq:1", "ticker": "AAPL", "exchange": "NASDAQ", "listing_country": "US", "instrument_type": "common_stock"},
    {"instrument_id": "nasdaq:2", "ticker": "BABA", "exchange": "NYSE", "listing_country": "US", "instrument_type": "adr"},
]


class UniversePageTests(unittest.TestCase):
    def test_a_paged_instrument_carries_no_recommendation_word(self) -> None:
        page = build_market_candidates(UNIVERSE)

        self.assertNotIn("recommendation_state", page["candidates"][0])

    def test_the_page_counts_what_it_filtered_and_not_what_it_graded(self) -> None:
        page = build_market_candidates(UNIVERSE, limit=1)

        self.assertNotIn("recommendation_count", page["page"])
        self.assertEqual(page["page"]["candidate_count"], 2)
        self.assertEqual(page["page"]["returned_count"], 1)

    def test_a_recommendation_word_the_caller_supplies_is_not_carried_through(self) -> None:
        page = build_market_candidates([{**UNIVERSE[0], "recommendation_state": "recommended"}])

        self.assertNotIn("recommendation_state", page["candidates"][0])


if __name__ == "__main__":
    unittest.main()
