"""Behavior checks for operations cache."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import pandas as pd
from scripts.minervini.cache import ProviderCache
from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot
from ._operation_fixtures import AS_OF, price_snapshot, rs_snapshot


class OperationCompositionTests(unittest.TestCase):
    def test_no_cache_bypasses_both_operation_cache_reads_and_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            calls = {"price": 0, "rs": 0}

            def prices(ticker: str, as_of: str) -> ProviderSnapshot[pd.DataFrame]:
                calls["price"] += 1
                return price_snapshot()

            def rating(ticker: str, as_of: str) -> ProviderSnapshot[dict[str, object]]:
                calls["rs"] += 1
                return rs_snapshot()

            runtime = Runtime(
                price_history=prices,
                rs_rating=rating,
                cache=ProviderCache(root=Path(temporary)),
            )

            first = execute("ticker.qualify", {"ticker": "TEST", "as_of": AS_OF}, runtime=runtime)
            cached = execute("ticker.qualify", {"ticker": "TEST", "as_of": AS_OF}, runtime=runtime)
            bypassed = execute("ticker.qualify", {"ticker": "TEST", "as_of": AS_OF, "no_cache": True}, runtime=runtime)
            restored = execute("ticker.qualify", {"ticker": "TEST", "as_of": AS_OF}, runtime=runtime)

            self.assertEqual([item["status"] for item in (first, cached, bypassed, restored)], ["ok", "ok", "ok", "ok"])
            self.assertEqual(calls, {"price": 2, "rs": 2})
