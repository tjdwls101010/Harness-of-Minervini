"""Behavior checks for setup chart approval envelope."""

from __future__ import annotations

from tests.providers import rows_snapshot
from datetime import date, datetime, timezone
import tempfile
import unittest
from unittest import mock
import pandas as pd
from scripts.minervini.chart import render_chart_artifacts
from scripts.minervini.contracts import RequestError
from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import SnapshotMeta
from tests.series import base_series
from ._setup_envelope_fixtures import run, snapshot


class TheRenderersRefusalSurvivesToTheEnvelopeTests(unittest.TestCase):
    def test_history_the_renderer_will_not_draw_is_typed_unavailability(self) -> None:
        """An unhandled raise becomes internal_error, with the request and the as_of stripped.

        The renderer refuses unusable history by naming the reason, and naming it is the whole
        point -- a caller told only "internal error" cannot tell a data problem from a bug.
        """

        frame, _ = base_series()
        frame.index = [pd.NaT, *frame.index[1:]]
        meta = SnapshotMeta(provider="fixture-prices", retrieved_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
                            as_of=date(2026, 6, 25), coverage={"completed_only": True})
        runtime = Runtime(price_history=lambda ticker, requested: rows_snapshot(frame, provider="fixture-prices", retrieved_at=datetime(2026, 7, 1, tzinfo=timezone.utc), as_of=frame.index[-1].date(), coverage={"completed_only": True}))

        with tempfile.TemporaryDirectory() as directory:
            payload = execute("ticker.chart", {
                "ticker": "TEST", "as_of": "2026-06-25", "output_dir": directory, "no_cache": True,
            }, runtime=runtime)

        self.assertEqual(payload["status"], "unavailable")
        self.assertEqual(payload["as_of"]["date"], "2026-06-25")
        self.assertEqual(payload["request"]["ticker"], "TEST")
        self.assertIn("history_index_is_not_dates", payload["missing"][0]["reason"])

    def test_a_defect_in_the_renderer_is_not_dressed_up_as_missing_data(self) -> None:
        """Catching every ValueError would report a bug, and a malformed request, as absent bars.

        The refusal has its own type for that reason: a caller who is told the provider returned
        nothing goes looking at the provider.
        """

        frame, _ = base_series()
        meta = SnapshotMeta(provider="fixture-prices", retrieved_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
                            as_of=frame.index[-1].date(), coverage={"completed_only": True})
        runtime = Runtime(price_history=lambda ticker, requested: rows_snapshot(frame, provider="fixture-prices", retrieved_at=datetime(2026, 7, 1, tzinfo=timezone.utc), as_of=frame.index[-1].date(), coverage={"completed_only": True}))

        with mock.patch("scripts.minervini.chart._render_png", side_effect=ValueError("boom")):
            with tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(ValueError):
                    execute("ticker.chart", {
                        "ticker": "TEST", "as_of": frame.index[-1].date().isoformat(),
                        "output_dir": directory, "no_cache": True,
                    }, runtime=runtime)


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
