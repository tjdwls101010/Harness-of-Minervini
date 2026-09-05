"""Shared fixtures for chart draws the power play."""

from __future__ import annotations

from pathlib import Path
from scripts.minervini import chart as chart_module
from scripts.minervini.chart import _power_play_spans, render_chart_artifacts


def _rendered(frame, directory):
    return render_chart_artifacts(
        frame, ticker="TEST", as_of=frame.index[-1].date(), output_dir=directory
    )


def _png_software(path) -> str | None:
    """What the PNG itself says drew it, read out of its own tEXt chunks."""

    raw = Path(path).read_bytes()
    offset = 8
    while offset + 8 <= len(raw):
        length = int.from_bytes(raw[offset:offset + 4], "big")
        kind = raw[offset + 4:offset + 8]
        body = raw[offset + 8:offset + 8 + length]
        if kind == b"tEXt":
            keyword, _, value = body.partition(b"\x00")
            if keyword == b"Software":
                return value.decode("latin-1")
        offset += 12 + length
    return None


def _panel_index(artifact, daily):
    """The bars the named panel actually drew, as an index."""
    if artifact["timeframe"] == "weekly":
        return (
            daily.resample("W-FRI")
            .agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
            .dropna()
            .index
        )
    if artifact["timeframe"] == "power_play":
        window = chart_module._span_window(daily, _power_play_spans(daily, "digest")["spans"])
        return window.index
    return daily.index


def artifact_end(artifact, daily):
    return _panel_index(artifact, daily)[-1]
