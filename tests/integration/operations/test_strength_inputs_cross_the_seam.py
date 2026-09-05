"""What --base-top and --breakout-date buy at the operation seam, and what their absence costs."""

from __future__ import annotations

from tests.providers import rows_snapshot

from datetime import date, datetime, timezone
import unittest
import numpy as np
import pandas as pd

from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot


AS_OF = "2025-12-31"
PAUSE = "management.tl_base_extension_pause_zone"
FAILED_VOLUME = "management.low_volume_breakout_then_high_volume_selling"


def frame(rows: list[tuple[float, float, float, float, int]]) -> pd.DataFrame:
    index = pd.bdate_range(end=AS_OF, periods=len(rows))
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"], index=index)


def snapshot(bars: pd.DataFrame) -> ProviderSnapshot[pd.DataFrame]:
    return rows_snapshot(bars, provider="fixture-prices", retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc), as_of=date.fromisoformat(AS_OF), coverage={"completed_only": True})


def flat(sessions: int, close: float = 100.0, volume: int = 1_000_000) -> list[tuple[float, float, float, float, int]]:
    return [(close, close * 1.01, close * 0.99, close, volume)] * sessions


def bar(close: float, volume: int = 1_000_000, *, open_: float | None = None) -> tuple[float, float, float, float, int]:
    return (close if open_ is None else open_, close * 1.01, close * 0.99, close, volume)


def run(bars: pd.DataFrame, evidence: dict) -> dict:
    return execute("ticker.risk", {"ticker": "TEST", "mode": "active", "as_of": AS_OF, **evidence}, runtime=Runtime(price_history=lambda ticker, as_of: snapshot(bars)))


def reasons(payload: dict) -> list[str | None]:
    return [action.get("reason") for action in payload["data"]["management_actions"]]


class TheBaseTopTheTraderDeclares(unittest.TestCase):
    """A rise of 22% over the declared base top sits inside the zone TraderLion describes."""

    def bars(self) -> pd.DataFrame:
        return frame(flat(60) + [bar(close) for close in np.linspace(101.0, 122.0, 20)])

    def position(self) -> dict:
        bars = self.bars()
        return {"entry_price": 101.0, "entry_date": bars.index[60].date().isoformat(), "stop_price": 95.0}

    def test_with_the_base_top_the_pause_zone_is_a_tagged_review(self) -> None:
        payload = run(self.bars(), {**self.position(), "base_top": 100.0, "breakout_date": self.position()["entry_date"]})

        block = payload["data"]["management_evidence"]["base_extension"]
        self.assertEqual(block["extension_pct"], 22.0)
        self.assertEqual(block["band"]["state"], "within_source_range")
        self.assertIn("base_extension_pause_zone", reasons(payload))
        review = next(action for action in payload["data"]["management_actions"] if action.get("reason") == "base_extension_pause_zone")
        self.assertIs(review["binds"], False)
        self.assertEqual(review["source"], "[TL]")
        self.assertIn(PAUSE, payload["doctrine_ids"])

    def test_without_it_the_block_says_why_and_nothing_is_inferred(self) -> None:
        payload = run(self.bars(), self.position())

        self.assertEqual(payload["data"]["management_evidence"]["base_extension"], {"state": "unavailable", "reason": "base_top_not_declared"})
        self.assertNotIn("base_extension_pause_zone", reasons(payload))
        self.assertNotIn(PAUSE, payload["doctrine_ids"])


class TheBreakoutSessionTheTraderDeclares(unittest.TestCase):
    """A breakout on light volume, then selling heavier than the breakout itself."""

    def bars(self) -> pd.DataFrame:
        return frame(flat(60) + [bar(105.0, 800_000), bar(106.0), bar(103.0, 2_000_000)] + flat(3, 103.0))

    def position(self) -> dict:
        bars = self.bars()
        return {"entry_price": 105.0, "entry_date": bars.index[60].date().isoformat(), "stop_price": 98.0}

    def test_with_the_breakout_date_the_heavier_selling_is_a_binding_review(self) -> None:
        bars = self.bars()
        payload = run(bars, {**self.position(), "breakout_date": bars.index[60].date().isoformat()})

        block = payload["data"]["management_evidence"]["failed_volume_confirmation"]
        self.assertEqual(block["breakout_volume_ratio"], 0.8)
        self.assertEqual(block["heaviest_down_session"]["volume_ratio"], 2.0)
        self.assertIs(block["selling_volume_exceeded_breakout_volume"], True)
        review = next(action for action in payload["data"]["management_actions"] if action.get("reason") == "selling_volume_exceeded_breakout_volume")
        self.assertEqual(review["action"], "REVIEW")
        self.assertIs(review["binds"], True)
        self.assertNotIn("reduce_or_sell", review)
        self.assertIn(FAILED_VOLUME, payload["doctrine_ids"])
        self.assertEqual(payload["data"]["verdict"], "HOLD")

    def test_without_it_the_volume_comparison_is_unavailable_not_guessed_from_the_entry(self) -> None:
        payload = run(self.bars(), self.position())

        self.assertEqual(payload["data"]["management_evidence"]["failed_volume_confirmation"], {"state": "unavailable", "reason": "breakout_date_not_declared"})
        self.assertNotIn("failed_volume_confirmation", reasons(payload))

    def test_without_it_the_post_breakout_blocks_are_withheld_by_name(self) -> None:
        payload = run(self.bars(), self.position())

        evidence = payload["data"]["management_evidence"]
        withheld = {"state": "unavailable", "reason": "breakout_date_not_declared"}
        self.assertEqual(evidence["key_reversal"], withheld)
        self.assertEqual(evidence["gaps_since_breakout"], withheld)
        self.assertEqual(evidence["post_breakout_behavior"], withheld)


class InputsThatDoNotSurviveValidation(unittest.TestCase):
    def test_a_base_top_of_zero_is_refused_at_the_seam(self) -> None:
        with self.assertRaises(Exception) as caught:
            run(frame(flat(60)), {"entry_price": 100.0, "entry_date": "2025-11-03", "stop_price": 95.0, "base_top": 0.0})
        self.assertEqual(getattr(caught.exception, "field", None), "base_top")

    def test_a_breakout_after_as_of_is_refused_at_the_seam(self) -> None:
        with self.assertRaises(Exception) as caught:
            run(frame(flat(60)), {"entry_price": 100.0, "entry_date": "2025-11-03", "stop_price": 95.0, "breakout_date": "2026-02-02"})
        self.assertEqual(getattr(caught.exception, "field", None), "breakout_date")


if __name__ == "__main__":
    unittest.main()
