"""Shared JSON, cache, and yfinance utilities for market-data scripts."""

import argparse
import base64
import datetime
import functools
import hashlib
import inspect
import json
import math
import os
import sys
import tempfile
import threading
import time
from collections.abc import Mapping
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd


CACHE_SCHEMA_VERSION = 2
OPEN_PRICE_TTL_SECONDS = 15 * 60
_CACHE_ENV_DISABLED = os.environ.get("MINERVINI_NO_CACHE", "").lower() in {"1", "true", "yes", "on"}
_CACHE_CLI_DISABLED = "--no-cache" in sys.argv[1:]
_CACHE_DISABLED = _CACHE_ENV_DISABLED or _CACHE_CLI_DISABLED
_CACHE_EVENTS = []
_CACHE_EVENTS_LOCK = threading.Lock()


def _consume_no_cache_flag():
	"""Observe, but do not remove, the global flag before a parser dispatches."""
	return _CACHE_CLI_DISABLED


_consume_no_cache_flag()


def configure_cache(no_cache: bool):
	"""Apply a process-wide cache bypass without ever re-enabling it later.

	A module may configure the shared layer more than once while dispatching a
	command.  Once any caller, the environment, or ``--no-cache`` requests a
	bypass, a later ``configure_cache(False)`` must not silently turn caching
	back on for another live source in the same process.
	"""
	global _CACHE_DISABLED
	_CACHE_DISABLED = _CACHE_DISABLED or _CACHE_ENV_DISABLED or _CACHE_CLI_DISABLED or bool(no_cache)
	return not _CACHE_DISABLED


def cache_disabled():
	"""Return whether process-wide cache bypass is active."""
	return _CACHE_DISABLED


def cache_dir():
	"""Return the user-scoped cache root without creating it."""
	return Path(os.environ.get("MINERVINI_CACHE_DIR", "~/.cache/minervini-harness")).expanduser()


def cache_entry_count():
	"""Count complete cache entries; temporary atomic-write files are excluded."""
	root = cache_dir()
	try:
		return sum(1 for path in root.iterdir() if path.is_file() and path.suffix == ".json")
	except (FileNotFoundError, NotADirectoryError, PermissionError):
		return 0


def _record_cache_event(event):
	with _CACHE_EVENTS_LOCK:
		_CACHE_EVENTS.append(event)


def cache_metadata(reset=False):
	"""Return process-local hit/miss/bypass evidence suitable for JSON output."""
	with _CACHE_EVENTS_LOCK:
		events = [dict(event) for event in _CACHE_EVENTS]
		if reset:
			_CACHE_EVENTS.clear()
	counts = {name: sum(event.get("status") == name for event in events) for name in ("hit", "miss", "bypass", "error")}
	return {
		"status": events[-1]["status"] if events else "unused",
		"enabled": not _CACHE_DISABLED,
		"counts": counts,
		"events": events[-50:],
	}


def _encode_axis(axis):
	if isinstance(axis, pd.MultiIndex):
		return {
			"kind": "multi",
			"values": [_encode_cache_value(tuple(item)) for item in axis.tolist()],
			"names": [_encode_cache_value(name) for name in axis.names],
		}
	if isinstance(axis, pd.RangeIndex):
		return {
			"kind": "range",
			"start": axis.start,
			"stop": axis.stop,
			"step": axis.step,
			"name": _encode_cache_value(axis.name),
		}
	if isinstance(axis, pd.DatetimeIndex):
		return {
			"kind": "datetime",
			"values": [_encode_cache_value(item) for item in axis.tolist()],
			"name": _encode_cache_value(axis.name),
			"freq": axis.freqstr,
		}
	if isinstance(axis, pd.TimedeltaIndex):
		return {
			"kind": "timedelta",
			"values": [_encode_cache_value(item) for item in axis.tolist()],
			"name": _encode_cache_value(axis.name),
			"freq": axis.freqstr,
		}
	return {
		"kind": "index",
		"values": [_encode_cache_value(item) for item in axis.tolist()],
		"name": _encode_cache_value(axis.name),
		"dtype": str(axis.dtype),
	}


