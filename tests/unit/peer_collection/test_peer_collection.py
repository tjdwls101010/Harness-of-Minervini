from __future__ import annotations

from tests.paths import FIXTURES as SHARED_FIXTURES

import json
import unittest
import pandas as pd

from scripts.minervini.peer_collection import collect_same_industry_peer_rows
from scripts.minervini.peers import compare_same_industry_peers
from scripts.minervini.providers.nasdaq import SecurityRecord


FIXTURES = SHARED_FIXTURES / "peer_collection"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def security(symbol: str, *, exchange: str = "NASDAQ", instrument_type: str = "common_stock", is_adr: bool = False) -> SecurityRecord:
    return SecurityRecord(
        instrument_id=f"nasdaq-trader:{exchange}:{symbol}",
        symbol=symbol,
        exchange=exchange,
        security_name=f"{symbol} common stock",
        instrument_type=instrument_type,
        is_adr=is_adr,
        eligible=True,
        exclusion_reason=None,
    )


class PeerCollectionTests(unittest.TestCase):
    def test_builds_only_master_backed_peer_rows_with_exact_rs_and_completed_price_evidence(self) -> None:
        inputs = fixture("industry_inputs.json")
        prices = {
            ticker: pd.DataFrame(rows).set_index("date")
            for ticker, rows in inputs["prices"].items()
        }
        universe = [
            security("TARGET"),
            security("LEADER", exchange="NYSE"),
            security("ADRPEER", exchange="NYSE", instrument_type="adr", is_adr=True),
        ]

        result = collect_same_industry_peer_rows(
            inputs["target_classification"],
            universe,
            inputs["industry_top_rows"],
            inputs["target_rs_rating"],
            prices,
            as_of=inputs["as_of"],
        )

        self.assertEqual(result["target"]["instrument_id"], "nasdaq-trader:NASDAQ:TARGET")
        self.assertEqual(result["target"]["industry_id"], "yfinance:technology:semiconductors")
        self.assertEqual(result["target"]["rs_evidence"], {"provider": "ibd-rs-rating", "as_of": "2026-08-14", "rating": 94.0})
        self.assertEqual(
            result["target"]["price_evidence"],
            {"provider": "yfinance", "as_of": "2026-08-14", "return_3m_pct": 20.0, "distance_from_52_week_high_pct": 3.2258},
        )
        self.assertEqual([row["instrument_id"] for row in result["candidates"]], ["nasdaq-trader:NYSE:LEADER", "nasdaq-trader:NYSE:ADRPEER"])
        self.assertEqual(result["candidates"][0]["price_evidence"], {"provider": "yfinance", "as_of": "2026-08-14", "return_3m_pct": 41.6667, "distance_from_52_week_high_pct": 2.8571})
        self.assertEqual(result["missing"], [{"ticker": "MISSING", "reason": "absent_from_security_master"}])
        self.assertNotIn("score", result)

        comparison = compare_same_industry_peers(result["target"], result["candidates"])
        self.assertEqual(comparison["comparison_state"], "complete")
        self.assertEqual([peer["ticker"] for peer in comparison["peers"]], ["LEADER", "ADRPEER"])

    def test_marks_an_absent_target_instead_of_inventing_a_stable_instrument_id(self) -> None:
        inputs = fixture("industry_inputs.json")

        result = collect_same_industry_peer_rows(
            inputs["target_classification"],
            [security("LEADER", exchange="NYSE")],
            inputs["industry_top_rows"],
            inputs["target_rs_rating"],
            {},
            as_of=inputs["as_of"],
        )

        self.assertIsNone(result["target"])
        self.assertEqual(result["candidates"], [{"instrument_id": "nasdaq-trader:NYSE:LEADER", "ticker": "LEADER", "industry_id": "yfinance:technology:semiconductors", "exchange": "NYSE", "listing_country": "US", "instrument_type": "common_stock", "is_adr": False, "rs_evidence": {"provider": "ibd-rs-rating", "as_of": "2026-08-14", "rating": 98.0}}])
        self.assertEqual(
            result["missing"],
            [
                {"ticker": "TARGET", "reason": "absent_from_security_master"},
                {"ticker": "ADRPEER", "reason": "absent_from_security_master"},
                {"ticker": "MISSING", "reason": "absent_from_security_master"},
            ],
        )

    def test_leaves_non_exact_rs_or_price_evidence_unavailable(self) -> None:
        inputs = fixture("industry_inputs.json")
        stale_rating = {"rating": 94, "rating_date": "2026-08-13"}
        target_prices = pd.DataFrame(inputs["prices"]["TARGET"][:-1]).set_index("date")

        result = collect_same_industry_peer_rows(
            inputs["target_classification"],
            [security("TARGET")],
            [],
            stale_rating,
            {"TARGET": target_prices},
            as_of=inputs["as_of"],
        )

        self.assertNotIn("rs_evidence", result["target"])
        self.assertNotIn("price_evidence", result["target"])


if __name__ == "__main__":
    unittest.main()
