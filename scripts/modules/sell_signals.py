#!/usr/bin/env python3
"""Deterministic sell-signal instruments with explicit doctrine provenance.

The module does not issue portfolio-allocation advice or collapse observations into a universal sell verdict. Minervini remains the doctrine of record; TraderLion mechanics are a tagged practice layer where that corpus is silent. Run ``scripts/.venv/bin/python scripts/modules/stage_analysis.py risk SYMBOL`` for the Stage-2 drawdown diagnostic, which deliberately has a single owner.
"""

import argparse
import datetime as dt
import os
import sys
import pandas as pd
import yfinance as yf

sys.path.insert(0, os.path.dirname(__file__))
from market_clock import get_market_state
from utils import configure_cache, error_json, output_json, safe_run


BASE_EXTENSION_ZONE_PCT = (20.0, 25.0)  # [TL] The map's explicit base-top sell-into-strength zone.
VOLUME_BAND_MULT = 1.25  # [TL] Average-volume vocabulary begins at +25% versus the chosen baseline.
LOWER_RANGE_CR_PCT = 50.0  # [TL] Closing Range below 50% means sellers controlled the bar's lower half.
DEFAULT_VISUAL_EXTENSION_PCT = 20.0  # Noncanonical proxy only: transfers the base-zone floor to MA distance so item 1 can be observed mechanically.

DOCTRINE = "Minervini-first: SEPA risk rules remain controlling; TraderLion sell mechanics are tagged practice-layer observations, not a universal verdict."


class JsonArgumentParser(argparse.ArgumentParser):
    """Keep CLI usage errors on the module's JSON/exit-1 contract."""

    def error(self, message):
        error_json(f"ArgumentError: {message}")


def _parse_date(value, flag_name):
    if value is None:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{flag_name} must be YYYY-MM-DD: {value}") from exc


def _completed_daily(data):
    required = ["Open", "High", "Low", "Close", "Volume"]
    if data is None or data.empty:
        return pd.DataFrame(columns=required)
    missing = [column for column in required if column not in data.columns]
    if missing:
        raise ValueError(f"History is missing required columns: {', '.join(missing)}")
    complete = data.dropna(subset=required).copy()
    if complete.empty:
        return complete
    state = get_market_state()
    now_et_date = pd.Timestamp(state["now_et"]).date()
    if state["market_open"] and complete.index[-1].date() == now_et_date:
        complete = complete.iloc[:-1]
    return complete


def _load_daily(symbol, period, start=None):
    ticker = yf.Ticker(symbol)
    if start is None:
        raw = ticker.history(period=period, interval="1d", auto_adjust=True)
    else:
        warmup_start = start - dt.timedelta(days=420)
        raw = ticker.history(start=warmup_start.isoformat(), interval="1d", auto_adjust=True)
    data = _completed_daily(raw)
    if data.empty:
        raise ValueError(f"No completed daily OHLCV history for {symbol}")
    return data


def _ema(series, period):
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def _sma(series, period):
    return series.rolling(window=period, min_periods=period).mean()


def _pct_above(value, reference):
    if reference is None or pd.isna(reference) or float(reference) <= 0:
        raise ValueError("Reference price must be positive")
    return (float(value) / float(reference) - 1.0) * 100.0


def _date_text(index_value):
    return str(index_value.date())


def _closing_range_pct(row):
    spread = float(row["High"]) - float(row["Low"])
    if spread <= 0:
        return None
    return (float(row["Close"]) - float(row["Low"])) / spread * 100.0