def _decode_axis(value):
	kind = value["kind"]
	if kind == "range":
		return pd.RangeIndex(value["start"], value["stop"], value["step"], name=_decode_cache_value(value.get("name")))
	if kind == "multi":
		items = [tuple(_decode_cache_value(item)) for item in value["values"]]
		return pd.MultiIndex.from_tuples(items, names=[_decode_cache_value(name) for name in value["names"]])
	items = [_decode_cache_value(item) for item in value["values"]]
	name = _decode_cache_value(value.get("name"))
	if kind == "datetime":
		try:
			return pd.DatetimeIndex(items, name=name, freq=value.get("freq"))
		except ValueError:
			return pd.DatetimeIndex(items, name=name)
	if kind == "timedelta":
		try:
			return pd.TimedeltaIndex(items, name=name, freq=value.get("freq"))
		except ValueError:
			return pd.TimedeltaIndex(items, name=name)
	try:
		return pd.Index(items, name=name, dtype=value.get("dtype"), tupleize_cols=False)
	except (TypeError, ValueError):
		return pd.Index(items, name=name, tupleize_cols=False)


def _encode_cache_value(value):
	"""Encode market-data values into a reversible JSON tree or fail safely."""
	if value is pd.NA:
		return {"__type__": "pd_na"}
	if value is pd.NaT:
		return {"__type__": "pd_nat"}
	if value is None or isinstance(value, (str, int, bool)):
		return value
	if isinstance(value, float):
		if math.isnan(value):
			return {"__type__": "float", "value": "nan"}
		if math.isinf(value):
			return {"__type__": "float", "value": "inf" if value > 0 else "-inf"}
		return value
	if isinstance(value, pd.Timestamp):
		return {
			"__type__": "timestamp",
			"value": value.isoformat(),
			"timezone": getattr(value.tzinfo, "key", None) or getattr(value.tzinfo, "zone", None),
		}
	if isinstance(value, pd.Timedelta):
		return {"__type__": "pd_timedelta", "value": value.isoformat()}
	if isinstance(value, datetime.datetime):
		return {
			"__type__": "datetime",
			"value": value.isoformat(),
			"timezone": getattr(value.tzinfo, "key", None) or getattr(value.tzinfo, "zone", None),
		}
	if isinstance(value, datetime.date):
		return {"__type__": "date", "value": value.isoformat()}
	if isinstance(value, datetime.time):
		return {"__type__": "time", "value": value.isoformat()}
	if isinstance(value, datetime.timedelta):
		return {"__type__": "timedelta", "seconds": value.total_seconds()}
	if isinstance(value, Path):
		return {"__type__": "path", "value": os.fspath(value)}
	if isinstance(value, bytes):
		return {"__type__": "bytes", "value": base64.b64encode(value).decode("ascii")}
	if isinstance(value, pd.DataFrame):
		return {
			"__type__": "dataframe",
			"columns": _encode_axis(value.columns),
			"index": _encode_axis(value.index),
			"dtypes": [str(dtype) for dtype in value.dtypes],
			"attrs": _encode_cache_value(value.attrs),
			"data": [[_encode_cache_value(item) for item in row] for row in value.itertuples(index=False, name=None)],
		}
	if isinstance(value, pd.Series):
		return {
			"__type__": "series",
			"name": _encode_cache_value(value.name),
			"index": _encode_axis(value.index),
			"dtype": str(value.dtype),
			"attrs": _encode_cache_value(value.attrs),
			"data": [_encode_cache_value(item) for item in value.tolist()],
		}
	if isinstance(value, Mapping):
		return {
			"__type__": "mapping",
			"items": [[_encode_cache_value(key), _encode_cache_value(item)] for key, item in value.items()],
		}
	if isinstance(value, tuple):
		return {"__type__": "tuple", "items": [_encode_cache_value(item) for item in value]}
	if isinstance(value, set):
		return {"__type__": "set", "items": [_encode_cache_value(item) for item in sorted(value, key=str)]}
	if isinstance(value, list):
		return [_encode_cache_value(item) for item in value]
	if hasattr(value, "item"):
		return _encode_cache_value(value.item())
	raise TypeError(f"Unsupported cache value type: {type(value).__module__}.{type(value).__qualname__}")


def _restore_frame_dtypes(frame, dtypes):
	for position, dtype in enumerate(dtypes):
		try:
			converted = frame.iloc[:, position].astype(dtype)
			frame.isetitem(position, converted)
		except (TypeError, ValueError):
			continue
	return frame


