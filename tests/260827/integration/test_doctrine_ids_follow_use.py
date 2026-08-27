"""doctrine_ids is the audit route to the claims a result actually used, not a fixed list."""

from __future__ import annotations

from datetime import date, datetime, timezone
import unittest

import numpy as np
import pandas as pd

from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot, SnapshotMeta


AS_OF = "2025-12-31"


def bars(closes: list[float]) -> ProviderSnapshot[pd.DataFrame]:
    index = pd.bdate_range(end=AS_OF, periods=len(closes))
    close = pd.Series(closes, index=index, dtype=float)
    frame = pd.DataFrame({"Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close, "Volume": np.full(len(close), 1_000_000)}, index=index)
    return ProviderSnapshot(frame, SnapshotMeta(provider="fixture-prices", retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc), as_of=date.fromisoformat(AS_OF), coverage={"completed_only": True}))


class ProspectiveCitesNoManagementClaims(unittest.TestCase):
    def test_a_buy_ready_prospective_envelope_cites_only_what_it_read(self) -> None:
        payload = execute(
            "ticker.risk",
            {"ticker": "TEST", "as_of": AS_OF, "market": {"state": "favorable"}, "eligibility": {"state": "eligible"}, "setup": {"state": "ready"}, "fundamentals": {"state": "supports_convergence"}, "entry_price": 200.0, "stop_price": 188.0, "upside_price": 224.0, "average_gain_pct": 24.0},
            runtime=Runtime(),
        )

        self.assertEqual(payload["data"]["verdict"], "BUY-READY")
        self.assertNotIn("management.tl_stage12_half_at_five_percent", payload["doctrine_ids"])
        self.assertNotIn("management.ema21_sma50_roles", payload["doctrine_ids"])
        self.assertIn("risk.initial_stop_and_reward", payload["doctrine_ids"])


class ActiveCitesWhatItsPayloadNames(unittest.TestCase):
    def run_active(self, **request: object) -> dict:
        base = {"ticker": "TEST", "mode": "active", "entry_price": 100.0, "entry_date": "2025-10-01", "stop_price": 94.0, "as_of": AS_OF}
        return execute("ticker.risk", {**base, **request}, runtime=Runtime(price_history=lambda ticker, as_of: bars(list(np.linspace(100.0, 108.0, 90)))))

    def test_a_profiled_hold_cites_the_profile_claim_it_acted_from(self) -> None:
        payload = self.run_active(management_profile="tl_stage12", average_gain_pct=8.0)

        cited = payload["doctrine_ids"]
        self.assertEqual(payload["data"]["verdict"], "HOLD")
        self.assertIn("management.tl_stage12_half_at_five_percent", cited)
        self.assertIn("management.tl_sell_into_strength_at_average_gain_and_r_multiples", cited)
        self.assertIn("management.ema21_sma50_roles", cited)

    def test_every_claim_named_anywhere_in_the_payload_is_cited(self) -> None:
        payload = self.run_active(stage2_start="2025-10-01")

        named: set[str] = set()

        def walk(value: object) -> None:
            if isinstance(value, dict):
                claim = value.get("doctrine_id")
                if isinstance(claim, str):
                    named.add(claim)
                for item in value.values():
                    walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)

        walk(payload["data"])
        self.assertLessEqual(named, set(payload["doctrine_ids"]), named - set(payload["doctrine_ids"]))


if __name__ == "__main__":
    unittest.main()