def _extension_snapshot(data, base_top=None):
    if len(data) < 200:
        raise ValueError(f"Insufficient history: need at least 200 completed daily bars, received {len(data)}")
    close = data["Close"]
    current = float(close.iloc[-1])
    sma50 = _sma(close, 50)
    sma200 = _sma(close, 200)
    current_sma50 = float(sma50.iloc[-1])
    current_sma200 = float(sma200.iloc[-1])
    if base_top is None:
        base_top_result = {
            "status": "needs_input",
            "source": None,
            "base_top": None,
            "pct_above": None,
            "zone_pct": list(BASE_EXTENSION_ZONE_PCT),
            "zone_state": "needs_input",
            "origin": "[TL]",
            "reason": "No deterministic VCP pivot/base-top was supplied; a base anchor is never invented.",
        }
    else:
        if base_top <= 0:
            raise ValueError("--base-top must be positive")
        pct = _pct_above(current, base_top)
        low, high = BASE_EXTENSION_ZONE_PCT
        zone_state = "below_zone" if pct < low else "in_zone" if pct <= high else "above_zone"
        base_top_result = {
            "status": "measured",
            "source": "argument",
            "base_top": round(float(base_top), 4),
            "pct_above": round(pct, 2),
            "zone_pct": list(BASE_EXTENSION_ZONE_PCT),
            "zone_state": zone_state,
            "origin": "[TL]",
        }
    return {
        "current_price": current,
        "base_top_extension": base_top_result,
        "ma_extension": {
            "sma50": {"value": round(current_sma50, 4), "pct_above": round(_pct_above(current, current_sma50), 2), "origin": "[TL]"},
            "sma200": {"value": round(current_sma200, 4), "pct_above": round(_pct_above(current, current_sma200), 2), "origin": "[TL]"},
            "interpretation": "Distances are measurements only; the maps specify no canonical MA-distance sell threshold.",
        },
    }


def _climax_snapshot(data):
    from stage_analysis import compute_risk_snapshot

    snapshot = compute_risk_snapshot(data)
    climax = dict(snapshot["climax_extension"])
    climax["origin"] = "[M]"
    climax["owner"] = "stage_analysis.compute_risk_snapshot"
    return climax


def _item(item_id, key, status, evidence=None, caveat=None):
    result = {
        "id": item_id,
        "key": key,
        "origin": "[TL]",
        "status": status,
        "determinate": status in {"triggered", "not_triggered"},
        "evidence": evidence,
    }
    if caveat:
        result["caveat"] = caveat
    return result