def _decode_cache_value(value):
	"""Decode the JSON tree produced by `_encode_cache_value`."""
	if isinstance(value, list):
		return [_decode_cache_value(item) for item in value]
	if not isinstance(value, dict) or "__type__" not in value:
		return value
	kind = value["__type__"]
	if kind == "pd_na":
		return pd.NA
	if kind == "pd_nat":
		return pd.NaT
	if kind == "float":
		return {"nan": math.nan, "inf": math.inf, "-inf": -math.inf}[value["value"]]
	if kind == "timestamp":
		result = pd.Timestamp(value["value"])
		if value.get("timezone") and result.tzinfo is not None:
			try:
				result = result.tz_convert(ZoneInfo(value["timezone"]))
			except ZoneInfoNotFoundError:
				pass
		return result
	if kind == "pd_timedelta":
		return pd.Timedelta(value["value"])
	if kind == "datetime":
		result = datetime.datetime.fromisoformat(value["value"])
		if value.get("timezone") and result.tzinfo is not None:
			try:
				result = result.astimezone(ZoneInfo(value["timezone"]))
			except ZoneInfoNotFoundError:
				pass
		return result
	if kind == "date":
		return datetime.date.fromisoformat(value["value"])
	if kind == "time":
		return datetime.time.fromisoformat(value["value"])
	if kind == "timedelta":
		return datetime.timedelta(seconds=value["seconds"])
	if kind == "path":
		return Path(value["value"])
	if kind == "bytes":
		return base64.b64decode(value["value"])
	if kind == "dataframe":
		frame = pd.DataFrame(
			[[_decode_cache_value(item) for item in row] for row in value["data"]],
			columns=_decode_axis(value["columns"]),
			index=_decode_axis(value["index"]),
		)
		frame.attrs = _decode_cache_value(value.get("attrs", {"__type__": "mapping", "items": []}))
		return _restore_frame_dtypes(frame, value.get("dtypes", []))
	if kind == "series":
		series = pd.Series(
			[_decode_cache_value(item) for item in value["data"]],
			index=_decode_axis(value["index"]),
			name=_decode_cache_value(value.get("name")),
		)
		try:
			series = series.astype(value.get("dtype"))
		except (TypeError, ValueError):
			pass
		series.attrs = _decode_cache_value(value.get("attrs", {"__type__": "mapping", "items": []}))
		return series
	if kind == "mapping":
		return {_decode_cache_value(key): _decode_cache_value(item) for key, item in value["items"]}
	if kind == "tuple":
		return tuple(_decode_cache_value(item) for item in value["items"])
	if kind == "set":
		return set(_decode_cache_value(item) for item in value["items"])
	raise ValueError(f"Unknown cache value type: {kind}")


