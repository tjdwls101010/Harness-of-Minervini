#!/usr/bin/env python3
"""Render daily or weekly OHLCV charts as non-gating corroboration.

Numbers decide and eyes corroborate. Daily eligibility uses 50/150/200 SMA while management overlays use 10/21 EMA; weekly uses only 10/30/40-week SMA equivalents and never a 200-week moving average.
"""

import argparse
import datetime as dt
import os
import re
import sys
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd
import yfinance as yf

sys.path.insert(0, os.path.dirname(__file__))
from market_clock import get_market_state, is_trading_day
from utils import configure_cache, error_json, output_json, safe_run


VOLUME_BAND_PCT = 25.0  # [TL] Meaningfully above/below average begins outside ±25%.
DAILY_VOLUME_AVERAGE_BARS = 50  # [TL] Position-trader volume baseline.
WEEKLY_VOLUME_AVERAGE_BARS = 10  # Five sessions per week gives the 50-session equivalent.
DAILY_MAS = ("EMA10", "EMA21", "SMA50", "SMA150", "SMA200")
WEEKLY_MAS = ("SMA10W", "SMA30W", "SMA40W")
DOCTRINE = "Numbers decide; eyes corroborate. This chart is never a gate."


class JsonArgumentParser(argparse.ArgumentParser):
    """Keep CLI usage errors on the module's JSON/exit-1 contract."""

    def error(self, message):
        error_json(f"ArgumentError: {message}")


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


def _period_delta(period):
    match = re.fullmatch(r"(\d+)(d|wk|mo|y)", period)
    if not match:
        if period in {"ytd", "max"}:
            return None
        raise ValueError("--period must use Nd, Nwk, Nmo, Ny, ytd, or max")
    amount = int(match.group(1))
    if amount <= 0:
        raise ValueError("--period amount must be positive")
    unit = match.group(2)
    days = amount if unit == "d" else amount * 7 if unit == "wk" else amount * 31 if unit == "mo" else amount * 366
    return dt.timedelta(days=days)


def _visible_start(last_date, period):
    if period == "max":
        return None
    if period == "ytd":
        return dt.date(last_date.year, 1, 1)
    return last_date - _period_delta(period)


def _fetch_start(period, timeframe):
    today = dt.datetime.now(ZoneInfo("America/New_York")).date()
    if period == "max":
        return None
    visible_start = dt.date(today.year, 1, 1) if period == "ytd" else today - _period_delta(period)
    return visible_start - dt.timedelta(days=330 if timeframe == "daily" else 320)


def _fetch_daily(symbol, period, timeframe):
    ticker = yf.Ticker(symbol)
    start = _fetch_start(period, timeframe)
    raw = ticker.history(period="max", interval="1d", auto_adjust=True) if start is None else ticker.history(start=start.isoformat(), interval="1d", auto_adjust=True)
    data = _completed_daily(raw)
    if data.empty:
        raise ValueError(f"No completed daily OHLCV history for {symbol}")
    return data


def _to_completed_weekly(daily):
    weekly = daily.resample("W-FRI").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}).dropna(subset=["Open", "High", "Low", "Close"])
    if not weekly.empty:
        label = weekly.index[-1]
        expected_last_session = label.date()
        while expected_last_session.weekday() >= 5 or not is_trading_day(expected_last_session):
            expected_last_session -= dt.timedelta(days=1)
        if daily.index[-1].date() < expected_last_session:
            weekly = weekly.iloc[:-1]
    return weekly


def _compute_overlays(bars, timeframe):
    close = bars["Close"]
    if timeframe == "daily":
        moving = {
            "EMA10": close.ewm(span=10, adjust=False, min_periods=10).mean(),
            "EMA21": close.ewm(span=21, adjust=False, min_periods=21).mean(),
            "SMA50": close.rolling(50, min_periods=50).mean(),
            "SMA150": close.rolling(150, min_periods=150).mean(),
            "SMA200": close.rolling(200, min_periods=200).mean(),
        }
        volume_bars = DAILY_VOLUME_AVERAGE_BARS
    else:
        moving = {
            "SMA10W": close.rolling(10, min_periods=10).mean(),
            "SMA30W": close.rolling(30, min_periods=30).mean(),
            "SMA40W": close.rolling(40, min_periods=40).mean(),
        }
        volume_bars = WEEKLY_VOLUME_AVERAGE_BARS
    volume_average = bars["Volume"].rolling(volume_bars, min_periods=volume_bars).mean()
    return moving, volume_average, volume_average * 1.25, volume_average * 0.75, volume_bars