def _reversal_items(data, base_top=None, breakout_date=None, visual_extension_pct=DEFAULT_VISUAL_EXTENSION_PCT):
    extension = _extension_snapshot(data, base_top=base_top)
    latest = data.iloc[-1]
    previous = data.iloc[-2]
    close = float(latest["Close"])
    latest_high = float(latest["High"])
    at_period_high = latest_high >= float(data["High"].max())
    ma_distances = [extension["ma_extension"]["sma50"]["pct_above"], extension["ma_extension"]["sma200"]["pct_above"]]
    if extension["base_top_extension"]["status"] == "measured":
        ma_distances.append(extension["base_top_extension"]["pct_above"])
    maximum_extension = max(ma_distances)
    item1_triggered = at_period_high and maximum_extension >= visual_extension_pct
    item1 = _item(
        1,
        "visual_extension_at_highs",
        "triggered" if item1_triggered else "not_triggered",
        {
            "at_fetched_period_high": at_period_high,
            "max_extension_pct": round(maximum_extension, 2),
            "heuristic_threshold_pct": visual_extension_pct,
            "base_top_status": extension["base_top_extension"]["status"],
        },
        "Invented heuristic, not canonical: the source says visual extension but gives no MA-distance threshold; the default transfers the +20% base-zone floor and is exposed as --visual-extension-pct.",
    )

    gap_up = float(latest["Open"]) > float(previous["High"])
    gap_filled = float(latest["Low"]) <= float(previous["High"])
    reversed_below_prior_close = close < float(previous["Close"])
    item2_triggered = gap_up and gap_filled and reversed_below_prior_close
    item2 = _item(
        2,
        "gap_up_fill_and_reverse",
        "triggered" if item2_triggered else "not_triggered",
        {"gap_up_above_prior_high": gap_up, "filled_to_prior_high": gap_filled, "closed_below_prior_close": reversed_below_prior_close},
        "Mechanical OHLCV operationalization; the source supplies the sequence but no gap-size threshold.",
    )

    item3 = _item(3, "high_trendline_break", "needs_chart", None, "The source supplies no deterministic trendline anchor; corroborate with chart_render.")

    if breakout_date is None:
        item4 = _item(4, "abnormal_or_post_breakout_max_volume", "needs_input", None, "The source does not define a breakout anchor or maximum lookback; supply --breakout-date rather than inventing one.")
        item5 = _item(5, "post_breakout_max_range_bar", "needs_input", None, "The source does not define a breakout anchor or maximum lookback; supply --breakout-date rather than inventing one.")
    else:
        segment = data[data.index.date >= breakout_date]
        if segment.empty:
            raise ValueError("--breakout-date falls after the available completed history")
        volume50 = _sma(data["Volume"], 50)
        current_volume = float(latest["Volume"])
        current_volume_average = float(volume50.iloc[-1])
        max_volume = float(segment["Volume"].max())
        abnormal_volume = current_volume >= current_volume_average * VOLUME_BAND_MULT
        post_breakout_maximum = current_volume >= max_volume
        item4_triggered = abnormal_volume or post_breakout_maximum
        item4 = _item(
            4,
            "abnormal_or_post_breakout_max_volume",
            "triggered" if item4_triggered else "not_triggered",
            {
                "breakout_date": breakout_date.isoformat(),
                "current_volume": round(current_volume),
                "post_breakout_max_volume": round(max_volume),
                "is_post_breakout_maximum": post_breakout_maximum,
                "volume_vs_50bar_average": round(current_volume / current_volume_average, 3),
                "above_average_floor": VOLUME_BAND_MULT,
                "is_abnormal_volume": abnormal_volume,
            },
        )
        ranges = (segment["High"] - segment["Low"]).astype(float)
        current_range = float(ranges.iloc[-1])
        maximum_range = float(ranges.max())
        item5_triggered = current_range >= maximum_range
        item5 = _item(
            5,
            "post_breakout_max_range_bar",
            "triggered" if item5_triggered else "not_triggered",
            {"breakout_date": breakout_date.isoformat(), "current_range": round(current_range, 4), "post_breakout_max_range": round(maximum_range, 4)},
        )

    closing_range = _closing_range_pct(latest)
    if closing_range is None:
        item6 = _item(6, "reversal_below_prior_low_lower_range_close", "needs_chart", {"closing_range_pct": None}, "High equals low, so closing-range location is undefined.")
    else:
        traded_below_prior_low = float(latest["Low"]) < float(previous["Low"])
        lower_range_close = closing_range < LOWER_RANGE_CR_PCT
        item6_triggered = traded_below_prior_low and lower_range_close
        item6 = _item(
            6,
            "reversal_below_prior_low_lower_range_close",
            "triggered" if item6_triggered else "not_triggered",
            {
                "traded_below_prior_low": traded_below_prior_low,
                "closed_below_prior_low": close < float(previous["Low"]),
                "closing_range_pct": round(closing_range, 2),
                "lower_range_ceiling_pct": LOWER_RANGE_CR_PCT,
            },
            "Mechanical OHLCV operationalization: 'lower range' is the lower half (CR < 50%); it is not a universal sell threshold.",
        )
    return [item1, item2, item3, item4, item5, item6], extension


def _trail_events(view, ma_series):
    events = []
    consecutive_below = 0
    last_trigger_date = None
    for index, close in view["Close"].items():
        ma_value = ma_series.loc[index]
        if pd.isna(ma_value):
            continue
        below = float(close) < float(ma_value)
        if below:
            consecutive_below += 1
            if consecutive_below == 1:
                event_type = "first_close_below"
            elif consecutive_below == 2:
                event_type = "second_close_below_trigger"
                last_trigger_date = _date_text(index)
            else:
                event_type = "additional_close_below"
            events.append({
                "date": _date_text(index),
                "type": event_type,
                "close": round(float(close), 4),
                "ma_value": round(float(ma_value), 4),
                "consecutive_below": consecutive_below,
                "triggered": consecutive_below == 2,
            })
        else:
            if consecutive_below:
                events.append({
                    "date": _date_text(index),
                    "type": "reclaim_reset",
                    "close": round(float(close), 4),
                    "ma_value": round(float(ma_value), 4),
                    "consecutive_below": 0,
                    "triggered": False,
                })
            consecutive_below = 0
    state = "above" if consecutive_below == 0 else "one_close_below" if consecutive_below == 1 else "exit_triggered"
    return events, {"state": state, "consecutive_below": consecutive_below, "last_trigger_date": last_trigger_date}


