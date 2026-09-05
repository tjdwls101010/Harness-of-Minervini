from __future__ import annotations

from tests.paths import FIXTURES as SHARED_FIXTURES

import copy
import json
import unittest

from scripts.minervini.peers import compare_same_industry_peers


FIXTURES = SHARED_FIXTURES / "peers"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


class SameIndustryPeersTests(unittest.TestCase):
    def test_ranks_only_same_industry_us_common_and_adr_rows_by_explicit_evidence(self) -> None:
        evidence = load_fixture("same_industry_rows.json")

        result = compare_same_industry_peers(evidence["target"], evidence["candidates"])

        self.assertEqual(result["comparison_state"], "incomplete")
        self.assertEqual(result["peer_count"], 2)
        self.assertEqual([peer["ticker"] for peer in result["peers"]], ["LEADER", "ADRPEER"])
        self.assertEqual(result["target"]["rank"], 3)
        self.assertEqual(
            result["rank_basis"],
            ["rs_rating_desc", "return_3m_pct_desc", "distance_from_52_week_high_pct_asc", "ticker_asc", "instrument_id_asc"],
        )
        self.assertNotIn("score", result)
        self.assertEqual(
            result["peers"][0]["leadership_evidence"],
            {
                "rs_rating": {"value": 98.0, "as_of": "2026-08-14", "provider": "ibd-rs-rating"},
                "price": {"return_3m_pct": 57.0, "distance_from_52_week_high_pct": 1.1, "as_of": "2026-08-14", "provider": "yfinance"},
            },
        )
        self.assertEqual(
            result["missing"],
            [{"instrument_id": "nasdaq:INCOMPLETE", "ticker": "INCOMPLETE", "fields": ["price_evidence"]}],
        )
        self.assertEqual(
            result["exclusions"],
            [
                {"instrument_id": "nasdaq:OTHER", "ticker": "OTHER", "reasons": ["different_industry"]},
                {"instrument_id": "arcx:ETF", "ticker": "ETF", "reasons": ["etf_context_only"]},
                {"instrument_id": None, "ticker": "NOID", "reasons": ["missing_instrument_id"]},
            ],
        )

    def test_target_or_eligible_peer_without_required_evidence_is_incomplete_not_a_false_rank(self) -> None:
        evidence = load_fixture("same_industry_rows.json")
        target = copy.deepcopy(evidence["target"])
        target["rs_evidence"] = {"provider": "ibd-rs-rating", "rating": 94}

        result = compare_same_industry_peers(target, evidence["candidates"])

        self.assertEqual(result["comparison_state"], "incomplete")
        self.assertIsNone(result["target"]["rank"])
        self.assertEqual(result["peers"], [])
        self.assertEqual(result["peer_count"], 0)
        self.assertEqual(
            result["missing"],
            [
                {"instrument_id": "nasdaq:TARGET", "ticker": "TARGET", "fields": ["rs_evidence.as_of"]},
                {"instrument_id": "nasdaq:INCOMPLETE", "ticker": "INCOMPLETE", "fields": ["price_evidence"]},
            ],
        )

    def test_returns_an_honest_empty_comparison_when_no_eligible_same_industry_peer_exists(self) -> None:
        evidence = load_fixture("same_industry_rows.json")

        result = compare_same_industry_peers(evidence["target"], [evidence["candidates"][3], evidence["candidates"][4]])

        self.assertEqual(result["comparison_state"], "complete")
        self.assertEqual(result["peer_count"], 0)
        self.assertEqual(result["peers"], [])
        self.assertEqual(result["target"]["rank"], 1)
        self.assertEqual(result["missing"], [])

    def test_wrong_provider_evidence_is_unavailable_not_a_rankable_substitute(self) -> None:
        evidence = load_fixture("same_industry_rows.json")
        candidate = copy.deepcopy(evidence["candidates"][0])
        candidate["rs_evidence"]["provider"] = "web_narrative"

        result = compare_same_industry_peers(evidence["target"], [candidate])

        self.assertEqual(result["comparison_state"], "incomplete")
        self.assertEqual(result["peer_count"], 0)
        self.assertEqual(result["target"]["rank"], 1)
        self.assertEqual(
            result["missing"],
            [{"instrument_id": "nyse:LEADER", "ticker": "LEADER", "fields": ["rs_evidence.provider"]}],
        )

    def test_explicit_first_party_rs_marker_is_preserved_when_no_named_rs_provider_is_available(self) -> None:
        evidence = load_fixture("same_industry_rows.json")
        candidate = copy.deepcopy(evidence["candidates"][0])
        candidate["rs_evidence"]["provider"] = "first_party"

        result = compare_same_industry_peers(evidence["target"], [candidate])

        self.assertEqual(result["comparison_state"], "complete")
        self.assertEqual(result["peers"][0]["leadership_evidence"]["rs_rating"]["provider"], "first_party")

    def test_out_of_range_rs_rating_is_unavailable_not_a_rankable_substitute(self) -> None:
        evidence = load_fixture("same_industry_rows.json")
        candidate = copy.deepcopy(evidence["candidates"][0])
        candidate["rs_evidence"]["rating"] = 100

        result = compare_same_industry_peers(evidence["target"], [candidate])

        self.assertEqual(result["comparison_state"], "incomplete")
        self.assertEqual(result["peer_count"], 0)
        self.assertEqual(result["target"]["rank"], 1)
        self.assertEqual(
            result["missing"],
            [{"instrument_id": "nyse:LEADER", "ticker": "LEADER", "fields": ["rs_evidence.rating"]}],
        )


if __name__ == "__main__":
    unittest.main()
