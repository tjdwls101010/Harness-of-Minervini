"""Two things the audit must not do: skip a session it claims, and cite a claim nobody registered."""

from __future__ import annotations

from tests.providers import rows_snapshot

from datetime import date, datetime, timezone
import unittest
import pandas as pd

from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot


AS_OF = "2025-12-08"


def snapshot(bars: pd.DataFrame) -> ProviderSnapshot[pd.DataFrame]:
    return rows_snapshot(bars, provider="fixture-prices", retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc), as_of=date.fromisoformat(AS_OF), coverage={"completed_only": True})


def frame(rows: list[tuple[str, float, float]]) -> pd.DataFrame:
    index = pd.DatetimeIndex([pd.Timestamp(stamp) for stamp, _, _ in rows])
    closes = [close for _, _, close in rows]
    return pd.DataFrame({"Open": closes, "High": [close * 1.01 for close in closes], "Low": [low for _, low, _ in rows], "Close": closes, "Volume": [1_000_000] * len(rows)}, index=index)


def run(bars: pd.DataFrame, **evidence: object) -> dict:
    request = {"ticker": "TEST", "mode": "active", "as_of": AS_OF, "entry_price": 100.0, "entry_date": "2025-12-01", "stop_price": 94.0, **evidence}
    return execute("ticker.risk", request, runtime=Runtime(price_history=lambda ticker, as_of: snapshot(bars)))


WEEK = [("2025-12-01", 99.0, 100.0), ("2025-12-02", 99.0, 100.0), ("2025-12-03", 99.0, 100.0), ("2025-12-04", 99.0, 100.0), ("2025-12-05", 99.0, 100.0), ("2025-12-08", 99.0, 100.0)]


class TheEntrySessionMustBeInTheHistory(unittest.TestCase):
    def test_a_frame_missing_the_entry_bar_cannot_hold_the_position(self) -> None:
        payload = run(frame([("2025-11-28", 99.0, 100.0)] + WEEK[1:]))

        path = payload["data"]["completed_price_path"]
        self.assertEqual(path["state"], "unavailable")
        self.assertEqual(path["reason"], "no_completed_bar_on_window_start")
        self.assertEqual(payload["data"]["verdict"], "INCOMPLETE")
        self.assertEqual(payload["status"], "partial")
        # Nothing was established, so nothing is measured about it.
        self.assertEqual(payload["data"]["management_evidence"], {})
        self.assertEqual(payload["data"]["management_actions"], [])

    def test_a_stop_raised_on_a_saturday_still_splits_the_window(self) -> None:
        # A stop can be moved on a day the market is shut; an entry cannot happen on one.
        payload = run(frame(WEEK), initial_stop_price=94.0, stop_price=97.0, stop_effective_date="2025-12-06")

        self.assertEqual(payload["data"]["verdict"], "HOLD")
        audits = {audit["role"]: audit for audit in payload["data"]["completed_price_path"]["audits"]}
        self.assertEqual(audits["initial_stop"]["state"], "clear")
        self.assertEqual(audits["initial_stop"]["last_bar_checked"], "2025-12-05")
        self.assertEqual(audits["stop"]["state"], "clear")
        self.assertEqual(audits["stop"]["first_bar_checked"], "2025-12-08")


class CitationsPointAtSomething(unittest.TestCase):
    def test_a_doctrine_id_the_registry_never_heard_of_is_not_cited(self) -> None:
        payload = run(frame(WEEK), management={"invented": {"doctrine_id": "not.a.registered.claim"}})

        self.assertNotIn("not.a.registered.claim", payload["doctrine_ids"])
        for claim_id in payload["doctrine_ids"]:
            self.assertRegex(claim_id, r"^[a-z0-9_]+\.[a-z0-9_]+$")


if __name__ == "__main__":
    unittest.main()