def _cross_below_indices(close, ma, allowed_index):
    crossed = (close < ma) & (close.shift(1) >= ma.shift(1))
    return [index for index in close.index if index in allowed_index and bool(crossed.loc[index])]


def _first_at_or_after(indices, earliest_index=None):
    for index in indices:
        if earliest_index is None or index >= earliest_index:
            return index
    return None


def _caller_failed_retest(data, start_index, prior_high, tolerance_pct):
    lower = prior_high * (1.0 - tolerance_pct / 100.0)
    upper = prior_high * (1.0 + tolerance_pct / 100.0)
    segment = data.loc[start_index:]
    touch_date = None
    for index, row in segment.iterrows():
        intersects = float(row["High"]) >= lower and float(row["Low"]) <= upper
        if touch_date is None and intersects:
            touch_date = index
        if touch_date is not None and float(row["Close"]) < lower:
            return index, touch_date, lower, upper
    return None, touch_date, lower, upper


def _cascade_snapshot(data, start=None, prior_high=None, tolerance_pct=None):
    close = data["Close"]
    ema21 = _ema(close, 21)
    sma50 = _sma(close, 50)
    sma200 = _sma(close, 200)
    valid = data.index[data.index.date >= start] if start else data.index
    if len(valid) == 0:
        raise ValueError("--start falls after the available completed history")
    loss21 = _first_at_or_after(_cross_below_indices(close, ema21, valid))
    loss50 = _first_at_or_after(_cross_below_indices(close, sma50, valid), loss21) if loss21 is not None else None
    loss200 = _first_at_or_after(_cross_below_indices(close, sma200, valid), loss50) if loss50 is not None else None

    events = []
    for stage, key, index, reference in [
        (1, "loss_21e", loss21, ema21),
        (2, "loss_50s", loss50, sma50),
        (4, "loss_200s_terminal", loss200, sma200),
    ]:
        if index is not None:
            events.append({"date": _date_text(index), "stage": stage, "event": key, "close": round(float(close.loc[index]), 4), "reference_value": round(float(reference.loc[index]), 4)})

    retest_status = "needs_chart"
    retest_date = None
    retest_evidence = {"method": "visual anchor required; no canonical nearness threshold is invented"}
    if prior_high is not None:
        if loss50 is None:
            retest_status = "not_observed"
            retest_evidence = {"method": "caller_controlled_noncanonical", "reason": "No preceding 50 SMA loss was observed in the requested period."}
        else:
            retest_date, touch_date, lower, upper = _caller_failed_retest(data, loss50, prior_high, tolerance_pct)
            retest_status = "observed" if retest_date is not None else "not_observed"
            retest_evidence = {
                "method": "caller_controlled_noncanonical",
                "prior_high": round(prior_high, 4),
                "tolerance_pct": tolerance_pct,
                "band": [round(lower, 4), round(upper, 4)],
                "band_touch_date": _date_text(touch_date) if touch_date is not None else None,
                "rule": "After the 50 SMA loss, a completed bar intersects the caller band and the same or a later completed bar closes below its lower edge.",
            }
            if retest_date is not None:
                events.append({"date": _date_text(retest_date), "stage": 3, "event": "prior_high_failed_retest", "close": round(float(close.loc[retest_date]), 4), "reference_value": round(prior_high, 4)})

    events.sort(key=lambda event: (event["date"], event["stage"]))
    stages = [
        {"stage": 1, "key": "loss_21e", "status": "observed" if loss21 is not None else "not_observed", "date": _date_text(loss21) if loss21 is not None else None, "origin": "[TL]"},
        {"stage": 2, "key": "loss_50s", "status": "observed" if loss50 is not None else "not_observed", "date": _date_text(loss50) if loss50 is not None else None, "origin": "[TL]"},
        {"stage": 3, "key": "prior_high_failed_retest", "status": retest_status, "date": _date_text(retest_date) if retest_date is not None else None, "origin": "[TL]", "evidence": retest_evidence},
        {"stage": 4, "key": "loss_200s_terminal", "status": "observed" if loss200 is not None else "not_observed", "date": _date_text(loss200) if loss200 is not None else None, "origin": "[TL]"},
    ]
    if loss200 is not None:
        current_state = "200s_terminal"
    elif retest_date is not None:
        current_state = "failed_retest"
    elif loss50 is not None:
        current_state = "50s_lost"
    elif loss21 is not None:
        current_state = "21e_lost"
    else:
        current_state = "intact"
    return stages, events, current_state