def _canonical_param_value(value):
	if value is None or isinstance(value, (str, int, bool)):
		return value
	if isinstance(value, float):
		if math.isnan(value):
			return {"float": "nan"}
		if math.isinf(value):
			return {"float": "inf" if value > 0 else "-inf"}
		return value
	if isinstance(value, Mapping):
		items = [[_canonical_param_value(key), _canonical_param_value(item)] for key, item in value.items()]
		items.sort(key=lambda item: json.dumps(item[0], ensure_ascii=False, sort_keys=True, separators=(",", ":")))
		return {"mapping": items}
	if isinstance(value, (list, tuple)):
		return {type(value).__name__: [_canonical_param_value(item) for item in value]}
	if isinstance(value, (set, frozenset)):
		items = [_canonical_param_value(item) for item in value]
		items.sort(key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
		return {"set": items}
	if isinstance(value, (pd.Timestamp, pd.Timedelta, datetime.datetime, datetime.date, datetime.time, datetime.timedelta, Path)):
		return {type(value).__name__: str(value)}
	if hasattr(value, "item"):
		return _canonical_param_value(value.item())
	return {"type": f"{type(value).__module__}.{type(value).__qualname__}", "repr": repr(value)}


def _canonical_params(params):
	encoded = _canonical_param_value(params)
	return json.dumps(encoded, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _cache_identity(source, symbol, function, params, session_date):
	params_hash = hashlib.sha256(_canonical_params(params).encode("utf-8")).hexdigest()
	identity = {
		"source": str(source),
		"symbol": str(symbol or "_").upper(),
		"function": str(function),
		"params_hash": params_hash,
		"session_date": str(session_date),
	}
	filename = hashlib.sha256(json.dumps(identity, sort_keys=True).encode("utf-8")).hexdigest() + ".json"
	return identity, filename


def _atomic_json_write(path, document):
	path.parent.mkdir(parents=True, exist_ok=True)
	fd, temporary = tempfile.mkstemp(prefix=f".{path.stem}-", suffix=".tmp", dir=path.parent)
	try:
		with os.fdopen(fd, "w", encoding="utf-8") as handle:
			json.dump(document, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
			handle.flush()
			os.fsync(handle.fileno())
		os.replace(temporary, path)
	finally:
		try:
			os.unlink(temporary)
		except FileNotFoundError:
			pass


def cached_call(source, symbol, function, params, fetcher, *, price_endpoint=False, no_cache=None):
	"""Return a cached live-source result while preserving its Python data type.

	The key follows the binding `(source, symbol, function, params, completed-session)` contract. Price data may change during the regular session, so an open-market entry lives for at most fifteen minutes; non-price data keeps the completed-session lifetime.
	"""
	try:
		from market_clock import get_market_state
	except ModuleNotFoundError:
		from .market_clock import get_market_state

	state = get_market_state()
	disabled = _CACHE_DISABLED or bool(no_cache)
	identity, filename = _cache_identity(source, symbol, function, params, state["last_completed_session"])
	path = cache_dir() / filename
	event = {**identity, "key": filename[:-5][:12]}
	if disabled:
		_record_cache_event({**event, "status": "bypass", "reason": "no-cache"})
		try:
			return fetcher()
		except Exception as exc:
			_record_cache_event({**event, "status": "error", "reason": f"fetch:{type(exc).__name__}"})
			raise

	max_age = OPEN_PRICE_TTL_SECONDS if price_endpoint and state["market_open"] else None
	try:
		with path.open("r", encoding="utf-8") as handle:
			document = json.load(handle)
		age = max(0.0, time.time() - float(document["created_at_epoch"]))
		valid = document.get("schema") == CACHE_SCHEMA_VERSION and document.get("identity") == identity
		if valid and (max_age is None or age <= max_age):
			_record_cache_event({**event, "status": "hit", "age_seconds": round(age, 3)})
			return _decode_cache_value(document["payload"])
	except FileNotFoundError:
		pass
	except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
		_record_cache_event({**event, "status": "error", "reason": f"cache-read:{type(exc).__name__}"})

	_record_cache_event({**event, "status": "miss"})
	try:
		value = fetcher()
	except Exception as exc:
		_record_cache_event({**event, "status": "error", "reason": f"fetch:{type(exc).__name__}"})
		raise
	try:
		document = {
			"schema": CACHE_SCHEMA_VERSION,
			"created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
			"created_at_epoch": time.time(),
			"identity": identity,
			"payload": _encode_cache_value(value),
		}
		_atomic_json_write(path, document)
	except (OSError, TypeError, ValueError) as exc:
		_record_cache_event({**event, "status": "error", "reason": f"cache-write:{type(exc).__name__}"})
	return value


def normalize(obj):
	"""Convert pandas/numpy types to JSON-serializable Python objects."""
	if obj is None:
		return None
	if isinstance(obj, bool):
		return obj
	if isinstance(obj, float):
		if not math.isfinite(obj):
			return None
		return obj
	if isinstance(obj, (str, int)):
		return obj
	if isinstance(obj, (datetime.datetime, datetime.date)):
		return obj.isoformat()
	if isinstance(obj, pd.Timestamp):
		return obj.isoformat()
	if isinstance(obj, pd.Timedelta):
		return str(obj)
	if isinstance(obj, pd.DataFrame):
		if obj.empty:
			return []
		result = {}
		for col in obj.columns:
			result[str(col)] = {str(idx): normalize(val) for idx, val in obj[col].items()}
		return result
	if isinstance(obj, pd.Series):
		return {str(k): normalize(v) for k, v in obj.items()}
	if isinstance(obj, dict):
		return {str(k): normalize(v) for k, v in obj.items()}
	if isinstance(obj, (list, tuple)):
		return [normalize(v) for v in obj]
	if hasattr(obj, "item"):  # numpy scalar
		val = obj.item()
		if isinstance(val, float) and not math.isfinite(val):
			return None
		return val
	return str(obj)


def _inject_cache_metadata(data):
	metadata = cache_metadata()
	if isinstance(data, dict) and metadata["events"] and "_cache" not in data:
		data = dict(data)
		data["_cache"] = metadata
	return data


def output_json(data):
	"""Serialize data to JSON and print to stdout."""
	json.dump(_inject_cache_metadata(normalize(data)), sys.stdout, ensure_ascii=False, indent=2, allow_nan=False)
	print()


def error_json(message, code=1):
	"""Output error as JSON and exit."""
	json.dump(_inject_cache_metadata({"error": str(message)}), sys.stdout, ensure_ascii=False, indent=2, allow_nan=False)
	print()
	sys.exit(code)


class JsonArgumentParser(argparse.ArgumentParser):
	"""Make public CLI usage errors obey the JSON-stdout/exit-1 contract."""

	def error(self, message):
		error_json(f"argument error: {message}")


def output_json_records(data):
	"""Serialize data as JSON records format and print to stdout.

	Converts a pandas DataFrame or dict-of-dicts to records format:
	[{col1: val1, col2: val2}, ...] instead of the default column-oriented format.
	For non-DataFrame inputs, delegates to output_json.
	"""
	if isinstance(data, pd.DataFrame):
		if data.empty:
			json.dump([], sys.stdout, ensure_ascii=False, indent=2, allow_nan=False)
		else:
			records = [{str(col): normalize(row[col]) for col in data.columns} for _, row in data.iterrows()]
			json.dump(records, sys.stdout, ensure_ascii=False, indent=2, allow_nan=False)
		print()
	else:
		output_json(data)


def calculate_sma(prices, period):
	"""Simple moving average over `period` bars.

	The one indicator the SEPA tools actually share. It lives here, with the other
	plumbing, rather than in a standalone indicators module: the rest of that module
	was RSI/EMA/Bollinger/ATR/MACD — mean-reversion oscillators that work against a
	momentum method and were never imported.
	"""
	return prices.rolling(window=period).mean()


def safe_run(func):
	"""Decorator: wrap function in try/except with JSON error output."""

	@functools.wraps(func)
	def wrapper(*args, **kwargs):
		try:
			return func(*args, **kwargs)
		except SystemExit:
			raise
		except Exception as e:
			error_json(f"{type(e).__name__}: {e}")

	return wrapper


_YFINANCE_PRICE_METHODS = {"history"}


class FastInfoView(dict):
	"""Cached mapping that preserves yfinance FastInfo-style attribute access."""

	def __getattr__(self, name):
		try:
			return self[name]
		except KeyError as exc:
			raise AttributeError(name) from exc

	def __dir__(self):
		return sorted(set(super().__dir__()) | {str(key) for key in self})


def _fast_info_snapshot(value):
	"""Materialize FastInfo once so the live quote can use the normal price TTL."""
	result = {}
	try:
		result.update(dict(value))
	except (TypeError, ValueError):
		pass
	for name in dir(value):
		if name.startswith("_"):
			continue
		try:
			item = getattr(value, name)
		except Exception:
			continue
		if not callable(item):
			result[name] = item
	return result


class CachedTicker:
	"""Drop-in `yfinance.Ticker` proxy backed by the shared JSON cache."""

	def __init__(self, ticker, *args, **kwargs):
		self._symbol = str(ticker).upper()
		self._ticker = _ORIGINAL_YFINANCE_TICKER(ticker, *args, **kwargs)

	def __repr__(self):
		return repr(self._ticker)

	def __getattr__(self, name):
		if name == "fast_info":
			payload = cached_call(
				"yfinance",
				self._symbol,
				"property:fast_info",
				{},
				lambda: _fast_info_snapshot(getattr(self._ticker, name)),
				price_endpoint=True,
			)
			return FastInfoView(payload)
		static = inspect.getattr_static(type(self._ticker), name, None)
		if isinstance(static, property):
			return cached_call(
				"yfinance",
				self._symbol,
				f"property:{name}",
				{},
				lambda: getattr(self._ticker, name),
				price_endpoint=False,
			)
		attribute = getattr(self._ticker, name)
		if not callable(attribute):
			return attribute
		if name == "get_fast_info":
			@functools.wraps(attribute)
			def get_fast_info(*args, **kwargs):
				payload = cached_call(
					"yfinance",
					self._symbol,
					name,
					{"args": args, "kwargs": kwargs},
					lambda: _fast_info_snapshot(attribute(*args, **kwargs)),
					price_endpoint=True,
				)
				return FastInfoView(payload)

			return get_fast_info

		@functools.wraps(attribute)
		def invoke(*args, **kwargs):
			return cached_call(
				"yfinance",
				self._symbol,
				name,
				{"args": args, "kwargs": kwargs},
				lambda: attribute(*args, **kwargs),
				price_endpoint=name in _YFINANCE_PRICE_METHODS,
			)

		return invoke


def install_yfinance_cache():
	"""Install the process-local Ticker proxy once and return the yfinance module."""
	import yfinance as yf

	if not hasattr(yf, "_minervini_original_ticker"):
		yf._minervini_original_ticker = yf.Ticker
	yf.Ticker = CachedTicker
	yf._minervini_cache_installed = True
	return yf


import yfinance as _yfinance

_ORIGINAL_YFINANCE_TICKER = getattr(_yfinance, "_minervini_original_ticker", _yfinance.Ticker)
install_yfinance_cache()
