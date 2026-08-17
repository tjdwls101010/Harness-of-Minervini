from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
import unittest

from scripts.minervini.providers import ProviderUnavailable
from scripts.minervini.providers.yfinance import current_classification_snapshot


FIXTURES = Path(__file__).parents[1] / "fixtures" / "providers" / "yfinance"


class RetryingInfoTicker:
    def __init__(self, info: dict[str, object]) -> None:
        self._info = info
        self.info_calls = 0

    @property
    def info(self) -> dict[str, object]:
        self.info_calls += 1
        if self.info_calls == 1:
            raise TimeoutError("frozen boundary timeout")
        return self._info


class YFinanceClassificationProviderTests(unittest.TestCase):
    def test_current_classification_normalizes_the_mutable_yfinance_taxonomy_with_auditable_metadata(self) -> None:
        info = json.loads((FIXTURES / "current_classification.json").read_text())
        retrieved_at = datetime(2026, 8, 17, 22, 0, tzinfo=timezone.utc)

        snapshot = current_classification_snapshot("acme", info=info, retrieved_at=retrieved_at)

        self.assertEqual(
            snapshot.data,
            {
                "symbol": "ACME",
                "sector": "Technology",
                "industry": "Semiconductors",
                "industry_id": "yfinance:technology:semiconductors",
            },
        )
        self.assertEqual(snapshot.meta.provider, "yfinance")
        self.assertEqual(snapshot.meta.retrieved_at, retrieved_at)
        self.assertEqual(snapshot.meta.as_of, date(2026, 8, 17))
        self.assertEqual(
            snapshot.meta.coverage,
            {
                "kind": "current_classification_only",
                "historical": False,
                "taxonomy": "mutable_current_only",
                "source": "ticker.info",
                "source_fields": {"sector": "sector", "industry": "industry"},
            },
        )

    def test_ticker_info_retries_once_at_the_external_boundary(self) -> None:
        info = json.loads((FIXTURES / "current_classification.json").read_text())
        ticker = RetryingInfoTicker(info)

        snapshot = current_classification_snapshot("ACME", ticker=ticker, retrieved_at=datetime(2026, 8, 17, tzinfo=timezone.utc))

        self.assertEqual(ticker.info_calls, 2)
        self.assertEqual(snapshot.data["industry_id"], "yfinance:technology:semiconductors")

    def test_current_metadata_is_never_mislabeled_as_historical_classification(self) -> None:
        ticker = RetryingInfoTicker({"sector": "Technology", "industry": "Semiconductors"})

        with self.assertRaises(ProviderUnavailable) as raised:
            current_classification_snapshot(
                "ACME",
                as_of="2026-08-14",
                ticker=ticker,
                retrieved_at=datetime(2026, 8, 17, tzinfo=timezone.utc),
            )

        self.assertEqual(raised.exception.provider, "yfinance")
        self.assertEqual(raised.exception.reason, "historical_classification_unavailable")
        self.assertEqual(raised.exception.operation, "current_classification")
        self.assertEqual(ticker.info_calls, 0)

    def test_missing_current_taxonomy_fields_are_typed_unavailable(self) -> None:
        with self.assertRaises(ProviderUnavailable) as raised:
            current_classification_snapshot("ACME", info={"sector": "Technology"})

        self.assertEqual(raised.exception.provider, "yfinance")
        self.assertEqual(raised.exception.reason, "classification_missing")
        self.assertEqual(raised.exception.operation, "current_classification")


if __name__ == "__main__":
    unittest.main()