@safe_run
def cmd_reversal(args):
    configure_cache(args.no_cache)
    symbol = args.symbol.upper()
    breakout_date = _parse_date(args.breakout_date, "--breakout-date")
    if args.visual_extension_pct <= 0:
        raise ValueError("--visual-extension-pct must be positive")
    data = _load_daily(symbol, args.period)
    if len(data) < 200:
        raise ValueError(f"Insufficient history for reversal: need 200 completed daily bars, received {len(data)}")
    items, extension = _reversal_items(data, base_top=args.base_top, breakout_date=breakout_date, visual_extension_pct=args.visual_extension_pct)
    determinate = [item for item in items if item["determinate"]]
    triggered = sum(item["status"] == "triggered" for item in determinate)
    output_json({
        "symbol": symbol,
        "command": "reversal",
        "date": _date_text(data.index[-1]),
        "items": items,
        "summary": {"triggered": triggered, "not_triggered": len(determinate) - triggered, "determinate": len(determinate), "indeterminate": len(items) - len(determinate), "total": 6},
        "extension_context": {"base_top_extension": extension["base_top_extension"], "ma_extension": extension["ma_extension"]},
        "related_chart_command": f"scripts/.venv/bin/python scripts/modules/chart_render.py daily {symbol}",
        "doctrine": DOCTRINE,
        "provenance": {"checklist": "[TL]", "priority": "[M]"},
    })


@safe_run
def cmd_extension(args):
    configure_cache(args.no_cache)
    symbol = args.symbol.upper()
    data = _load_daily(symbol, args.period)
    snapshot = _extension_snapshot(data, base_top=args.base_top)
    output_json({
        "symbol": symbol,
        "command": "extension",
        "date": _date_text(data.index[-1]),
        "current_price": round(snapshot["current_price"], 4),
        "base_top_extension": snapshot["base_top_extension"],
        "ma_extension": snapshot["ma_extension"],
        "climax_extension": _climax_snapshot(data),
		"related_command": f"scripts/.venv/bin/python scripts/modules/stage_analysis.py risk {symbol}",
        "doctrine": DOCTRINE,
        "provenance": {"base_and_ma_extension": "[TL]", "climax": "[M]"},
    })


@safe_run
def cmd_trail(args):
    configure_cache(args.no_cache)
    symbol = args.symbol.upper()
    start = _parse_date(args.start, "--start")
    data = _load_daily(symbol, args.period, start=start)
    period = 21 if args.ma == "21e" else 50
    ma_series = _ema(data["Close"], period) if args.ma == "21e" else _sma(data["Close"], period)
    view = data[data.index.date >= start] if start else data.loc[ma_series.dropna().index]
    if view.empty:
        raise ValueError("No completed bars in the requested trail period")
    events, current_state = _trail_events(view, ma_series)
    output_json({
        "symbol": symbol,
        "command": "trail",
        "date": _date_text(data.index[-1]),
        "start": start.isoformat() if start else None,
        "ma": {"code": args.ma, "kind": "EMA" if args.ma == "21e" else "SMA", "period": period},
        "events": events,
        "violation_count": sum(event["type"] == "second_close_below_trigger" for event in events),
        "current_state": current_state,
        "origin": "[TL-Kell]",
        "doctrine": "[TL-Kell] Two completed closes below the selected management MA trigger the mechanical baseline; reclaim resets the close counter. SEPA hard stops and planned strength-selling remain controlling.",
        "provenance": {"trail": "[TL-Kell]", "priority": "[M]"},
    })


