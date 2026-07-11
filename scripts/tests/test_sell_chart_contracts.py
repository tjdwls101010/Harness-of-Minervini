#!/usr/bin/env python3
"""Deterministic contract tests for sell signals and chart corroboration."""

import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import numpy as np
import pandas as pd


MODULES = Path(__file__).resolve().parents[1] / "modules"
sys.path.insert(0, str(MODULES))

import chart_render
import sell_signals


def daily_history(periods=320):
    index = pd.bdate_range(end="2026-07-10", periods=periods, tz="America/New_York")
    close = pd.Series(np.linspace(80.0, 160.0, periods), index=index)
    return pd.DataFrame(
        {
            "Open": close - 0.25,
            "High": close + 1.0,
            "Low": close - 1.0,
            "Close": close,
            "Volume": np.linspace(1_000_000, 2_000_000, periods),
        },
        index=index,
    )


class CompletedBarContractTests(unittest.TestCase):
    def test_early_close_after_session_keeps_the_completed_daily_bar(self):
        frame = daily_history(5)
        after_early_close = {
            "now_et": "2026-07-10T13:30:00-04:00",
            "market_open": False,
        }
        for module in (sell_signals, chart_render):
            with self.subTest(module=module.__name__), mock.patch.object(
                module, "get_market_state", return_value=after_early_close
            ):
                self.assertEqual(len(module._completed_daily(frame)), len(frame))

    def test_regular_session_drops_the_partial_current_bar(self):
        frame = daily_history(5)
        regular = {
            "now_et": "2026-07-10T11:00:00-04:00",
            "market_open": True,
        }
        for module in (sell_signals, chart_render):
            with self.subTest(module=module.__name__), mock.patch.object(
                module, "get_market_state", return_value=regular
            ):
                self.assertEqual(len(module._completed_daily(frame)), len(frame) - 1)


class SellSignalContractTests(unittest.TestCase):
    def test_extension_never_invents_base_top(self):
        result = sell_signals._extension_snapshot(daily_history(), base_top=None)
        self.assertEqual(result["base_top_extension"]["status"], "needs_input")
        self.assertIsNone(result["base_top_extension"]["pct_above"])
        self.assertEqual(result["base_top_extension"]["zone_pct"], [20.0, 25.0])

    def test_climax_measure_reuses_stage_analysis_owner(self):
        result = sell_signals._climax_snapshot(daily_history())
        self.assertEqual(result["owner"], "stage_analysis.compute_risk_snapshot")
        self.assertEqual(result["origin"], "[M]")
        self.assertIn("heuristic_climactic", result)

    def test_reversal_counts_only_determinate_items(self):
        data = daily_history()
        items, _ = sell_signals._reversal_items(data)
        by_id = {item["id"]: item for item in items}
        self.assertEqual(len(items), 6)
        self.assertEqual(by_id[3]["status"], "needs_chart")
        self.assertEqual(by_id[4]["status"], "needs_input")
        self.assertEqual(by_id[5]["status"], "needs_input")
        self.assertIn("Invented heuristic, not canonical", by_id[1]["caveat"])
        self.assertEqual(sum(item["determinate"] for item in items), 3)

    def test_trail_emits_each_violation_and_reclaim(self):
        index = pd.date_range("2026-01-02", periods=7, freq="B")
        view = pd.DataFrame({"Close": [101.0, 99.0, 98.0, 102.0, 97.0, 96.0, 95.0]}, index=index)
        ma = pd.Series(100.0, index=index)
        events, state = sell_signals._trail_events(view, ma)
        self.assertEqual(
            [event["type"] for event in events],
            [
                "first_close_below",
                "second_close_below_trigger",
                "reclaim_reset",
                "first_close_below",
                "second_close_below_trigger",
                "additional_close_below",
            ],
        )
        self.assertEqual(state["state"], "exit_triggered")
        self.assertEqual(state["last_trigger_date"], "2026-01-09")

    def test_cascade_is_ordered_and_prior_high_is_caller_anchored(self):
        index = pd.date_range("2026-01-02", periods=6, freq="B")
        close = pd.Series([110.0, 108.0, 99.0, 90.0, 95.0, 80.0], index=index)
        data = pd.DataFrame(
            {
                "Open": close,
                "High": [111.0, 109.0, 100.0, 94.0, 101.0, 96.0],
                "Low": [109.0, 107.0, 98.0, 89.0, 94.0, 79.0],
                "Close": close,
                "Volume": [1_000_000] * 6,
            },
            index=index,
        )
        with (
            mock.patch.object(sell_signals, "_ema", return_value=pd.Series(100.0, index=index)),
            mock.patch.object(sell_signals, "_sma", side_effect=[pd.Series(95.0, index=index), pd.Series(85.0, index=index)]),
        ):
            stages, events, current = sell_signals._cascade_snapshot(data, prior_high=100.0, tolerance_pct=5.0)
        self.assertEqual([stage["status"] for stage in stages], ["observed", "observed", "observed", "observed"])
        self.assertEqual([event["stage"] for event in events], [1, 2, 3, 4])
        self.assertEqual(stages[2]["evidence"]["method"], "caller_controlled_noncanonical")
        self.assertEqual(current, "200s_terminal")

    def test_cascade_cannot_skip_the_21ema_stage(self):
        index = pd.date_range("2026-01-02", periods=4, freq="B")
        close = pd.Series([110.0, 108.0, 99.0, 90.0], index=index)
        data = pd.DataFrame({"Open": close, "High": close + 1, "Low": close - 1, "Close": close, "Volume": 1}, index=index)
        with (
            mock.patch.object(sell_signals, "_ema", return_value=pd.Series(50.0, index=index)),
            mock.patch.object(sell_signals, "_sma", side_effect=[pd.Series(105.0, index=index), pd.Series(85.0, index=index)]),
        ):
            stages, events, current = sell_signals._cascade_snapshot(data)
        self.assertEqual([stage["status"] for stage in stages[:2]], ["not_observed", "not_observed"])
        self.assertEqual(events, [])
        self.assertEqual(current, "intact")

    def test_cascade_rejects_half_supplied_anchor_as_json(self):
        args = SimpleNamespace(
            no_cache=True,
            symbol="TEST",
            start=None,
            prior_high=100.0,
            prior_high_tolerance_pct=None,
            period="2y",
        )
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), self.assertRaises(SystemExit) as raised:
            sell_signals.cmd_cascade(args)
        self.assertEqual(raised.exception.code, 1)
        self.assertIn("must be supplied together", json.loads(stdout.getvalue())["error"])


