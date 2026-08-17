"""Render auditable chart artifacts from completed provider OHLCV data only."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np
import pandas as pd


RENDERER_VERSION = "1.0.0"
_REQUIRED_COLUMNS = ("Open", "High", "Low", "Close", "Volume")
_TICKER_PATTERN = re.compile(r"[A-Z][A-Z0-9.-]{0,9}")


def render_chart_artifacts(
    daily_ohlcv: pd.DataFrame,
    *,
    ticker: str,
    as_of: str | date,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Render weekly then daily PNGs and a colocated provenance manifest.

    ``daily_ohlcv`` is already-completed provider data. This boundary performs no
    provider lookup and rejects data outside the explicit ``as_of`` session.
    """
    symbol = _ticker(ticker)
    as_of_date = _as_of_date(as_of)
    daily = _completed_daily(daily_ohlcv, as_of_date)
    directory = Path(output_dir).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)

    input_sha256 = _input_sha256(daily)
    weekly = _weekly_bars(daily, as_of_date)
    artifact_specs = (("weekly", weekly), ("daily", daily))
    artifacts: list[dict[str, Any]] = []
    for timeframe, bars in artifact_specs:
        path = directory / f"{symbol}_{as_of_date.isoformat()}_{timeframe}.png"
        _render_png(bars, path, symbol, timeframe, as_of_date)
        artifacts.append({"timeframe": timeframe, "path": str(path), "bars": len(bars)})

    manifest_path = directory / f"{symbol}_{as_of_date.isoformat()}_manifest.json"
    manifest = {
        "renderer_version": RENDERER_VERSION,
        "ticker": symbol,
        "as_of": as_of_date.isoformat(),
        "input_sha256": input_sha256,
        "paths": {artifact["timeframe"]: artifact["path"] for artifact in artifacts},
        "artifacts": artifacts,
    }
    _atomic_json(manifest_path, manifest)
    return {**manifest, "manifest_path": str(manifest_path)}


def _ticker(value: str) -> str:
    symbol = str(value).strip().upper()
    if not _TICKER_PATTERN.fullmatch(symbol):
        raise ValueError("ticker must be a US-listed symbol")
    return symbol


def _as_of_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise ValueError("as_of must be an ISO date") from error


def _completed_daily(daily_ohlcv: pd.DataFrame, as_of: date) -> pd.DataFrame:
    if not isinstance(daily_ohlcv, pd.DataFrame):
        raise ValueError("daily_ohlcv must be a DataFrame")
    missing = [column for column in _REQUIRED_COLUMNS if column not in daily_ohlcv.columns]
    if missing:
        raise ValueError(f"daily_ohlcv is missing required columns: {', '.join(missing)}")
    if daily_ohlcv.empty:
        raise ValueError("daily_ohlcv contains no completed bars")

    bars = daily_ohlcv.loc[:, _REQUIRED_COLUMNS].copy()
    index = pd.to_datetime(bars.index, errors="coerce")
    if index.isna().any() or index.has_duplicates:
        raise ValueError("daily_ohlcv index must contain unique trading dates")
    bars.index = index.tz_localize(None) if index.tz is not None else index
    bars = bars.sort_index()
    if bars.index[-1].date() > as_of:
        raise ValueError("daily_ohlcv contains a bar after as_of")
    for column in _REQUIRED_COLUMNS:
        bars[column] = pd.to_numeric(bars[column], errors="coerce")
    if bars.isna().any().any() or not np.isfinite(bars.to_numpy(dtype=float)).all():
        raise ValueError("daily_ohlcv must contain finite completed OHLCV values")
    if (bars["Volume"] < 0).any() or (bars["High"] < bars["Low"]).any():
        raise ValueError("daily_ohlcv contains invalid OHLCV ranges")
    if ((bars["Open"] < bars["Low"]) | (bars["Open"] > bars["High"]) | (bars["Close"] < bars["Low"]) | (bars["Close"] > bars["High"])).any():
        raise ValueError("daily_ohlcv open and close must fall inside each high-low range")
    return bars


