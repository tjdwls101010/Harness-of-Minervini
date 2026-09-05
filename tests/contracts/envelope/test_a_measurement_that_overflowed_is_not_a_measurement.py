"""Arithmetic that ran off the end of a float is reported as a gap, not as an answer.

The readers now refuse values that are not prices. These are the ones that are: every input
below is a finite positive real number the shared reader accepts, and the arithmetic on top of
it leaves the float range. What comes back is `nan` and `inf`, and nothing downstream was
looking for either.

`nan` is the dangerous one, because every comparison against it is False. A 200-day average
that overflowed reads as an average the price failed to exceed, so a history that qualifies on
all eight criteria comes back AVOID -- a hard gate decided by an arithmetic accident. `inf` is
the loud one: it reaches the envelope, and the CLI serialises with `allow_nan=False`, so the
caller gets a traceback instead of any envelope at all. This capability's whole contract is
that every command emits exactly one of those.

Real prices reach neither. Across 48 names in six industries the harness measured today, no
derived value came close to the float range. What makes these worth closing is not their
frequency but their shape: one turns an unmeasurable quantity into a verdict, and the other
takes away the envelope that would have said so.
"""

from __future__ import annotations

from tests.providers import rows_snapshot

from datetime import date, datetime, timezone
import unittest
import numpy as np
import pandas as pd

from scripts.minervini.operations import Runtime, execute
from scripts.minervini.peer_collection import _price_evidence

from scripts.minervini.setup_structure import read_bars


AS_OF = "2025-12-31"


def frame(closes: list[float]) -> pd.DataFrame:
    index = pd.bdate_range(end=AS_OF, periods=len(closes))
    close = pd.Series(closes, index=index, dtype=float)
    return pd.DataFrame(
        {"Open": close, "High": close, "Low": close, "Close": close, "Volume": np.full(len(close), 1_000_000.0)},
        index=index,
    )


def tiny_inside_the_year() -> np.ndarray:
    """One session at the bottom of the float range, inside the 52-week window that reads it."""

    closes = np.linspace(50.0, 150.0, 260)
    closes[20] = 1e-320
    return closes


def snapshot(payload, provider: str):
    return rows_snapshot(payload, provider=provider, retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc), as_of=date.fromisoformat(AS_OF), coverage={"completed_only": True})


def qualify(history: pd.DataFrame) -> dict:
    return execute(
        "ticker.qualify",
        {"ticker": "TEST", "as_of": AS_OF},
        runtime=Runtime(
            price_history=lambda ticker, as_of: snapshot(history, "fixture-prices"),
            rs_rating=lambda ticker, as_of: snapshot({"rating": 94, "rating_date": AS_OF}, "ibd-rs-rating"),
        ),
    )


class AnAverageThatOverflowedIsNotAnAverage(unittest.TestCase):
    def test_a_rising_history_of_very_large_prices_is_not_read_as_a_failed_trend(self) -> None:
        """Every criterion passes on these numbers; the rolling sum is what leaves the range.

        `nan > anything` is False, so the overflow arrives dressed as evidence the price sits
        below its averages -- a Stage 2 failure the history does not contain.
        """

        history = frame(np.linspace(1e307, 9e307, 260).tolist())
        self.assertIsNone(read_bars(history)[1])

        payload = qualify(history)

        self.assertNotEqual(payload["data"]["eligibility_state"], "avoid")
        self.assertNotEqual(payload["status"], "ok")

    def test_an_envelope_never_carries_a_number_json_cannot_hold(self) -> None:
        """The CLI serialises with `allow_nan=False`, so one of these loses the envelope."""

        for description, closes in {
            "prices near the top of the float range": np.linspace(1e307, 9e307, 260).tolist(),
            "one price near the bottom of it": tiny_inside_the_year().tolist(),
        }.items():
            with self.subTest(history=description):
                payload = qualify(frame(closes))

                for signal in payload.get("signals", []):
                    measured = signal.get("basis", {}).get("measured")
                    if isinstance(measured, float):
                        self.assertTrue(np.isfinite(measured), f"{signal['id']} published {measured}")

    def test_a_gate_that_could_not_be_measured_is_a_gap_the_envelope_reports(self) -> None:
        """`status: ok` beside `eligibility_state: incomplete` is the envelope contradicting itself.

        The reducer knew the criterion was unmeasurable -- the registry's own word for it is
        `measurement_not_finite` -- and the envelope's status was decided from provider gaps
        alone, so a reading that measured seven of eight criteria claimed to be complete.
        """

        payload = qualify(frame(tiny_inside_the_year().tolist()))

        self.assertEqual(payload["data"]["eligibility_state"], "incomplete")
        self.assertNotEqual(payload["status"], "ok")
        self.assertTrue(payload["missing"], "an incomplete reading named no gap")


class AnExceptionTheRouteGrantsIsNotAGap(unittest.TestCase):
    """The other direction, and the one this fix opened before the round closed it.

    The recent-IPO route exists for a stock with too little history to have a 200-day average,
    and it reaches `eligible` on a Primary Base instead. Those five long-history criteria are
    unavailable by the route's own design, so reporting them as required evidence makes an
    envelope that qualified a stock and simultaneously claims required evidence is missing.

    A criterion nobody could measure is a gap only where the reading needed it, which is the
    reading that could not reach a verdict.
    """

    def test_a_stock_qualified_through_the_ipo_route_names_no_missing_evidence(self) -> None:
        peak, trough, last = 100.0, 75.0, 99.0
        closes = [60.0 + position for position in range(20)] + [peak, trough]
        step = (peak * 0.99 - trough) / (120 - 20 - 3 + 1)
        closes.extend(trough + step * (position + 1) for position in range(120 - 20 - 3))
        closes.append(last)

        payload = execute(
            "ticker.qualify",
            {"ticker": "TEST", "as_of": AS_OF, "primary_base_quality": "supports", "primary_base_emergence": "near_high_consolidation"},
            runtime=Runtime(
                price_history=lambda ticker, as_of: snapshot(frame(closes), "fixture-prices"),
                rs_rating=lambda ticker, as_of: snapshot({"rating": 94, "rating_date": AS_OF}, "ibd-rs-rating"),
            ),
        )

        self.assertEqual(payload["data"]["route"], "recent_ipo_primary_base")
        self.assertEqual(payload["data"]["eligibility_state"], "eligible")
        self.assertEqual(payload["missing"], [])
        self.assertEqual(payload["status"], "ok")


class ARatioThatOverflowedIsNotAReturn(unittest.TestCase):
    def test_a_peer_whose_three_month_return_left_the_float_range_measures_nothing(self) -> None:
        """Both closes are finite and positive; their ratio is not."""

        history = frame([1e-308] * 399 + [1e308])
        self.assertIsNone(read_bars(history)[1])

        self.assertIsNone(_price_evidence(history, date.fromisoformat(AS_OF)))


if __name__ == "__main__":
    unittest.main()
