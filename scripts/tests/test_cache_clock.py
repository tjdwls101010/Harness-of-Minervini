#!/usr/bin/env python3
"""Deterministic contract tests for the shared live-source cache and NYSE clock."""

import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock
from zoneinfo import ZoneInfo

import pandas as pd


MODULES = Path(__file__).resolve().parents[1] / "modules"
sys.path.insert(0, str(MODULES))

import market_clock
import utils


ET = ZoneInfo("America/New_York")
KST = ZoneInfo("Asia/Seoul")


def _state(session="2026-07-09", market_open=False):
	return {
		"now_local": "2026-07-11T00:00:00+09:00",
		"now_et": "2026-07-10T11:00:00-04:00",
		"market_open": market_open,
		"session": "regular" if market_open else "closed",
		"last_completed_session": session,
		"cache_entries": 0,
	}


class CacheContractTests(unittest.TestCase):
	def setUp(self):
		self.temporary = tempfile.TemporaryDirectory()
		self.environment = mock.patch.dict(
			os.environ,
			{"MINERVINI_CACHE_DIR": self.temporary.name},
			clear=False,
		)
		self.environment.start()
		self.original_disabled = utils._CACHE_DISABLED
		utils._CACHE_DISABLED = False
		utils.cache_metadata(reset=True)

	def tearDown(self):
		utils._CACHE_DISABLED = self.original_disabled
		utils.cache_metadata(reset=True)
		self.environment.stop()
		self.temporary.cleanup()

	def test_json_normalization_never_emits_nonfinite_literals(self):
		payload = utils.normalize({"nan": float("nan"), "positive": float("inf"), "negative": float("-inf")})
		self.assertEqual(payload, {"nan": None, "positive": None, "negative": None})
		self.assertNotIn("Infinity", json.dumps(payload, allow_nan=False))

	def test_key_canonicalizes_symbol_and_params_but_separates_source_function_and_session(self):
		calls = []

		def fetch(label):
			calls.append(label)
			return label

		with mock.patch.object(market_clock, "get_market_state", return_value=_state()):
			first = utils.cached_call(
				"finviz",
				"us-market",
				"homepage",
				{"url": "https://finviz.com/", "headers": {"b": 2, "a": 1}},
				lambda: fetch("finviz"),
			)
			second = utils.cached_call(
				"finviz",
				"US-MARKET",
				"homepage",
				{"headers": {"a": 1, "b": 2}, "url": "https://finviz.com/"},
				lambda: fetch("duplicate"),
			)
			backend = utils.cached_call(
				"ibd-rs-rating",
				"AAPL",
				"get",
				{"ticker": "AAPL"},
				lambda: fetch("ibd"),
			)
			other_function = utils.cached_call(
				"ibd-rs-rating",
				"AAPL",
				"history",
				{"ticker": "AAPL"},
				lambda: fetch("history"),
			)
		with mock.patch.object(market_clock, "get_market_state", return_value=_state("2026-07-10")):
			other_session = utils.cached_call(
				"ibd-rs-rating",
				"AAPL",
				"get",
				{"ticker": "AAPL"},
				lambda: fetch("next-session"),
			)

		self.assertEqual((first, second), ("finviz", "finviz"))
		self.assertEqual((backend, other_function, other_session), ("ibd", "history", "next-session"))
		self.assertEqual(calls, ["finviz", "ibd", "history", "next-session"])
		self.assertEqual(utils.cache_entry_count(), 4)

	def test_dataframe_series_and_nested_market_types_round_trip(self):
		index = pd.MultiIndex.from_tuples(
			[("AAPL", pd.Timestamp("2026-07-09", tz=ET)), ("MSFT", pd.Timestamp("2026-07-10", tz=ET))],
			names=["symbol", "date"],
		)
		columns = pd.MultiIndex.from_tuples(
			[("price", "Close"), ("trade", "Volume"), ("flag", "eligible")],
			names=["group", "field"],
		)
		frame = pd.DataFrame(
			[[210.25, 1_000, True], [215.5, 2_000, False]],
			index=index,
			columns=columns,
		)
		frame[("trade", "Volume")] = frame[("trade", "Volume")].astype("Int64")
		frame.attrs["as_of"] = pd.Timestamp("2026-07-10T16:00:00", tz=ET)
		series = pd.Series([1.0, pd.NA], index=pd.RangeIndex(2, name="row"), dtype="Float64", name="rs")
		payload = {
			"frame": frame,
			"series": series,
			("tuple", 1): {
				"date": dt.date(2026, 7, 10),
				"datetime": dt.datetime(2026, 7, 10, 16, tzinfo=ET),
				"delta": dt.timedelta(minutes=15),
				"bytes": b"cache",
				"path": Path("chart.png"),
				"special": [float("nan"), float("inf"), pd.NaT],
			},
		}

		with mock.patch.object(market_clock, "get_market_state", return_value=_state()):
			utils.cached_call("yfinance", "AAPL", "history", {}, lambda: payload, price_endpoint=True)
			decoded = utils.cached_call("yfinance", "AAPL", "history", {}, lambda: self.fail("cache miss"), price_endpoint=True)

		pd.testing.assert_frame_equal(decoded["frame"], frame)
		pd.testing.assert_series_equal(decoded["series"], series)
		self.assertEqual(decoded[("tuple", 1)]["date"], dt.date(2026, 7, 10))
		self.assertEqual(decoded[("tuple", 1)]["datetime"], dt.datetime(2026, 7, 10, 16, tzinfo=ET))
		self.assertEqual(decoded[("tuple", 1)]["delta"], dt.timedelta(minutes=15))
		self.assertEqual(decoded[("tuple", 1)]["bytes"], b"cache")
		self.assertEqual(decoded[("tuple", 1)]["path"], Path("chart.png"))
		self.assertTrue(pd.isna(decoded[("tuple", 1)]["special"][0]))
		self.assertEqual(decoded[("tuple", 1)]["special"][1], float("inf"))
		self.assertIs(decoded[("tuple", 1)]["special"][2], pd.NaT)

	def test_open_market_price_ttl_is_fifteen_minutes_but_nonprice_is_session_lived(self):
		price_calls = []
		info_calls = []
		with (
			mock.patch.object(market_clock, "get_market_state", return_value=_state(market_open=True)),
			mock.patch.object(utils.time, "time", side_effect=[1_000.0, 1_899.0, 1_901.0, 1_901.0, 1_901.0, 99_999.0]),
		):
			first = utils.cached_call("yfinance", "AAPL", "history", {}, lambda: price_calls.append(1) or "p1", price_endpoint=True)
			within = utils.cached_call("yfinance", "AAPL", "history", {}, lambda: price_calls.append(2) or "p2", price_endpoint=True)
			expired = utils.cached_call("yfinance", "AAPL", "history", {}, lambda: price_calls.append(3) or "p3", price_endpoint=True)
			info_first = utils.cached_call("yfinance", "AAPL", "property:info", {}, lambda: info_calls.append(1) or "i1")
			info_late = utils.cached_call("yfinance", "AAPL", "property:info", {}, lambda: info_calls.append(2) or "i2")

		self.assertEqual((first, within, expired), ("p1", "p1", "p3"))
		self.assertEqual(price_calls, [1, 3])
		self.assertEqual((info_first, info_late), ("i1", "i1"))
		self.assertEqual(info_calls, [1])

	def test_no_cache_is_monotonic_and_never_reads_or_writes(self):
		utils.configure_cache(True)
		self.assertFalse(utils.configure_cache(False))
		calls = []
		with mock.patch.object(market_clock, "get_market_state", return_value=_state()):
			for _ in range(2):
				utils.cached_call("finviz", "US-MARKET", "homepage", {}, lambda: calls.append(1) or "live")
		self.assertEqual(calls, [1, 1])
		self.assertEqual(utils.cache_entry_count(), 0)
		metadata = utils.cache_metadata()
		self.assertEqual(metadata["counts"]["bypass"], 2)
		self.assertFalse(metadata["enabled"])

	def test_atomic_writer_never_exposes_partial_json_and_cleans_failed_temp(self):
		path = Path(self.temporary.name) / "entry.json"
		documents = [{"writer": value, "payload": "x" * 10_000} for value in range(8)]
		threads = [threading.Thread(target=utils._atomic_json_write, args=(path, document)) for document in documents]
		for thread in threads:
			thread.start()
		for thread in threads:
			thread.join()
		with path.open(encoding="utf-8") as handle:
			self.assertIn(json.load(handle), documents)
		self.assertEqual(list(Path(self.temporary.name).glob("*.tmp")), [])

		with mock.patch.object(utils.os, "replace", side_effect=OSError("replace failed")):
			with self.assertRaises(OSError):
				utils._atomic_json_write(path, {"writer": "failed"})
		self.assertEqual(list(Path(self.temporary.name).glob("*.tmp")), [])

	def test_yfinance_proxy_caches_methods_and_properties_transparently(self):
		class FakeFastInfo(dict):
			def __init__(self):
				super().__init__({"lastPrice": 123.0})
				self.last_price = 123.0

		class FakeTicker:
			def __init__(self, ticker, *args, **kwargs):
				self.ticker = ticker
				self.info_calls = 0
				self.history_calls = 0
				self.fast_info_calls = 0

			@property
			def info(self):
				self.info_calls += 1
				return {"symbol": self.ticker, "call": self.info_calls}

			@property
			def fast_info(self):
				self.fast_info_calls += 1
				return FakeFastInfo()

			def get_fast_info(self):
				self.fast_info_calls += 1
				return FakeFastInfo()

			def history(self, **kwargs):
				self.history_calls += 1
				return pd.DataFrame({"Close": [100.0]}, index=pd.DatetimeIndex(["2026-07-09"]))

		with (
			mock.patch.object(utils, "_ORIGINAL_YFINANCE_TICKER", FakeTicker),
			mock.patch.object(market_clock, "get_market_state", return_value=_state()),
		):
			ticker = utils.CachedTicker("aapl")
			self.assertEqual(ticker.info, ticker.info)
			pd.testing.assert_frame_equal(ticker.history(period="1y"), ticker.history(period="1y"))
			self.assertEqual(ticker.fast_info.last_price, ticker.fast_info.last_price)
			self.assertEqual(ticker.get_fast_info().last_price, ticker.get_fast_info().last_price)
			self.assertEqual(ticker._ticker.info_calls, 1)
			self.assertEqual(ticker._ticker.history_calls, 1)
			self.assertEqual(ticker._ticker.fast_info_calls, 2)