def _input_sha256(daily: pd.DataFrame) -> str:
    records = [
        {
            "date": timestamp.date().isoformat(),
            **{column: float(row[column]) for column in _REQUIRED_COLUMNS},
        }
        for timestamp, row in daily.iterrows()
    ]
    canonical = json.dumps({"columns": _REQUIRED_COLUMNS, "bars": records}, separators=(",", ":"), sort_keys=True, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _weekly_bars(daily: pd.DataFrame, as_of: date) -> pd.DataFrame:
    weekly = daily.resample("W-FRI").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    ).dropna()
    weekly = weekly.loc[weekly.index.date <= as_of]
    if weekly.empty:
        raise ValueError("daily_ohlcv contains no completed weekly bars as_of")
    return weekly


def _render_png(bars: pd.DataFrame, path: Path, ticker: str, timeframe: str, as_of: date) -> None:
    figure, (price_axis, volume_axis) = plt.subplots(
        2,
        1,
        figsize=(12, 7),
        sharex=True,
        gridspec_kw={"height_ratios": (3, 1)},
        layout="constrained",
    )
    try:
        dates = mdates.date2num(bars.index.to_pydatetime())
        width = 0.65 if timeframe == "daily" else 3.25
        colors = np.where(bars["Close"].to_numpy() >= bars["Open"].to_numpy(), "#18794e", "#b42318")
        for position, (_, row), color in zip(dates, bars.iterrows(), colors, strict=True):
            price_axis.vlines(position, row["Low"], row["High"], color=color, linewidth=0.8)
            body_low = min(row["Open"], row["Close"])
            body_height = max(abs(row["Close"] - row["Open"]), 0.01)
            price_axis.add_patch(Rectangle((position - width / 2, body_low), width, body_height, facecolor=color, edgecolor=color, linewidth=0.6))
        close = bars["Close"]
        if timeframe == "daily":
            overlays = {"EMA 10": close.ewm(span=10, adjust=False, min_periods=10).mean(), "EMA 21": close.ewm(span=21, adjust=False, min_periods=21).mean(), "SMA 50": close.rolling(50, min_periods=50).mean()}
        else:
            overlays = {"SMA 10W": close.rolling(10, min_periods=10).mean(), "SMA 30W": close.rolling(30, min_periods=30).mean(), "SMA 40W": close.rolling(40, min_periods=40).mean()}
        for label, values in overlays.items():
            if values.notna().any():
                price_axis.plot(bars.index, values, linewidth=0.9, label=label)
        volume_axis.bar(bars.index, bars["Volume"], width=width, color=colors, alpha=0.8)
        price_axis.set_title(f"{ticker} {timeframe.title()} — as of {as_of.isoformat()}")
        price_axis.set_ylabel("Price")
        volume_axis.set_ylabel("Volume")
        price_axis.grid(axis="y", alpha=0.25)
        volume_axis.grid(axis="y", alpha=0.25)
        if price_axis.get_legend_handles_labels()[0]:
            price_axis.legend(loc="upper left", fontsize=8, frameon=False)
        volume_axis.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
        figure.autofmt_xdate(rotation=30, ha="right")
        _atomic_figure(figure, path)
    finally:
        plt.close(figure)


def _atomic_figure(figure: plt.Figure, path: Path) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix=f".{path.stem}-", suffix=".png", dir=path.parent, delete=False) as handle:
            temporary_path = Path(handle.name)
        figure.savefig(temporary_path, format="png", dpi=150, metadata={"Software": f"minervini-chart/{RENDERER_VERSION}"})
        if temporary_path.stat().st_size == 0:
            raise ValueError("chart renderer produced an empty PNG")
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix=f".{path.stem}-", suffix=".json", dir=path.parent, mode="w", encoding="utf-8", delete=False) as handle:
            temporary_path = Path(handle.name)
            json.dump(payload, handle, sort_keys=True, indent=2)
            handle.write("\n")
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


__all__ = ["RENDERER_VERSION", "render_chart_artifacts"]
