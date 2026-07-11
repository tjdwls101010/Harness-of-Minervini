#!/usr/bin/env python3
"""Market breadth plus the QQQ 21-EMA information switch.

``breadth`` keeps its two fragile sources isolated: Finviz supplies four breadth
sections and Yahoo Finance supplies the QQQ switch. A failure in either source is
reported on that section as unavailable and does not erase the other evidence.
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import requests
from lxml import html
import pandas as pd
import yfinance as yf

from market_clock import get_market_state
from utils import JsonArgumentParser, configure_cache, output_json, safe_run

_URL = "https://finviz.com/"
_REQUEST_TIMEOUT_SECONDS = 10
_USER_AGENT = (
	"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
	"AppleWebKit/537.36 (KHTML, like Gecko) "
	"Chrome/120.0.0.0 Safari/537.36"
)

_FIELDS = [
	("advancing_declining", "advancing", "declining"),
	("new_high_low", "new_high", "new_low"),
	("sma50", "above", "below"),
	("sma200", "above", "below"),
]
_PCT_COUNT_RE = re.compile(r"([\d.]+)%\s*\((\d+)\)")
_COUNT_PCT_RE = re.compile(r"\((\d+)\)\s*([\d.]+)%")
_CLASS_TOKEN = "contains(concat(' ', normalize-space(@class), ' '), ' {} ')"

_DOCTRINE = (
	"[M] Market exposure is decided bottom-up by leader quality and trade feedback. "
	"[TL] The QQQ 21-EMA state is only an information filter: ON permits probes, not "
	"automatic exposure expansion; OFF argues for defense. It is not an O'Neil FTD."
)


def _unavailable(reason):
	return {"unavailable": True, "reason": str(reason)}


def _parse_side(texts, pattern):
	for text in texts:
		match = pattern.search(text)
		if not match:
			continue
		if pattern is _PCT_COUNT_RE:
			return {"pct": float(match.group(1)), "count": int(match.group(2))}
		return {"pct": float(match.group(2)), "count": int(match.group(1))}
	return None


def _fetch_finviz_html():
	"""Fetch and minimally validate the Finviz homepage before caching it."""
	from utils import cached_call

	def fetcher():
		response = requests.get(
			_URL,
			headers={"User-Agent": _USER_AGENT},
			timeout=_REQUEST_TIMEOUT_SECONDS,
		)
		response.raise_for_status()
		if "market-stats" not in response.text:
			raise ValueError("Finviz response is missing market-stats DOM markers")
		return response.text

	return cached_call(
		"finviz",
		"US-MARKET",
		"homepage-market-stats",
		{"url": _URL},
		fetcher,
	)


def _parse_finviz_sections(document):
	"""Parse breadth blocks with XPath only; malformed sections degrade locally."""
	tree = html.fromstring(document)
	if tree.tag.lower() not in {"html", "body", "div"}:
		raise ValueError(f"Unexpected Finviz DOM root: {tree.tag}")
	stats = tree.xpath(f"//div[{_CLASS_TOKEN.format('market-stats')}]")
	if not stats:
		raise ValueError("Finviz DOM contains no market-stats blocks")

	result = {}
	for index, (key, positive_name, negative_name) in enumerate(_FIELDS):
		if index >= len(stats):
			result[key] = _unavailable("Finviz DOM section is missing")
			continue

		element = stats[index]
		positive_nodes = element.xpath(
			f".//*[{_CLASS_TOKEN.format('market-stats_labels_left')}]//p"
		)
		negative_nodes = element.xpath(
			f".//*[{_CLASS_TOKEN.format('market-stats_labels_right')}]//p"
		)
		positive_texts = [node.text_content().strip() for node in positive_nodes]
		negative_texts = [node.text_content().strip() for node in negative_nodes]
		positive = _parse_side(positive_texts, _PCT_COUNT_RE)
		negative = _parse_side(negative_texts, _COUNT_PCT_RE)
		if positive is None or negative is None:
			result[key] = _unavailable("Finviz DOM section did not contain valid percent/count values")
			continue
		result[key] = {positive_name: positive, negative_name: negative}
	return result


def get_market_breadth():
	"""Fetch Finviz and return all four breadth sections."""
	return _parse_finviz_sections(_fetch_finviz_html())


def _completed_qqq_history():
	"""Return completed QQQ daily bars; never treat an intraday partial as a close."""
	data = yf.Ticker("QQQ").history(period="6mo", interval="1d", auto_adjust=False, actions=False)
	data = data.dropna(subset=["High", "Low", "Close"])
	if data.empty:
		return data

	state = get_market_state()
	now_et = pd.Timestamp(state["now_et"])
	last_date = data.index[-1].date()
	if last_date == now_et.date() and state.get("market_open"):
		data = data.iloc[:-1]
	return data


def _evaluate_qqq_switch(data):
	"""Evaluate the asymmetric state machine on completed daily OHLC rows."""
	if len(data) < 22:
		raise ValueError("Need at least 22 completed QQQ sessions for the 21-EMA switch")

	data = data.copy()
	data["ema21"] = data["Close"].ewm(span=21, adjust=False, min_periods=21).mean()
	state = "UNKNOWN"
	last_transition = None
	transition_reason = None
	transitions = []
	for index in range(20, len(data)):
		close = float(data["Close"].iloc[index])
		ema = float(data["ema21"].iloc[index])
		new_state = state
		reason = None
		if close > ema:
			new_state = "ON"
			reason = "one completed close above the 21 EMA"
		elif index > 20:
			prior_close = float(data["Close"].iloc[index - 1])
			prior_ema = float(data["ema21"].iloc[index - 1])
			prior_low = float(data["Low"].iloc[index - 1])
			if prior_close < prior_ema and close < ema and close < prior_low:
				new_state = "OFF"
				reason = "two closes below the 21 EMA and the second close below the prior low"

		if new_state != state and new_state != "UNKNOWN":
			last_transition = str(data.index[index].date())
			transition_reason = reason
			transitions.append({"date": last_transition, "state": new_state, "reason": reason})
		state = new_state

	latest = data.iloc[-1]
	previous = data.iloc[-2]
	return {
		"state": state,
		"date": str(data.index[-1].date()),
		"close": round(float(latest["Close"]), 4),
		"ema21": round(float(latest["ema21"]), 4),
		"prior_close": round(float(previous["Close"]), 4),
		"prior_low": round(float(previous["Low"]), 4),
		"last_transition": last_transition,
		"transition_reason": transition_reason,
		"recent_transitions": transitions[-5:],
		"rules": {
			"ON": "[TL] one completed QQQ close above the 21 EMA",
			"OFF": "[TL] two consecutive closes below the 21 EMA AND the second close below the prior day's low",
		},
	}


def get_qqq_switch():
	"""Fetch completed QQQ bars and evaluate the [TL] asymmetric switch."""
	return _evaluate_qqq_switch(_completed_qqq_history())


@safe_run
def cmd_breadth(args):
	"""Get independent Finviz breadth and QQQ-switch sections."""
	if args.no_cache:
		configure_cache(True)
	result = {}
	try:
		result.update(get_market_breadth())
	except Exception as exc:
		for key, _, _ in _FIELDS:
			result[key] = _unavailable(f"{type(exc).__name__}: {exc}")

	try:
		result["qqq_21ema_switch"] = get_qqq_switch()
	except Exception as exc:
		result["qqq_21ema_switch"] = _unavailable(f"{type(exc).__name__}: {exc}")

	result["doctrine"] = _DOCTRINE
	result["provenance"] = {
		"breadth": "Finviz homepage market-stats blocks",
		"qqq_21ema_switch": "Yahoo Finance QQQ completed daily OHLC via yfinance",
		"methodology": ["[M] bottom-up leader feedback", "[TL] asymmetric QQQ 21-EMA information switch"],
	}
	output_json(result)


def main():
	parser = JsonArgumentParser(description="Market breadth and QQQ 21-EMA information switch")
	sub = parser.add_subparsers(dest="command", required=True)

	sp = sub.add_parser("breadth", help="Market breadth snapshot plus asymmetric QQQ switch")
	sp.add_argument("--no-cache", action="store_true", help="Bypass cache reads and writes for this command")
	sp.set_defaults(func=cmd_breadth)

	args = parser.parse_args()
	args.func(args)


if __name__ == "__main__":
	main()
