"""The setup envelope: measurements in the verdict, contrast beside it.

`signals` is what the verdict was built from. A caller reading it -- or a later reducer
composing several capabilities -- must be able to trust that everything in it counted.
Contrast evidence is real and worth printing, and it belongs in the payload rather than in
that list, because its state words mean something no verdict vocabulary contains.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import unittest

from scripts.minervini.contracts import RequestError
from scripts.minervini.cli import format_payload
from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot, SnapshotMeta
from tests.series import anchor_dates, base_series


def snapshot(**kwargs) -> tuple[ProviderSnapshot, list[str]]:
    frame, anchors = base_series(**kwargs)
    meta = SnapshotMeta(
        provider="fixture-prices",
        retrieved_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        as_of=frame.index[-1].date(),
        coverage={"completed_only": True},
    )
    return ProviderSnapshot(frame, meta), anchor_dates(frame, anchors)


def run(*, swings=None, as_of=None, **kwargs) -> dict:
    prices, chain = snapshot(**kwargs)
    runtime = Runtime(price_history=lambda ticker, requested: prices)
    request = {
        "ticker": "TEST",
        "as_of": as_of or prices.meta.as_of.isoformat(),
        "swing": chain if swings is None else swings,
        "right_side_development": "constructive",
        "chain_completeness": "complete",
        "entry_proximity": "at_pivot",
        "entry_price": float(prices.data["Close"].iloc[-1]),
        "no_cache": True,
    }
    return execute("ticker.setup", request, runtime=runtime)


class EnvelopeTests(unittest.TestCase):
    def test_a_fully_read_setup_corroborated_by_the_harnesss_own_segmentation_is_ready(self) -> None:
        payload = run()

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["data"]["setup_state"], "ready")
        self.assertEqual(payload["data"]["measurements"]["contraction_count"], 3)
        self.assertEqual(payload["data"]["segmentation"]["state"], "resolved")

    def test_no_signal_in_the_envelope_carries_a_state_or_a_flag_the_verdict_must_ignore(self) -> None:
        """Not that every signal was required -- most report -- but that none of them is contrast."""

        payload = run()

        for signal in payload["signals"]:
            with self.subTest(signal=signal["id"]):
                self.assertNotIn(signal["state"], {"contrast_pass", "contrast_fail"})
                self.assertIsNot(signal.get("binds"), False)

    def test_contrast_evidence_rides_in_the_payload_and_names_whose_standard_it_is(self) -> None:
        payload = run()

        attributed = {item.get("attributed_to") for item in payload["data"]["contrast"]}
        self.assertTrue({"Ryan", "Zanger"}.issubset(attributed), attributed)
        self.assertNotIn("contrast", {signal["id"] for signal in payload["signals"]})

    def test_the_doctrine_ids_are_the_claims_the_signals_actually_cite(self) -> None:
        payload = run()

        self.assertIn("setup.demand_supply_volume_asymmetry", payload["doctrine_ids"])
        self.assertNotIn("setup.vcp_supply_contraction", payload["doctrine_ids"])

    def test_a_base_nobody_declared_is_needs_input_rather_than_an_unobjectionable_pass(self) -> None:
        payload = run(swings=[])

        self.assertEqual(payload["status"], "needs_input")
        self.assertEqual(payload["data"]["setup_state"], "incomplete")
        self.assertIn("base_structure", {item["id"] for item in payload["missing"]})

    def test_a_chain_the_bars_contradict_is_needs_input_with_the_offending_date(self) -> None:
        prices, chain = snapshot()
        broken = list(chain)
        broken[1] = "2026-04-07"

        runtime = Runtime(price_history=lambda ticker, requested: prices)
        payload = execute(
            "ticker.setup",
            {"ticker": "TEST", "as_of": prices.meta.as_of.isoformat(), "swing": broken, "no_cache": True},
            runtime=runtime,
        )

        self.assertEqual(payload["status"], "needs_input")
        self.assertTrue(any("2026-04-07" in problem for problem in payload["data"]["structure"]["problems"]))

    def test_a_distributing_base_is_avoid_and_names_the_gate_it_failed(self) -> None:
        payload = run(volume_profile="distribution")

        self.assertEqual(payload["data"]["setup_state"], "avoid")
        self.assertIn("setup.demand_supply_volume_asymmetry", payload["data"]["failed"])

    def test_a_swing_list_that_is_not_a_list_is_a_request_error(self) -> None:
        prices, _ = snapshot()
        runtime = Runtime(price_history=lambda ticker, requested: prices)

        with self.assertRaises(RequestError):
            execute(
                "ticker.setup",
                {"ticker": "TEST", "as_of": prices.meta.as_of.isoformat(), "swing": "2026-04-06", "no_cache": True},
                runtime=runtime,
            )




class DeclaredReadingsAreVisibleTests(unittest.TestCase):
    def test_the_envelope_says_which_evidence_came_from_a_person_rather_than_the_bars(self) -> None:
        """Three of the required conditions are readings, and a reader should see that.

        Everything else in the verdict is measured and cannot be declared away. These three
        cover only what completed bars genuinely cannot settle, so the honest thing is to
        name them rather than let them blend into the measurements beside them.
        """

        payload = run()

        declared = payload["data"]["declared_readings"]
        self.assertEqual(
            declared,
            {"right_side_development": "constructive", "chain_completeness": "complete", "entry_proximity": "at_pivot"},
        )

    def test_a_setup_with_no_readings_names_the_three_it_is_waiting_on(self) -> None:
        prices, chain = snapshot()
        runtime = Runtime(price_history=lambda ticker, requested: prices)

        payload = execute(
            "ticker.setup",
            {"ticker": "TEST", "as_of": prices.meta.as_of.isoformat(), "swing": chain, "no_cache": True},
            runtime=runtime,
        )

        self.assertEqual(payload["data"]["declared_readings"], {})
        missing = {item["id"] for item in payload["missing"]}
        self.assertTrue({"setup.time_compression_hazard", "setup.declared_chain_completeness", "setup.chase_limit_above_pivot"}.issubset(missing))




class CompactFormatTests(unittest.TestCase):
    def test_compact_drops_the_measurement_detail_and_keeps_every_decision_surface(self) -> None:
        """Compact changes detail, never meaning: the signals carry the values that decided."""

        prices, chain = snapshot()
        runtime = Runtime(price_history=lambda ticker, requested: prices)
        request = {
            "ticker": "TEST",
            "as_of": prices.meta.as_of.isoformat(),
            "swing": chain,
            "right_side_development": "constructive",
            "chain_completeness": "complete",
            "entry_proximity": "at_pivot",
        "entry_price": float(prices.data["Close"].iloc[-1]),
            "no_cache": True,
        }

        full = execute("ticker.setup", request, runtime=runtime)
        compact = format_payload(execute("ticker.setup", request, runtime=runtime), "compact")

        self.assertEqual(compact["data"]["setup_state"], full["data"]["setup_state"])
        self.assertEqual(compact["signals"], full["signals"])
        self.assertEqual(compact["missing"], full["missing"])
        self.assertNotIn("measurements", compact["data"])
        self.assertIn("problems", compact["data"]["structure"])


if __name__ == "__main__":
    unittest.main()