def _trim_visible(bars, moving, volume_average, volume_upper, volume_lower, period):
    cutoff = _visible_start(bars.index[-1].date(), period)
    visible = bars if cutoff is None else bars[bars.index.date >= cutoff]
    if visible.empty:
        raise ValueError("No completed bars fall inside the requested visible period")
    first_index = visible.index[0]
    longest_name = "SMA200" if "SMA200" in moving else "SMA40W"
    longest = moving[longest_name].loc[visible.index]
    if longest.notna().sum() == 0:
        raise ValueError("Insufficient history to compute the longest moving average")
    if period != "max" and pd.isna(longest.loc[first_index]):
        raise ValueError("Insufficient warmup history to populate the longest moving average at the first visible bar")
    trimmed = {name: series.loc[visible.index] for name, series in moving.items()}
    return visible, trimmed, volume_average.loc[visible.index], volume_upper.loc[visible.index], volume_lower.loc[visible.index]


def _default_output(symbol, timeframe, date_text):
    cache_root = Path(os.environ.get("MINERVINI_CACHE_DIR", "~/.cache/minervini-harness")).expanduser()
    return cache_root / "charts" / f"{symbol}_{timeframe}_{date_text}.png"


def _output_path(value, symbol, timeframe, date_text):
    path = Path(value).expanduser() if value else _default_output(symbol, timeframe, date_text)
    if path.suffix.lower() != ".png":
        raise ValueError("--out must end in .png")
    return path.resolve()


def _addplots(moving, volume_average, volume_upper, volume_lower, pivot):
    colors = {
        "EMA10": "#ff9800",
        "EMA21": "#1e88e5",
        "SMA50": "#7b1fa2",
        "SMA150": "#00897b",
        "SMA200": "#424242",
        "SMA10W": "#ff9800",
        "SMA30W": "#1e88e5",
        "SMA40W": "#424242",
    }
    plots = [
        mpf.make_addplot(series, panel=0, color=colors[name], width=0.9, label=name, secondary_y=False)
        for name, series in moving.items()
    ]
    plots.extend(
        [
            mpf.make_addplot(volume_average, panel=1, color="#546e7a", width=0.9, label="Vol avg", secondary_y=False),
            mpf.make_addplot(volume_upper, panel=1, color="#2e7d32", width=0.7, linestyle="--", label="Vol +25%", secondary_y=False),
            mpf.make_addplot(volume_lower, panel=1, color="#c62828", width=0.7, linestyle="--", label="Vol -25%", secondary_y=False),
        ]
    )
    if pivot is not None:
        pivot_series = pd.Series(float(pivot), index=next(iter(moving.values())).index)
        plots.append(mpf.make_addplot(pivot_series, panel=0, color="#d32f2f", width=1.1, linestyle="--", label=f"Pivot {pivot:g}", secondary_y=False))
    return plots


def _render_png(bars, moving, volume_average, volume_upper, volume_lower, output_path, symbol, timeframe, pivot):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    addplots = _addplots(moving, volume_average, volume_upper, volume_lower, pivot)
    style = mpf.make_mpf_style(base_mpf_style="yahoo", gridstyle=":", y_on_right=False)
    style["rc"]["figure.titleweight"] = "bold"
    title = f"{symbol} {timeframe.title()} — corroboration only"
    if pivot is not None:
        title += f" — pivot {pivot:g}"

    figure, axes = mpf.plot(
        bars,
        type="candle",
        volume=True,
        addplot=addplots,
        style=style,
        title=title,
        ylabel="Price",
        ylabel_lower="Volume",
        panel_ratios=(3, 1),
        returnfig=True,
        warn_too_much_data=max(1000, len(bars) + 1),
        figsize=(14, 8),
    )
    axes[0].legend(loc="upper left", fontsize=7, ncol=3, frameon=False)
    if len(axes) >= 3:
        axes[2].legend(loc="upper left", fontsize=7, ncol=3, frameon=False)
    temporary_name = None
    try:
        with tempfile.NamedTemporaryFile(prefix=f".{output_path.stem}-", suffix=".png", dir=output_path.parent, delete=False) as handle:
            temporary_name = handle.name
        figure.savefig(temporary_name, format="png", dpi=150, bbox_inches="tight")
        if Path(temporary_name).stat().st_size == 0:
            raise ValueError("Chart renderer produced an empty PNG")
        os.replace(temporary_name, output_path)
        temporary_name = None
    finally:
        plt.close(figure)
        if temporary_name is not None:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass


