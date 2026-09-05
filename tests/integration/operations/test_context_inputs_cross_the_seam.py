"""The context a caller declares -- the tape, the calendar, the base count -- through the operation."""

from __future__ import annotations

from tests.providers import rows_snapshot

from datetime import date, datetime, timezone
import unittest
import numpy as np
import pandas as pd

from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot


AS_OF = "2025-12-31"
DEFENSE = "management.market_defense_tightens_stops"
EARNINGS = "management.earnings_awareness_while_holding"


def bars(closes: list[float]) -> ProviderSnapshot[pd.DataFrame]:
    index = pd.bdate_range(end=AS_OF, periods=len(closes))
    close = pd.Series(closes, index=index, dtype=float)
    frame = pd.DataFrame({"Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close, "Volume": np.full(len(close), 1_000_000)}, index=index)
    return rows_snapshot(frame, provider="fixture-prices", retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc), as_of=date.fromisoformat(AS_OF), coverage={"completed_only": True})


RISING = list(np.linspace(80.0, 130.0, 132))


def run(**evidence: object) -> dict:
    request = {"ticker": "TEST", "mode": "active", "as_of": AS_OF, "entry_price": 100.0, "entry_date": "2025-11-03", "stop_price": 90.0, **evidence}
    return execute("ticker.risk", request, runtime=Runtime(price_history=lambda ticker, as_of: bars(RISING)))


def reasons(payload: dict) -> list[str | None]:
    return [action.get("reason") for action in payload["data"]["management_actions"]]


class TheTapeTightensTheStop(unittest.TestCase):
    def test_a_defensive_market_raises_the_stop_and_leaves_the_verdict_alone(self) -> None:
        payload = run(market={"state": "defensive"})

        self.assertEqual(payload["data"]["verdict"], "HOLD")
        self.assertIn("market_defense_tightens_stops", reasons(payload))
        action = next(item for item in payload["data"]["management_actions"] if item["doctrine_id"] == DEFENSE)
        self.assertEqual(action["action"], "RAISE_STOP")
        self.assertEqual(action["to_at_least"], 94.0)
        self.assertIn(DEFENSE, payload["doctrine_ids"])

    def test_a_favourable_market_leaves_the_stop_where_the_trader_put_it(self) -> None:
        payload = run(market={"state": "favorable"})

        self.assertNotIn("market_defense_tightens_stops", reasons(payload))


class TheCalendarAndTheBaseCount(unittest.TestCase):
    def test_a_report_ahead_is_a_review_and_the_base_count_is_only_context(self) -> None:
        payload = run(earnings_date="2026-01-14", base_count=4)

        self.assertIn("earnings_ahead", reasons(payload))
        self.assertIn(EARNINGS, payload["doctrine_ids"])
        context = payload["data"]["base_count_context"]
        self.assertEqual(context["base_count"], 4)
        self.assertEqual(context["band"]["state"], "within_source_range")
        self.assertNotIn("base_count", reasons(payload))

    def test_a_base_count_that_is_not_a_count_is_refused_at_the_seam(self) -> None:
        with self.assertRaises(Exception) as caught:
            run(base_count=0)
        self.assertEqual(getattr(caught.exception, "field", None), "base_count")

    def test_an_earnings_date_that_is_not_a_date_is_refused_at_the_seam(self) -> None:
        with self.assertRaises(Exception) as caught:
            run(earnings_date="next tuesday")
        self.assertEqual(getattr(caught.exception, "field", None), "earnings_date")


class TimeEvidenceTravelsWithTheHold(unittest.TestCase):
    def test_the_post_breakout_block_counts_the_sessions_since_the_declared_breakout(self) -> None:
        payload = run(breakout_date="2025-11-03")

        block = payload["data"]["management_evidence"]["post_breakout_behavior"]
        self.assertEqual(block["since_basis"], "breakout_date")
        self.assertGreater(block["sessions_since_entry"], 0)
        self.assertEqual(block["first_sessions"]["source"], "Zanger")
        self.assertIs(block["first_sessions"]["binds"], False)


if __name__ == "__main__":
    unittest.main()


class TheBandEdgesAreAcceptedInputs(unittest.TestCase):
    def test_a_third_base_is_a_valid_count_at_the_lower_edge(self) -> None:
        payload = run(base_count=3)

        block = payload["data"]["base_count_context"]
        self.assertEqual(block["base_count"], 3)
        self.assertEqual(block["band"]["state"], "within_source_range")
