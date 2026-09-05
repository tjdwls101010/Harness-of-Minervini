"""doctrine_ids is the audit route to the claims a result actually used, not a fixed list."""

from __future__ import annotations

from tests.providers import rows_snapshot

from datetime import date, datetime, timezone
import unittest
import numpy as np
import pandas as pd

from scripts.minervini.doctrine import get_claim
from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot
from tests.attestations import envelopes


AS_OF = "2025-12-31"


def bars(closes: list[float]) -> ProviderSnapshot[pd.DataFrame]:
    index = pd.bdate_range(end=AS_OF, periods=len(closes))
    close = pd.Series(closes, index=index, dtype=float)
    frame = pd.DataFrame({"Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close, "Volume": np.full(len(close), 1_000_000)}, index=index)
    return rows_snapshot(frame, provider="fixture-prices", retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc), as_of=date.fromisoformat(AS_OF), coverage={"completed_only": True})


class ProspectiveCitesNoManagementClaims(unittest.TestCase):
    def test_a_buy_ready_prospective_envelope_cites_only_what_it_read(self) -> None:
        payload = execute(
            "ticker.risk",
            {"ticker": "TEST", "as_of": AS_OF, "evidence": envelopes(), "entry_price": 200.0, "stop_price": 188.0, "upside_price": 224.0, "average_gain_pct": 24.0},
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


class EveryCitationIsAClaimThisCapabilityIsRegisteredFor(unittest.TestCase):
    """A citation the registry does not expect from here is a contract nobody agreed to."""

    def payload(self) -> dict:
        index = pd.bdate_range(end=AS_OF, periods=80)
        return execute(
            "ticker.risk",
            {
                "ticker": "TEST",
                "mode": "active",
                "as_of": AS_OF,
                "entry_price": 100.0,
                "entry_date": index[60].date().isoformat(),
                "breakout_date": index[60].date().isoformat(),
                "stop_price": 90.0,
                "base_count": 4,
                "base_top": 95.0,
                "stage2_start": index[10].date().isoformat(),
            },
            runtime=Runtime(price_history=lambda ticker, as_of: bars([100.0] * 80)),
        )

    def test_ticker_risk_is_a_registered_consumer_of_everything_it_cites(self) -> None:
        for claim_id in self.payload()["doctrine_ids"]:
            with self.subTest(claim=claim_id):
                self.assertIn("ticker.risk", get_claim(claim_id)["claim"]["consumers"])

    def test_a_claim_named_beside_a_disclaimer_reaches_the_envelope(self) -> None:
        payload = self.payload()
        disclaimer = payload["data"]["base_count_context"]["disclaimer_doctrine_id"]

        # It is cited under its own key rather than doctrine_id, and a collector that read
        # only that one key published a result citing a claim the envelope never listed.
        self.assertIn(disclaimer, payload["doctrine_ids"])


class AMarkerTravelsWithItsDistance(unittest.TestCase):
    def test_the_closing_range_is_published_as_the_marker_the_registry_records(self) -> None:
        index = pd.bdate_range(end=AS_OF, periods=80)
        payload = execute(
            "ticker.risk",
            {"ticker": "TEST", "mode": "active", "as_of": AS_OF, "entry_price": 100.0, "entry_date": index[60].date().isoformat(), "breakout_date": index[60].date().isoformat(), "stop_price": 90.0},
            runtime=Runtime(price_history=lambda ticker, as_of: bars([100.0] * 80)),
        )

        marker = payload["data"]["management_evidence"]["key_reversal"]["features"]["closing_range_marker"]
        self.assertEqual(marker["role"], "marker")
        self.assertEqual(marker["source_value"], 50)
        self.assertEqual(marker["state"], "reported")
        self.assertAlmostEqual(marker["distance"], abs(marker["measured"] - 50))


class ACitedClaimSaysWhichHalfWasRead(unittest.TestCase):
    """Evidence a reading never consumes is named, and is not the same as evidence it wanted."""

    def test_the_climax_names_the_base_count_it_does_not_read(self) -> None:
        index = pd.bdate_range(end=AS_OF, periods=80)
        payload = execute(
            "ticker.risk",
            {"ticker": "TEST", "mode": "active", "as_of": AS_OF, "entry_price": 100.0, "entry_date": index[60].date().isoformat(), "stop_price": 90.0},
            runtime=Runtime(price_history=lambda ticker, as_of: bars([100.0] * 80)),
        )

        climax = payload["data"]["management_evidence"]["climax"]
        self.assertEqual(climax["claim_inputs_not_read"], ["base_count"])
        self.assertEqual(climax["missing_inputs"], [])

    def test_the_base_count_disclaimer_names_the_history_it_does_not_read(self) -> None:
        index = pd.bdate_range(end=AS_OF, periods=80)
        payload = execute(
            "ticker.risk",
            {"ticker": "TEST", "mode": "active", "as_of": AS_OF, "entry_price": 100.0, "entry_date": index[60].date().isoformat(), "stop_price": 90.0, "base_count": 4},
            runtime=Runtime(price_history=lambda ticker, as_of: bars([100.0] * 80)),
        )

        block = payload["data"]["base_count_context"]
        self.assertEqual(block["disclaimer_doctrine_id"], "basecount.role_and_disclaimer")
        self.assertEqual(block["claim_inputs_not_read"], ["price_history", "volume_history"])


class TheStageThreeVectorNamesTheInputItNeverRead(unittest.TestCase):
    def test_the_same_answer_comes_back_with_and_without_volume(self) -> None:
        # If the block read volume, removing it would change something. It does not, so the
        # claim's volume half is named as evidence this reading never consumes -- in both
        # histories -- rather than appearing as missing in one of them.
        index = pd.bdate_range(end=AS_OF, periods=224)
        close = pd.Series([100.0] * 224, index=index, dtype=float)
        columns = {"Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close}
        measured = []
        for volume in (True, False):
            frame = pd.DataFrame({**columns, **({"Volume": np.full(224, 1_000_000)} if volume else {})}, index=index)
            snapshot = rows_snapshot(frame, provider="fixture-prices", retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc), as_of=date.fromisoformat(AS_OF), coverage={"completed_only": True})
            payload = execute(
                "ticker.risk",
                {"ticker": "TEST", "mode": "active", "as_of": AS_OF, "entry_price": 100.0, "entry_date": index[200].date().isoformat(), "stop_price": 90.0},
                runtime=Runtime(price_history=lambda ticker, as_of, snapshot=snapshot: snapshot),
            )
            block = payload["data"]["management_evidence"]["stage3_transition"]
            self.assertEqual(block["claim_inputs_not_read"], ["volume_history"])
            self.assertNotIn("missing_inputs", block)
            measured.append((block["volatility_ratio"], block["sma200_slope_pct"]))

        self.assertEqual(measured[0], measured[1])

    def test_a_history_without_volume_says_so_beside_the_claim(self) -> None:
        index = pd.bdate_range(end=AS_OF, periods=224)
        close = pd.Series([100.0] * 224, index=index, dtype=float)
        frame = pd.DataFrame({"Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close}, index=index)
        snapshot = rows_snapshot(frame, provider="fixture-prices", retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc), as_of=date.fromisoformat(AS_OF), coverage={"completed_only": True})
        payload = execute(
            "ticker.risk",
            {"ticker": "TEST", "mode": "active", "as_of": AS_OF, "entry_price": 100.0, "entry_date": index[200].date().isoformat(), "stop_price": 90.0},
            runtime=Runtime(price_history=lambda ticker, as_of: snapshot),
        )

        # The claim describes a price break on heavy volume and lists volume among its
        # required inputs. Neither measurement here reads it, so the block reports what it
        # measured and names the half it never had.
        block = payload["data"]["management_evidence"]["stage3_transition"]
        self.assertEqual(block["claim_inputs_not_read"], ["volume_history"])
        self.assertEqual(block["doctrine_id"], "stage.stage3_characteristics")


if __name__ == "__main__":
    unittest.main()