class ChartRenderContractTests(unittest.TestCase):
    def test_daily_png_and_json_contract(self):
        data = daily_history()
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(chart_render, "_fetch_daily", return_value=data):
            output = Path(directory) / "daily.png"
            args = SimpleNamespace(
                no_cache=True,
                symbol="test",
                period="1mo",
                timeframe="daily",
                pivot=145.0,
                out=str(output),
            )
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                chart_render.cmd_render(args)
            result = json.loads(stdout.getvalue())
            self.assertEqual(result["moving_averages"], ["EMA10", "EMA21", "SMA50", "SMA150", "SMA200"])
            self.assertEqual(result["pivot_annotation"], {"status": "rendered", "value": 145.0})
            self.assertEqual(result["volume_overlay"]["bands_pct"], [-25.0, 25.0])
            self.assertGreater(result["png_bytes"], 0)
            self.assertEqual(output.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

    def test_weekly_overlays_never_include_200_week_average(self):
        weekly = chart_render._to_completed_weekly(daily_history(900))
        moving, _, _, _, volume_bars = chart_render._compute_overlays(weekly, "weekly")
        self.assertEqual(list(moving), ["SMA10W", "SMA30W", "SMA40W"])
        self.assertNotIn("SMA200W", moving)
        self.assertEqual(volume_bars, 10)

    def test_non_png_output_is_json_exit_one(self):
        data = daily_history()
        args = SimpleNamespace(no_cache=True, symbol="TEST", period="1mo", timeframe="daily", pivot=None, out="chart.jpg")
        stdout = io.StringIO()
        with mock.patch.object(chart_render, "_fetch_daily", return_value=data), contextlib.redirect_stdout(stdout), self.assertRaises(SystemExit) as raised:
            chart_render.cmd_render(args)
        self.assertEqual(raised.exception.code, 1)
        self.assertIn("--out must end in .png", json.loads(stdout.getvalue())["error"])


if __name__ == "__main__":
    unittest.main()
