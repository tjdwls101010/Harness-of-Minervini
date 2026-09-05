"""The eligibility gate measures the same bars every other surface refuses to measure.

`setup_structure.read_bars` is the harness's one definition of a usable price history. It
was made the owner after a slice whose defects all shared one root -- values, dtypes,
timezones and index representations quietly becoming numbers or dates, and then moving
between surfaces with a different meaning. Five surfaces read through it. `ticker.qualify`
does not, and it is the hard gate: eight Trend Template criteria and Stage 2, the AND gate
that rejects a candidate before any deeper work runs.

Its own reading is `pd.to_numeric(history["Close"], errors="coerce").dropna()`, which is
precisely the laundering that reading was written to stop. Every history below is one the
shared reader names and refuses; every one of them is measured here instead, and the
envelope says `ok` beside the answer.

Two of them are worse than a wrong number. A history whose closes are half holes is
measured on the survivors, so a data gap is read as a short history and the capability
switches to the recent-IPO route -- an AVOID reached through the exception that exists for
genuinely young stocks. And a provider that prints every session twice is measured over
twice as many rows, so the 200-session average the source asks for spans a hundred trading
days. Both contradict the constitution's own line: unavailable evidence produces
INCOMPLETE, never a guessed pass or fail.
"""

from __future__ import annotations

from tests.providers import rows_snapshot

from datetime import date, datetime, timezone
import unittest
import pandas as pd

from tests.malformed import doubled, holed, positional_index, rising
from scripts.minervini.operations import Runtime, execute


AS_OF = "2025-12-31"


def _snapshot(payload, provider: str):
    return rows_snapshot(payload, provider=provider, retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc), as_of=date.fromisoformat(AS_OF), coverage={"completed_only": True})


def qualify(history: pd.DataFrame) -> dict:
    return execute(
        "ticker.qualify",
        {"ticker": "TEST", "as_of": AS_OF},
        runtime=Runtime(
            price_history=lambda ticker, as_of: _snapshot(history, "fixture-prices"),
            rs_rating=lambda ticker, as_of: _snapshot({"rating": 95, "rating_date": AS_OF}, "ibd-rs-rating"),
        ),
    )


class TheGateRefusesWhatItCannotRead(unittest.TestCase):
    def test_the_clean_history_still_qualifies(self) -> None:
        """The route that was always earned, so every refusal below is the history and not the fix."""

        payload = qualify(rising())

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["data"]["eligibility_state"], "eligible")
        self.assertEqual(payload["data"]["completed_session_count"], 300)


    def test_a_history_with_holes_does_not_become_a_young_stock(self) -> None:
        """The recent-IPO route is an exception for a stock with no long history, not for a gap.

        Dropping the unreadable closes leaves 150 rows, and 150 rows is below the 200 the
        standard route needs -- so the capability took the route reserved for a stock that has
        not existed long enough to have those sessions. This history has 300 sessions and the
        harness could not read half of them, which is a different fact entirely.
        """

        payload = qualify(holed())

        self.assertNotEqual(payload["data"].get("route"), "recent_ipo_primary_base")

    def test_a_doubled_history_does_not_publish_a_session_count_it_did_not_measure(self) -> None:
        """600 rows over 300 sessions, and the 200-session average would span 100 trading days."""

        payload = qualify(doubled())

        self.assertNotEqual(payload["data"].get("completed_session_count"), 600)

    def test_the_published_session_date_is_a_session_date(self) -> None:
        """`price_as_of` is the row label stringified, so a positional index publishes "299"."""

        published = qualify(positional_index())["data"].get("price_as_of")

        self.assertNotEqual(published, "299")


if __name__ == "__main__":
    unittest.main()
