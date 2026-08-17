from __future__ import annotations

import json
from pathlib import Path
import unittest

from scripts.minervini.market import evaluate_market_snapshot
from scripts.minervini.market_evidence import build_market_evidence


FIXTURES = Path(__file__).parents[1] / "fixtures" / "market_evidence"


class MarketEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.qqq_bars = json.loads((FIXTURES / "completed_qqq_ohlcv.json").read_text())
        self.rs_rows = json.loads((FIXTURES / "rs_rows.json").read_text())

    def test_completed_qqq_switch_is_context_only_when_evaluated(self) -> None:
        evidence = build_market_evidence(
            qqq_daily_ohlcv=self.qqq_bars,
            finviz_html=None,
            sector_rows=[],
            industry_rows=[],
            leader_rows=[],
            trade_traction={"state": "positive"},
        )

        snapshot = evaluate_market_snapshot(evidence)

        self.assertEqual(evidence["qqq_21ema"]["state"], "on")
        self.assertEqual(evidence["qqq_21ema"]["rules"]["ON"], "one completed close above the 21 EMA")
        self.assertEqual(evidence["breadth"]["state"], "unavailable")
        self.assertTrue(all(section["state"] == "unavailable" for section in evidence["breadth"]["sections"].values()))
        self.assertTrue(snapshot["regime"]["qqq_switch_is_context_only"])
        self.assertNotEqual(snapshot["regime"]["judgment"], "favorable")

    def test_finviz_sections_degrade_independently(self) -> None:
        evidence = build_market_evidence(
            qqq_daily_ohlcv=self.qqq_bars,
            finviz_html=(FIXTURES / "finviz_partial.html").read_text(),
            sector_rows=[],
            industry_rows=[],
            leader_rows=[],
            trade_traction={"state": "positive"},
        )

        sections = evidence["breadth"]["sections"]

        self.assertEqual(sections["advancing_declining"]["advancing"], {"pct": 54.4, "count": 2314})
        self.assertEqual(sections["new_high_low"]["state"], "unavailable")
        self.assertEqual(sections["sma50"]["below"], {"pct": 38.0, "count": 700})
        self.assertEqual(sections["sma200"]["state"], "unavailable")
        self.assertEqual(evidence["breadth"]["state"], "observed")

    def test_finviz_labels_make_reordered_blocks_semantically_identical(self) -> None:
        evidence = build_market_evidence(
            qqq_daily_ohlcv=self.qqq_bars,
            finviz_html=(FIXTURES / "finviz_reordered.html").read_text(),
            sector_rows=[],
            industry_rows=[],
            leader_rows=[],
            trade_traction={"state": "positive"},
        )

        sections = evidence["breadth"]["sections"]

        self.assertEqual(sections["advancing_declining"]["advancing"], {"pct": 54.4, "count": 2314})
        self.assertEqual(sections["new_high_low"]["new_low"], {"pct": 2.0, "count": 40})
        self.assertEqual(sections["sma50"]["above"], {"pct": 62.0, "count": 1200})
        self.assertEqual(sections["sma200"]["below"], {"pct": 42.0, "count": 800})

    def test_unknown_or_duplicate_finviz_blocks_only_withhold_the_ambiguous_section(self) -> None:
        evidence = build_market_evidence(
            qqq_daily_ohlcv=self.qqq_bars,
            finviz_html=(FIXTURES / "finviz_unknown_duplicate.html").read_text(),
            sector_rows=[],
            industry_rows=[],
            leader_rows=[],
            trade_traction={"state": "positive"},
        )

        sections = evidence["breadth"]["sections"]

        self.assertEqual(sections["advancing_declining"], {"state": "unavailable", "reason": "finviz_section_duplicate"})
        self.assertEqual(sections["new_high_low"], {"state": "unavailable", "reason": "finviz_section_missing"})
        self.assertEqual(sections["sma50"]["state"], "observed")
        self.assertEqual(sections["sma200"]["state"], "observed")

    def test_rs_rows_keep_source_basis_and_do_not_infer_support_or_scores(self) -> None:
        evidence = build_market_evidence(
            qqq_daily_ohlcv=self.qqq_bars,
            finviz_html=None,
            sector_rows=self.rs_rows["sectors"],
            industry_rows=self.rs_rows["industries"],
            leader_rows=self.rs_rows["leaders"],
            trade_traction={"state": "constructive"},
        )

        technology = evidence["sectors"][0]
        avgo = evidence["leaders"][1]
        snapshot = evaluate_market_snapshot(evidence)

        self.assertEqual(technology["basis"], {"as_of": "2026-08-14", "rating": 91, "rank": 1})
        self.assertEqual(technology["price_momentum"]["state"], "supports")
        self.assertEqual(technology["rs_concentration"]["state"], "observed")
        self.assertEqual(technology["breadth"]["state"], "unavailable")
        self.assertEqual(avgo["behavior"]["state"], "observed")
        self.assertEqual(avgo["basis"], {"as_of": "2026-08-14", "rating": 97, "rank": 2})
        self.assertNotIn("score", technology)
        self.assertNotIn("score", snapshot["group_ranks"]["sectors"][0])

    def test_trade_traction_is_a_required_explicit_input(self) -> None:
        with self.assertRaises(TypeError):
            build_market_evidence(
                qqq_daily_ohlcv=self.qqq_bars,
                finviz_html=None,
                sector_rows=[],
                industry_rows=[],
                leader_rows=[],
            )


if __name__ == "__main__":
    unittest.main()
