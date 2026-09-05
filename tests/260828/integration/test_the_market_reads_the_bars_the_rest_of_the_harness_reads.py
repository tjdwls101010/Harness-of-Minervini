"""The regime word is reduced from leader histories nothing else in the harness will measure.

`market.snapshot` turns a leader's provider frame into row dicts through `_ohlcv_rows`, which
sorts nothing, deduplicates nothing, and stamps `completed: True` on every row it is handed.
The readers below it defend some of that and not the rest, so a frame the shared reader
refuses reaches `leader_traction` -- one of the four signals the regime word is reduced from.

Two of these move the word in opposite directions, which is the reason both are here. A
history of complex numbers loses its imaginary part on the way in and reads as an ordinary
advance, so the snapshot calls the regime favorable. A history of booleans becomes a flat line
at 1.0, which is simultaneously its own 52-week low, so the same laundering calls the regime
defensive. Neither history is a price series at all.
"""

from __future__ import annotations

from tests.providers import rows_snapshot

from datetime import date, datetime, timezone
import unittest
import numpy as np
import pandas as pd

from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot, ProviderUnavailable
from scripts.minervini.setup_structure import read_bars


AS_OF = "2025-12-31"


def rising(sessions: int = 300) -> pd.DataFrame:
    close = pd.Series(np.linspace(50.0, 150.0, sessions), index=pd.bdate_range(end=AS_OF, periods=sessions))
    return pd.DataFrame(
        {"Open": close * 0.999, "High": close * 1.002, "Low": close * 0.998, "Close": close, "Volume": np.full(sessions, 1_000_000.0)},
        index=close.index,
    )


def snapshot(frame: pd.DataFrame) -> ProviderSnapshot[pd.DataFrame]:
    return rows_snapshot(frame, provider="fixture-prices", retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc), as_of=date.fromisoformat(AS_OF), coverage={"completed_only": True})


def rows(provider: str, payload: list[dict[str, object]]) -> ProviderSnapshot[list[dict[str, object]]]:
    return rows_snapshot(payload, provider=provider, retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc), as_of=date.fromisoformat(AS_OF))


def complex_prices() -> pd.DataFrame:
    frame = rising()
    for column, imaginary in (("Open", 1j), ("High", 2j), ("Low", 3j), ("Close", 4j), ("Volume", 5j)):
        frame[column] = frame[column].astype(complex) + imaginary
    return frame


def booleans() -> pd.DataFrame:
    frame = rising()
    for column in frame.columns:
        frame[column] = True
    return frame


def one_session_printed_twice() -> pd.DataFrame:
    """The repeat carries a different clock time, so only the session date betrays it."""

    frame = rising(259)
    repeat = frame.iloc[[0]].copy()
    repeat.index = pd.DatetimeIndex([frame.index[0] + pd.Timedelta(hours=12)])
    return pd.concat([frame, repeat]).sort_index()


def epoch_index() -> pd.DataFrame:
    frame = rising()
    frame.index = pd.Index([stamp.value for stamp in frame.index])
    return frame


def inverted_first_bar() -> pd.DataFrame:
    frame = rising()
    frame.iloc[0, frame.columns.get_loc("High")] = 60.0
    frame.iloc[0, frame.columns.get_loc("Low")] = 70.0
    return frame


REFUSED = {
    "complex numbers throughout": (complex_prices, "history_contains_non_numeric_values"),
    "booleans throughout": (booleans, "history_contains_non_numeric_values"),
    "one session printed twice at a different clock time": (one_session_printed_twice, "history_repeats_a_session"),
    "an index of epoch nanoseconds": (epoch_index, "history_index_is_not_dates"),
    "a bar whose high is under its low": (inverted_first_bar, "history_contains_invalid_bar_ranges"),
}


class TheRegimeIsNotReducedFromUnreadableBars(unittest.TestCase):
    def runtime(self, price_history) -> Runtime:
        return Runtime(
            price_history=price_history,
            current_classification=lambda symbol: (_ for _ in ()).throw(ProviderUnavailable("yfinance", "fixture_withholds_classification", operation="current_classification")),
            finviz_breadth=lambda as_of: (_ for _ in ()).throw(ProviderUnavailable("finviz", "fixture_withholds_breadth", operation="raw_snapshot")),
            sector_ranking=lambda as_of: rows("ibd-rs-rating", [{"sector": "Zeta Technology", "avg_rs": 92.0, "count": 20}]),
            industry_ranking=lambda as_of: rows("ibd-rs-rating", [{"industry": "Semiconductors", "sector": "Zeta Technology", "avg_rs": 95.0, "count": 8}]),
            market_leaders=lambda as_of, limit: rows("ibd-rs-rating", [{"ticker": "LEAD", "rs_rating": 99, "rs_raw": 4.2}]),
        )

    def snapshot_from(self, leader: pd.DataFrame) -> dict:
        def prices(ticker: str, as_of: str) -> ProviderSnapshot[pd.DataFrame]:
            return snapshot(rising() if ticker == "QQQ" else leader)

        return execute("market.snapshot", {"as_of": AS_OF, "trade_traction": "supports", "leader_limit": 10}, runtime=self.runtime(prices))

    def test_a_readable_leader_is_still_measured(self) -> None:
        """The route that was always earned, so every refusal below is the history."""

        payload = self.snapshot_from(rising())

        leader = payload["data"]["leaders"][0]
        self.assertEqual(leader["ticker"], "LEAD")
        self.assertEqual(leader["behavior"]["state"], "supports")

    def test_a_leader_history_the_shared_reader_refuses_measures_nothing(self) -> None:
        for description, (build, reason) in REFUSED.items():
            history = build()
            with self.subTest(history=description):
                self.assertEqual(read_bars(history)[1], reason)

                payload = self.snapshot_from(history)

                leader = payload["data"]["leaders"][0]
                self.assertEqual(leader["behavior"]["state"], "unavailable")
                # The envelope has to say why. A leader read as flat and a leader whose bars
                # were not prices are the same word in the payload and different findings.
                named = [item for item in payload["missing"] if item.get("ticker") == "LEAD"]
                self.assertEqual([item["reason"] for item in named], [reason])

    def test_the_qqq_switch_is_not_read_off_a_history_the_shared_reader_refuses(self) -> None:
        """QQQ is context rather than a regime signal, and it still may not be invented."""

        def prices(ticker: str, as_of: str) -> ProviderSnapshot[pd.DataFrame]:
            return snapshot(epoch_index() if ticker == "QQQ" else rising())

        payload = execute("market.snapshot", {"as_of": AS_OF, "trade_traction": "supports", "leader_limit": 10}, runtime=self.runtime(prices))

        switch = next(signal for signal in payload["data"]["signal_vector"] if signal["id"] == "qqq_21ema_switch")

        self.assertEqual(switch["state"], "unavailable")
        # It used to publish `date: "1787788800000000000"` beside a state of `on`.
        self.assertNotIn("date", switch["value"])
        named = [item for item in payload["missing"] if item["id"] == "qqq_daily_bars"]
        self.assertEqual([item["reason"] for item in named], ["history_index_is_not_dates"])


if __name__ == "__main__":
    unittest.main()