@safe_run
def cmd_render(args):
    configure_cache(args.no_cache)
    symbol = args.symbol.upper()
    _period_delta(args.period)
    if args.pivot is not None and args.pivot <= 0:
        raise ValueError("--pivot must be positive")

    daily = _fetch_daily(symbol, args.period, args.timeframe)
    bars = daily if args.timeframe == "daily" else _to_completed_weekly(daily)
    if bars.empty:
        raise ValueError(f"No completed {args.timeframe} OHLCV history for {symbol}")
    moving, volume_average, volume_upper, volume_lower, volume_bars = _compute_overlays(bars, args.timeframe)
    visible, moving, volume_average, volume_upper, volume_lower = _trim_visible(
        bars, moving, volume_average, volume_upper, volume_lower, args.period
    )
    date_text = str(visible.index[-1].date())
    output_path = _output_path(args.out, symbol, args.timeframe, date_text)
    _render_png(visible, moving, volume_average, volume_upper, volume_lower, output_path, symbol, args.timeframe, args.pivot)

    output_json(
        {
            "symbol": symbol,
            "command": args.timeframe,
            "timeframe": args.timeframe,
            "period": args.period,
            "output": str(output_path),
            "png_bytes": output_path.stat().st_size,
            "bars": len(visible),
            "date_range": {"start": str(visible.index[0].date()), "end": date_text},
            "moving_averages": list(moving),
            "moving_average_roles": {
                "daily": "10/21 EMA are management overlays; 50/150/200 SMA are eligibility context.",
                "weekly": "10/30/40-week SMA equivalents; no 200-week average is rendered.",
            },
            "volume_overlay": {
                "average_bars": volume_bars,
                "bands_pct": [-VOLUME_BAND_PCT, VOLUME_BAND_PCT],
                "origin": "[TL]",
            },
            "pivot_annotation": {"status": "rendered", "value": args.pivot} if args.pivot is not None else {"status": "not_requested", "value": None},
            "doctrine": DOCTRINE,
            "provenance": {
                "eligibility_averages": "[M]",
                "management_averages": "[TL]",
                "volume_bands": "[TL]",
                "visual_role": "binding harness design",
            },
        }
    )


def _add_common(subparser, default_period):
    subparser.add_argument("symbol", help="Ticker symbol")
    subparser.add_argument("--period", default=default_period, help=f"Visible period: Nd, Nwk, Nmo, Ny, ytd, or max (default: {default_period})")
    subparser.add_argument("--out", help="PNG output path; default is the user cache charts directory")
    subparser.add_argument("--pivot", type=float, help="Optional caller-supplied pivot price annotation; never inferred")
    subparser.add_argument("--no-cache", action="store_true", help="Bypass cache reads and writes for this invocation")


def build_parser():
    parser = JsonArgumentParser(description="Render non-gating daily or weekly price/MA/volume corroboration charts")
    sub = parser.add_subparsers(dest="timeframe", required=True)
    daily = sub.add_parser("daily", help="Daily chart with 10/21 EMA and 50/150/200 SMA")
    _add_common(daily, "1y")
    daily.set_defaults(func=cmd_render)
    weekly = sub.add_parser("weekly", help="Weekly chart with 10/30/40-week SMA equivalents (never 200-week)")
    _add_common(weekly, "2y")
    weekly.set_defaults(func=cmd_render)
    return parser


def main():
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
