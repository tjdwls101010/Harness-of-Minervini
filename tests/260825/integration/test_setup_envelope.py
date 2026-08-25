"""The setup envelope: measurements in the verdict, contrast beside it.

`signals` is what the verdict was built from. A caller reading it -- or a later reducer
composing several capabilities -- must be able to trust that everything in it counted.
Contrast evidence is real and worth printing, and it belongs in the payload rather than in
that list, because its state words mean something no verdict vocabulary contains.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import tempfile
import unittest

from scripts.minervini.chart import render_chart_artifacts
from scripts.minervini.contracts import RequestError
from scripts.minervini.cli import format_payload
from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot, ProviderUnavailable, SnapshotMeta
from scripts.minervini.setup_structure import bars_fingerprint
from tests.series import anchor_dates, base_series, distribution_only_in_the_tail_series


def snapshot(**kwargs) -> tuple[ProviderSnapshot, list[str]]:
    frame, anchors = base_series(**kwargs)
    meta = SnapshotMeta(
        provider="fixture-prices",
        retrieved_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        as_of=frame.index[-1].date(),
        coverage={"completed_only": True},
    )
    return ProviderSnapshot(frame, meta), anchor_dates(frame, anchors)


def run(*, swings=None, as_of=None, approved_bars=None, chain_completeness="complete", **kwargs) -> dict:
    completeness = chain_completeness
    prices, chain = snapshot(**kwargs)
    runtime = Runtime(price_history=lambda ticker, requested: prices)
    request = {
        "ticker": "TEST",
        "as_of": as_of or prices.meta.as_of.isoformat(),
        "swing": chain if swings is None else swings,
        "right_side_development": "constructive",
        "chain_completeness": completeness,
        "approved_bars": approved_bars or bars_fingerprint(prices.data),
        "entry_proximity": "at_pivot",
        "entry_price": float(prices.data["Close"].iloc[-1]),
        "no_cache": True,
    }
    return execute("ticker.setup", request, runtime=runtime)


class AGapTheEngineKnowsAboutOutranksTheCallersTests(unittest.TestCase):
    def test_a_caller_admitting_a_gap_does_not_cover_the_one_the_detector_found(self) -> None:
        """Two different absences, and the caller's answered first.

        Declaring the chain partial returned `fail` -- a verdict about the reading -- and with a
        verdict there the envelope came back ok, wait, and pointing at ticker.risk, with the
        segmentation the detector refused to vouch for nowhere in it.
        """

        payload = run(daily_range_pct=0.5, hidden_bounce=True, chain_completeness="partial")

        self.assertEqual(payload["data"]["segmentation"]["state"], "unstable")
        self.assertEqual(payload["data"]["setup_state"], "incomplete")
        reasons = {item["id"]: item["reason"] for item in payload["missing"]}
        self.assertEqual(reasons.get("setup.declared_chain_completeness"), "segmentation_unstable")
        # Outranking the caller's admission is not the same as losing it: the signal that took
        # precedence carries the reading it took precedence over.
        completeness = next(item for item in payload["signals"] if item["id"] == "setup.declared_chain_completeness")
        self.assertEqual(completeness["measured"]["reading"], "partial")


class RefusedBeforeAnythingIsFetchedTests(unittest.TestCase):
    def test_a_request_no_history_could_rescue_never_reaches_the_provider(self) -> None:
        """Validating after the fetch reports the caller's fault as a provider outage.

        It also pays for a fetch whose result cannot be used, and on a provider that happens to
        be down the caller is told to retry something that was never going to work.
        """

        calls = []

        def provider(ticker, requested):
            calls.append(ticker)
            raise ProviderUnavailable("down")

        runtime = Runtime(price_history=provider)

        with self.assertRaises(RequestError) as raised:
            execute("ticker.setup", {
                "ticker": "TEST", "as_of": "2026-06-25", "swing": [],
                "chain_completeness": "complete", "no_cache": True,
            }, runtime=runtime)

        self.assertEqual(raised.exception.field, "approved_bars")
        self.assertEqual(calls, [])

    def test_every_shape_the_request_can_fail_on_is_checked_there_too(self) -> None:
        """One field moved ahead of the fetch and the rest stayed behind it."""

        calls = []

        def provider(ticker, requested):
            calls.append(ticker)
            raise ProviderUnavailable("down")

        runtime = Runtime(price_history=provider)

        with self.assertRaises(RequestError) as raised:
            execute("ticker.setup", {
                "ticker": "TEST", "as_of": "2026-06-25", "swing": "not-a-list", "no_cache": True,
            }, runtime=runtime)

        self.assertEqual(raised.exception.field, "swing")
        self.assertEqual(calls, [])


class AVerdictIsAboutTheBaseOrItIsNotAVerdictTests(unittest.TestCase):
    def test_a_gate_failing_on_a_chain_the_detector_did_not_produce_is_not_avoid(self) -> None:
        """The measurement was of another span, so what it found is not about this stock.

        The uncorroborated rule was applied only where the segmentation itself was unstable, so
        a declared chain the detector had rejected still published its hard-gate failure: an
        up/down volume ratio read off the last five anchors, where the base's own passed.
        """

        frame, whole, suffix = distribution_only_in_the_tail_series()
        meta = SnapshotMeta(provider="fixture-prices", retrieved_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
                            as_of=frame.index[-1].date(), coverage={"completed_only": True})
        prices = ProviderSnapshot(frame, meta)
        runtime = Runtime(price_history=lambda ticker, requested: prices)

        def run_with(chain):
            return execute("ticker.setup", {
                "ticker": "TEST", "as_of": prices.meta.as_of.isoformat(), "swing": chain,
                "right_side_development": "constructive", "chain_completeness": "complete",
                "approved_bars": bars_fingerprint(frame), "entry_proximity": "at_pivot",
                "no_cache": True,
            }, runtime=runtime)

        honest, misdeclared = run_with(whole), run_with(suffix)

        self.assertEqual(honest["data"]["setup_state"], "ready")
        self.assertEqual(misdeclared["data"]["setup_state"], "incomplete")
        self.assertEqual(misdeclared["data"]["uncorroborated_verdict"], "avoid")
        reasons = {item["id"]: item["reason"] for item in misdeclared["missing"]}
        self.assertEqual(reasons.get("setup.declared_chain_completeness"), "declared_chain_is_not_the_detected_one")
        # The caller can act on this one -- declare the chain ticker.swings proposed.
        self.assertEqual(misdeclared["status"], "needs_input")
        # And the machine channel carries nothing a reducer could read as a finding: the gate
        # that failed was measured off the wrong span, so only the signal explaining why
        # anything counts is published there. The evidence itself stays in the payload.
        published = {item["id"] for item in misdeclared["signals"]}
        self.assertEqual(published, {"setup.declared_chain_completeness"})
        self.assertIn(
            "setup.demand_supply_volume_asymmetry",
            {item["id"] for item in misdeclared["data"]["signals"]},
        )


class AnUnfixableGapIsNotAskedAboutTests(unittest.TestCase):
    def test_it_outranks_a_verdict_read_off_the_chain_nothing_vouched_for(self) -> None:
        """A hard gate failing on an uncorroborated chain is still uncorroborated.

        Letting the reducer's own state decide first returned ok, AVOID, and a pointer at
        ticker.risk over a data-integrity gap the engine already knew about.
        """

        payload = run(daily_range_pct=0.5, hidden_bounce=True, volume_profile="distribution")

        self.assertEqual(payload["data"]["segmentation"]["state"], "unstable")
        self.assertEqual(payload["status"], "unavailable")
        self.assertEqual(payload["next_capabilities"], [])
        # And the verdict itself, not only the status around it: leaving AVOID in the payload
        # published a finding about the stock that rested on a chain nothing vouched for.
        self.assertEqual(payload["data"]["setup_state"], "incomplete")
        self.assertEqual(payload["data"]["uncorroborated_verdict"], "avoid")

    def test_a_segmentation_nothing_will_vouch_for_stops_the_route_rather_than_routing_on(self) -> None:
        """The same gap, answered two different ways by two capabilities.

        ticker.swings says unavailable and offers no next step, because the parameters are out
        of the caller's reach and the chart draws no anchors for a chain the detector refuses.
        The setup was sending them to that chart anyway, on a needs_input that named nothing
        they could supply.
        """

        payload = run(daily_range_pct=0.5, hidden_bounce=True)

        self.assertEqual(payload["data"]["segmentation"]["state"], "unstable")
        self.assertEqual(payload["status"], "unavailable")
        self.assertEqual(payload["next_capabilities"], [])


class TheApprovalNamesItsOwnBarsTests(unittest.TestCase):
    """A chart reading is a reading of a particular picture, and pictures go stale."""

    def test_declaring_a_reading_requires_saying_which_bars_it_was_read_from(self) -> None:
        prices, chain = snapshot()
        runtime = Runtime(price_history=lambda ticker, requested: prices)

        with self.assertRaises(RequestError) as raised:
            execute("ticker.setup", {
                "ticker": "TEST", "as_of": prices.meta.as_of.isoformat(), "swing": chain,
                "chain_completeness": "complete", "no_cache": True,
            }, runtime=runtime)

        self.assertEqual(raised.exception.field, "approved_bars")

    def test_admitting_a_gap_costs_nothing_including_naming_the_bars(self) -> None:
        """The fingerprint gates a reading that would otherwise have counted, and partial is not
        one: it fails on its own terms whichever vintage it was read from."""

        prices, chain = snapshot()
        runtime = Runtime(price_history=lambda ticker, requested: prices)

        payload = execute("ticker.setup", {
            "ticker": "TEST", "as_of": prices.meta.as_of.isoformat(), "swing": chain,
            "chain_completeness": "partial", "no_cache": True,
        }, runtime=runtime)

        self.assertEqual(payload["data"]["declared_readings"]["chain_completeness"], "partial")
        self.assertNotEqual(payload["data"]["setup_state"], "ready")

    def test_a_reading_that_asks_for_the_chart_is_not_an_approval_of_other_bars(self) -> None:
        """`needs_chart` names a reader who has not looked yet, not one who looked elsewhere."""

        prices, chain = snapshot()
        runtime = Runtime(price_history=lambda ticker, requested: prices)

        payload = execute("ticker.setup", {
            "ticker": "TEST", "as_of": prices.meta.as_of.isoformat(), "swing": chain,
            "chain_completeness": "needs_chart", "no_cache": True,
        }, runtime=runtime)

        reasons = {item["id"]: item["reason"] for item in payload["missing"]}
        self.assertEqual(reasons.get("setup.declared_chain_completeness"), "evidence_required")

    def test_an_approval_of_other_bars_does_not_carry_over_to_these(self) -> None:
        """Same dates, different prices, and the reading was of the other picture.

        Comparing only the anchor dates let a chain approved from one vintage of the series
        vouch for a different one: every date matched while the pivot, the depths and the base
        the reader actually looked at had all moved.
        """

        payload = run(approved_bars="0" * 64)

        reasons = {item["id"]: item["reason"] for item in payload["missing"]}
        self.assertEqual(reasons.get("setup.declared_chain_completeness"), "approval_covers_different_bars")
        self.assertEqual(payload["data"]["setup_state"], "incomplete")

    def test_the_current_fingerprint_travels_back_so_the_reader_can_re_approve(self) -> None:
        payload = run(approved_bars="0" * 64)

        self.assertEqual(len(payload["data"]["segmentation"]["bars_fingerprint"]), 64)


class TheChartIsWhereTheApprovalComesFromTests(unittest.TestCase):
    """The fingerprint is only worth carrying if the path a person walks actually uses it."""

    def test_a_chain_approved_off_the_rendered_chart_is_the_one_setup_accepts(self) -> None:
        prices, chain = snapshot()
        runtime = Runtime(price_history=lambda ticker, requested: prices)

        with tempfile.TemporaryDirectory() as directory:
            manifest = render_chart_artifacts(
                prices.data, ticker="TEST", as_of=prices.meta.as_of, output_dir=directory
            )

        payload = execute("ticker.setup", {
            "ticker": "TEST", "as_of": prices.meta.as_of.isoformat(), "swing": chain,
            "right_side_development": "constructive", "chain_completeness": "complete",
            "approved_bars": manifest["input_sha256"], "entry_proximity": "at_pivot",
            "no_cache": True,
        }, runtime=runtime)

        self.assertEqual([anchor["date"] for anchor in manifest["segmentation"]["anchors"]], chain)
        self.assertEqual(payload["data"]["setup_state"], "ready")


class WhatDecidedItIsNamedTests(unittest.TestCase):
    """`doctrine_ids` is where a reader finds the sentences a verdict rests on."""

    def test_the_segmentation_convention_is_named_because_it_decided_the_chain(self) -> None:
        """The detector's own rules answered a required condition, so they are cited.

        Deriving the list from the signals alone left the one convention that is the harness's
        rather than the source's out of the answer -- the reader could see that completeness
        passed and not what the chain it passed against was produced by.
        """

        payload = run()

        self.assertIn("setup.swing_segmentation_convention", payload["doctrine_ids"])

    def test_a_chain_nothing_will_vouch_for_says_so_rather_than_asking_for_a_reading(self) -> None:
        """Two different absences reached the caller under one word.

        A completeness reading nobody declared is fixed by declaring one. A completeness
        reading the detector refuses to corroborate is not fixed by anything the caller types,
        and telling them "evidence required" sends them to look for an argument.
        """

        payload = run(daily_range_pct=0.5, hidden_bounce=True)

        self.assertEqual(payload["data"]["segmentation"]["state"], "unstable")
        reasons = {item["id"]: item["reason"] for item in payload["missing"]}
        self.assertEqual(reasons.get("setup.declared_chain_completeness"), "segmentation_unstable")


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
            "approved_bars": bars_fingerprint(prices.data),
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
