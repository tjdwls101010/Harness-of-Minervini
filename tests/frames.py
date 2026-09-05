"""Small OHLCV construction helpers; scenarios own the prices they supply."""

import pandas as pd


def frame(rows, *, end="2025-12-26", index=None, columns=("Open", "High", "Low", "Close", "Volume")) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=columns, index=pd.bdate_range(end=end, periods=len(rows)) if index is None else index)


def bars(count: int, *, end="2025-12-26", close=100.0, volume=1_000_000) -> pd.DataFrame:
    return pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close, "Volume": volume}, index=pd.bdate_range(end=end, periods=count))


def reading_date(frame: pd.DataFrame, position: int) -> str:
    return frame.index[position].date().isoformat()


def dict_bars(frame: pd.DataFrame) -> list[dict]:
    return [{"date": stamp.date().isoformat(), **{str(key).lower(): value for key, value in row.items()}} for stamp, row in frame.iterrows()]
