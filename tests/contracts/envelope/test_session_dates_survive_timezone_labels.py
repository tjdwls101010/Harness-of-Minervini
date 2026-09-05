from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from scripts.minervini import setup_structure
from scripts.minervini.operations import execute
from scripts.minervini.providers import ProviderSnapshot
from tests.contracts.envelope.test_a_declared_vocabulary_matches_the_envelopes import AS_OF, CIK, FILING_AS_OF, filed, measured


class ASessionKeepsTheDateOnItsLabel(unittest.TestCase):
    def test_dropping_a_zone_keeps_wall_clock_order_for_repeated_sessions(self) -> None:
        labels = pd.DatetimeIndex(["2025-12-31 18:00", "2025-12-31 09:00"], tz="UTC")
        expected = pd.DatetimeIndex(["2025-12-31 18:00", "2025-12-31 09:00"])
        pd.testing.assert_index_equal(setup_structure.session_index(labels), expected)

    def test_timezone_labels_do_not_change_the_session_read_by_an_operation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime = measured(Path(temporary) / "ledger.sqlite3")
            cases = (
                ("ticker.qualify", {"ticker": "TEST", "as_of": AS_OF}, runtime),
                ("ticker.risk", {"ticker": "TEST", "as_of": AS_OF, "mode": "active", "entry_price": 95, "entry_date": "2025-12-15", "stop_price": 90, "average_gain_pct": 20}, runtime),
                ("ticker.fundamentals", {"ticker": "TEST", "as_of": FILING_AS_OF, "cik": CIK, "breakout_date": FILING_AS_OF}, filed()),
            )
            for capability, request, plain in cases:
                snapshot = plain.price_history("TEST", request["as_of"])
                frame = snapshot.data.copy()
                frame.index = frame.index.tz_localize("UTC")
                utc = replace(plain, price_history=lambda *args, frame=frame, meta=snapshot.meta: ProviderSnapshot(frame, meta))
                with self.subTest(capability=capability):
                    expected = execute(capability, request, runtime=plain)
                    self.assertIn(expected["status"], {"ok", "partial"})
                    self.assertEqual(execute(capability, request, runtime=utc), expected)