@safe_run
def cmd_cascade(args):
    configure_cache(args.no_cache)
    symbol = args.symbol.upper()
    start = _parse_date(args.start, "--start")
    supplied = (args.prior_high is not None, args.prior_high_tolerance_pct is not None)
    if supplied[0] != supplied[1]:
        raise ValueError("--prior-high and --prior-high-tolerance-pct must be supplied together")
    if args.prior_high is not None and args.prior_high <= 0:
        raise ValueError("--prior-high must be positive")
    if args.prior_high_tolerance_pct is not None and args.prior_high_tolerance_pct < 0:
        raise ValueError("--prior-high-tolerance-pct must be nonnegative")
    data = _load_daily(symbol, args.period, start=start)
    if len(data) < 200:
        raise ValueError(f"Insufficient history for cascade: need 200 completed daily bars, received {len(data)}")
    stages, events, current_state = _cascade_snapshot(data, start=start, prior_high=args.prior_high, tolerance_pct=args.prior_high_tolerance_pct)
    output_json({
        "symbol": symbol,
        "command": "cascade",
        "date": _date_text(data.index[-1]),
        "start": start.isoformat() if start else None,
        "inputs": {"prior_high": args.prior_high, "prior_high_tolerance_pct": args.prior_high_tolerance_pct},
        "stages": stages,
        "events": events,
        "current_state": current_state,
        "doctrine": "[TL] Failure cascade: single-close 21 EMA loss, then 50 SMA loss, caller-anchored prior-high failed retest, and terminal 200 SMA loss. The failed-retest stage stays needs_chart without both caller inputs.",
        "provenance": {"cascade": "[TL]", "priority": "[M]"},
    })


def _add_common(subparser, default_period="2y"):
    subparser.add_argument("symbol", help="Ticker symbol")
    subparser.add_argument("--period", default=default_period, help=f"History period passed to yfinance (default: {default_period})")
    subparser.add_argument("--no-cache", action="store_true", help="Bypass cache reads and writes for this invocation")


def build_parser():
    parser = JsonArgumentParser(description="Provenance-tagged Minervini/TraderLion sell-signal instruments")
    sub = parser.add_subparsers(dest="command", required=True)

    reversal = sub.add_parser("reversal", help="Evaluate the TraderLion six-item key-reversal checklist")
    _add_common(reversal)
    reversal.add_argument("--base-top", type=float, help="Explicit base-top/pivot price for extension context; never inferred")
    reversal.add_argument("--breakout-date", help="Explicit YYYY-MM-DD breakout anchor for post-breakout maxima in items 4 and 5")
    reversal.add_argument("--visual-extension-pct", type=float, default=DEFAULT_VISUAL_EXTENSION_PCT, help="Noncanonical item-1 MA-extension proxy (default: 20; output is caveated)")
    reversal.set_defaults(func=cmd_reversal)

    extension = sub.add_parser("extension", help="Measure base-top and moving-average extension without inventing a base")
    _add_common(extension)
    extension.add_argument("--base-top", type=float, help="Explicit base-top/pivot price; omitted emits needs_input")
    extension.set_defaults(func=cmd_extension)

    trail = sub.add_parser("trail", help="Run the full dated two-close MA-trail state machine")
    _add_common(trail)
    trail.add_argument("--ma", choices=["21e", "50s"], default="21e", help="Management MA: 21-day EMA or 50-day SMA (default: 21e)")
    trail.add_argument("--start", help="First event date in YYYY-MM-DD; warmup is fetched before it")
    trail.set_defaults(func=cmd_trail)

    cascade = sub.add_parser("cascade", help="Run the dated 21e/50s/prior-high/200s failure cascade")
    _add_common(cascade)
    cascade.add_argument("--start", help="First event date in YYYY-MM-DD; warmup is fetched before it")
    cascade.add_argument("--prior-high", type=float, help="Caller-supplied prior-high anchor; requires --prior-high-tolerance-pct")
    cascade.add_argument("--prior-high-tolerance-pct", type=float, help="Caller-supplied nonnegative near-band tolerance in percent; requires --prior-high")
    cascade.set_defaults(func=cmd_cascade)
    return parser


def main():
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