class MarketClockContractTests(unittest.TestCase):
	def test_kst_midnight_uses_et_session_not_local_calendar_date(self):
		state = market_clock.get_market_state(dt.datetime(2026, 7, 11, 0, 0, tzinfo=KST))
		self.assertEqual(state["now_et"][:19], "2026-07-10T11:00:00")
		self.assertEqual(state["session"], "regular")
		self.assertEqual(state["last_completed_session"], "2026-07-09")

	def test_close_rolls_session_date_and_weekend_rolls_back(self):
		at_close = market_clock.get_market_state(dt.datetime(2026, 7, 10, 16, 0, tzinfo=ET))
		on_weekend = market_clock.get_market_state(dt.datetime(2026, 7, 12, 12, 0, tzinfo=ET))
		self.assertEqual(at_close["session"], "after")
		self.assertEqual(at_close["last_completed_session"], "2026-07-10")
		self.assertEqual(on_weekend["session"], "closed")
		self.assertEqual(on_weekend["last_completed_session"], "2026-07-10")

	def test_major_holidays_new_year_exception_and_early_close(self):
		self.assertFalse(market_clock.is_trading_day(dt.date(2026, 4, 3)))  # Good Friday
		self.assertFalse(market_clock.is_trading_day(dt.date(2026, 7, 3)))  # July 4 observed
		self.assertTrue(market_clock.is_trading_day(dt.date(2021, 12, 31)))  # Saturday New Year is not Friday-observed
		self.assertTrue(market_clock.is_early_close(dt.date(2025, 7, 3)))
		self.assertTrue(market_clock.is_early_close(dt.date(2026, 11, 27)))
		state = market_clock.get_market_state(dt.datetime(2025, 7, 3, 13, 0, tzinfo=ET))
		self.assertEqual(state["session"], "after")
		self.assertEqual(state["last_completed_session"], "2025-07-03")

	def test_help_is_offline_and_contract_is_valid_json(self):
		script = MODULES / "market_clock.py"
		help_result = subprocess.run(
			[sys.executable, str(script), "--help"],
			cwd=Path(__file__).resolve().parents[2],
			text=True,
			capture_output=True,
			check=False,
			timeout=10,
		)
		self.assertEqual(help_result.returncode, 0, help_result.stderr)
		self.assertIn("--no-cache", help_result.stdout)
		result = subprocess.run(
			[sys.executable, str(script), "--no-cache"],
			cwd=Path(__file__).resolve().parents[2],
			text=True,
			capture_output=True,
			check=False,
			timeout=10,
		)
		self.assertEqual(result.returncode, 0, result.stderr)
		payload = json.loads(result.stdout)
		self.assertEqual(
			set(payload),
			{"now_local", "now_et", "market_open", "session", "last_completed_session", "cache_entries"},
		)


if __name__ == "__main__":
	unittest.main()
