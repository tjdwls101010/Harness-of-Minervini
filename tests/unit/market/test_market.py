from __future__ import annotations

from tests.paths import FIXTURES as SHARED_FIXTURES

import json
import unittest

from scripts.minervini.market import build_market_candidates, evaluate_market_snapshot


FIXTURES = SHARED_FIXTURES / "market"


class MarketSnapshotTests(unittest.TestCase):
    def test_qqq_switch_without_trade_feedback_cannot_issue_favorable_regime(self) -> None:
        snapshot = evaluate_market_snapshot(
            {
                "breadth": {"state": "supports", "advance_decline_ratio": 2.1},
                "qqq_21ema": {"state": "on"},
                "sectors": [
                    {
                        "name": "Technology",
                        "new_highs": {"state": "supports", "measured": {"now": 3, "earlier": 1}},
                        "striking_distance_names": {"state": "reported", "measured": {"within_source_range": 2, "of_names_read": 3}},
                    }
                ],
                "industries": [],
                "leaders": [{"ticker": "NVDA", "behavior": "supports"}],
            }
        )

        self.assertEqual(snapshot["regime"]["judgment"], "incomplete")
        self.assertEqual(snapshot["evidence_quality"]["status"], "partial")
        self.assertIn("trade_traction", {item["id"] for item in snapshot["missing"]})
        self.assertEqual(
            next(signal for signal in snapshot["signal_vector"] if signal["id"] == "qqq_21ema_switch")["state"],
            "supports",
        )

    def test_convergent_evidence_is_ranked_by_explicit_vectors_not_a_weighted_score(self) -> None:
        evidence = json.loads((FIXTURES / "favorable_snapshot.json").read_text())

        snapshot = evaluate_market_snapshot(evidence)

        self.assertEqual(snapshot["regime"]["judgment"], "favorable")
        self.assertEqual(snapshot["evidence_quality"]["status"], "complete")
        self.assertEqual(snapshot["group_ranks"]["sectors"][0]["name"], "Technology")
        top_sector = snapshot["group_ranks"]["sectors"][0]
        self.assertEqual(top_sector["rank_basis"], ["new_highs", "striking_distance_names", "new_high_count", "provider_source_rank_tiebreaker"])
        self.assertNotIn("score", top_sector)
        self.assertEqual(
            {signal["metric"] for signal in top_sector["signal_vector"]},
            set(top_sector["rank_basis"][:2]),
        )

    def test_equal_signal_vectors_preserve_the_provider_source_rank(self) -> None:
        groups = []
        for name, source_rank in (("Zeta", 1), ("Alpha", 2)):
            groups.append(
                {
                    "name": name,
                    "basis": {"rank": source_rank, "as_of": "2026-08-14"},
                    "new_highs": {"state": "unavailable", "reason": "no_ranked_leader_in_this_group"},
                    "striking_distance_names": {"state": "unavailable", "reason": "no_ranked_leader_in_this_group"},
                }
            )

        snapshot = evaluate_market_snapshot(
            {
                "breadth": None,
                "qqq_21ema": None,
                "sectors": groups,
                "industries": [],
                "leaders": [],
                "trade_traction": None,
            }
        )

        ranked = snapshot["group_ranks"]["sectors"]
        self.assertEqual([group["name"] for group in ranked], ["Zeta", "Alpha"])
        self.assertEqual(ranked[0]["source_basis"], {"rank": 1, "as_of": "2026-08-14"})
        self.assertEqual(ranked[0]["rank_basis"][-1], "provider_source_rank_tiebreaker")

    def test_missing_industry_evidence_uses_the_public_industries_identifier(self) -> None:
        snapshot = evaluate_market_snapshot(
            {
                "breadth": None,
                "qqq_21ema": None,
                "sectors": None,
                "industries": None,
                "leaders": [],
                "trade_traction": None,
            }
        )

        missing_ids = {item["id"] for item in snapshot["missing"]}
        self.assertIn("industries", missing_ids)
        self.assertNotIn("industrys", missing_ids)


class CandidateUniverseTests(unittest.TestCase):
    def test_filters_the_recommendation_universe_and_keeps_paging_independent(self) -> None:
        instruments = json.loads((FIXTURES / "candidate_universe.json").read_text())

        first_page = build_market_candidates(instruments, limit=1)
        second_page = build_market_candidates(instruments, limit=1, cursor=first_page["page"]["next_cursor"])

        self.assertEqual(first_page["candidates"][0]["ticker"], "AAPL")
        self.assertEqual(first_page["candidates"][0]["origins"], ["rs-screen", "base-screen"])
        self.assertEqual(first_page["page"], {
            "page_size": 1,
            "cursor": None,
            "next_cursor": "offset:1",
            "returned_count": 1,
            "candidate_count": 2,
            "exclusion_count": 6,
        })
        self.assertEqual(second_page["candidates"][0]["ticker"], "BABA")
        self.assertTrue(second_page["candidates"][0]["is_adr"])
        self.assertIsNone(second_page["page"]["next_cursor"])
        self.assertEqual(
            set(first_page["exclusions"]["reason_counts"]),
            {"etf_context_only", "spac", "otc", "shell_company", "non_us_listing", "unsupported_exchange", "missing_instrument_id"},
        )
        self.assertEqual(first_page["exclusions"]["total_count"], 6)
        self.assertEqual(len(first_page["exclusions"]["samples"]), 1)
        self.assertEqual(first_page["page"]["exclusion_count"], 6)

    def test_zero_candidates_is_a_valid_page(self) -> None:
        page = build_market_candidates([
            {"instrument_id": "arcx:1", "ticker": "SPY", "exchange": "NYSE Arca", "listing_country": "US", "instrument_type": "etf"}
        ])

        self.assertEqual(page["candidates"], [])
        self.assertEqual(page["page"]["candidate_count"], 0)

    def test_exclusion_evidence_is_bounded_even_for_a_large_provider_universe(self) -> None:
        instruments = [
            {
                "instrument_id": f"arcx:{index}",
                "ticker": f"ETF{index}",
                "exchange": "NYSE Arca",
                "listing_country": "US",
                "instrument_type": "etf",
            }
            for index in range(5000)
        ]

        page = build_market_candidates(instruments, limit=5)
        encoded = json.dumps(page)

        self.assertEqual(page["exclusions"]["total_count"], 5000)
        self.assertEqual(page["exclusions"]["reason_counts"], {"etf_context_only": 5000})
        self.assertEqual(len(page["exclusions"]["samples"]), 5)
        self.assertLess(len(encoded), 5000)


if __name__ == "__main__":
    unittest.main()
