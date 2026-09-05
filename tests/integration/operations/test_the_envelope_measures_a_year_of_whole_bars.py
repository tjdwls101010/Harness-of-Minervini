"""The same two rules through the channel a person actually runs.

The unit seam settles what the reading is. This one settles what `ticker.qualify` publishes,
which is the only place the difference is visible to anyone: a criterion that went from a
guessed fail to unavailable changes the envelope's verdict word, its `missing` list and its
route all at once, and none of those are observable from the evidence builder alone.
"""

from __future__ import annotations

from tests.providers import rows_snapshot

from datetime import date, datetime, timezone
import unittest
import numpy as np
import pandas as pd

from scripts.minervini.operations import Runtime, execute


AS_OF = "2026-08-27"
ABOVE_LOW = "trend_template.price_above_52_week_low"
NEAR_HIGH = "trend_template.price_near_52_week_high"


def _snapshot(payload, provider: str):
    return rows_snapshot(payload, provider=provider, retrieved_at=datetime(2026, 8, 28, tzinfo=timezone.utc), as_of=date.fromisoformat(AS_OF), coverage={"completed_only": True})


def qualify(history: pd.DataFrame, **request) -> dict:
    return execute(
        "ticker.qualify",
        {"ticker": "TEST", "as_of": AS_OF, **request},
        runtime=Runtime(
            price_history=lambda ticker, as_of: _snapshot(history, "fixture-prices"),
            rs_rating=lambda ticker, as_of: _snapshot({"rating": 95, "rating_date": AS_OF}, "ibd-rs-rating"),
        ),
    )


def history(closes: list[float], *, highs: list[float] | None = None) -> pd.DataFrame:
    index = pd.bdate_range(end=AS_OF, periods=len(closes))
    close = pd.Series(closes, index=index, dtype=float)
    high = close * 1.01 if highs is None else pd.Series(highs, index=index, dtype=float)
    return pd.DataFrame(
        {
            "Open": close,
            "High": np.maximum(high, close),
            "Low": close * 0.99,
            "Close": close,
            "Volume": np.full(len(close), 1_000_000.0),
        },
        index=index,
    )


def criteria(payload: dict) -> dict:
    return {signal["id"]: signal for signal in payload["signals"]}


class TheEnvelopeSaysWhatItCouldMeasure(unittest.TestCase):
    def test_a_young_stock_reaches_its_own_route_instead_of_a_52_week_rejection(self) -> None:
        """The route the recent-IPO exception exists to open, no longer closed ahead of it."""

        advance = np.linspace(42.0, 52.0, 130)
        base = np.concatenate([np.linspace(52.0, 45.0, 18), np.linspace(45.0, 51.0, 20)])
        payload = qualify(
            history(np.concatenate([advance, base, [53.0]]).tolist()),
            primary_base_quality="supports",
        )

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["data"]["route"], "recent_ipo_primary_base")
        self.assertEqual(payload["data"]["eligibility_state"], "eligible")
        for identifier in (ABOVE_LOW, NEAR_HIGH):
            self.assertEqual(criteria(payload)[identifier]["state"], "unavailable")

    def test_an_unmeasurable_year_is_named_as_a_gap_rather_than_left_silent(self) -> None:
        """Where the reading could not reach a verdict, the envelope says which criteria.

        A history long enough for the 200-day average but short of a full year measures six
        criteria and cannot measure two, and INCOMPLETE without naming them is an envelope
        that reports whole evidence beside a verdict it could not reach.
        """

        payload = qualify(history(np.linspace(60.0, 150.0, 240).tolist()))

        self.assertEqual(payload["data"]["eligibility_state"], "incomplete")
        named = {item["id"] for item in payload["missing"]}
        self.assertIn(ABOVE_LOW, named)
        self.assertIn(NEAR_HIGH, named)

    def test_a_full_year_still_measures_both_criteria_off_the_whole_bar(self) -> None:
        """The ordinary path, and the intraday reading arriving through the envelope.

        One session traded far above where it closed. The closing series never saw it and the
        envelope qualified the stock; the tape saw it, and the stock is a third below what it
        actually traded at.
        """

        closes = np.linspace(60.0, 150.0, 300).tolist()
        highs = [close * 1.01 for close in closes]

        clean = qualify(history(closes))
        self.assertEqual(clean["data"]["eligibility_state"], "eligible")

        highs[200] = 225.0
        spiked = qualify(history(closes, highs=highs))

        self.assertEqual(spiked["data"]["eligibility_state"], "avoid")
        near_high = criteria(spiked)[NEAR_HIGH]
        self.assertEqual(near_high["state"], "fail")
        self.assertAlmostEqual(near_high["basis"]["measured"], (1 - closes[-1] / 225.0) * 100, places=4)


if __name__ == "__main__":
    unittest.main()
