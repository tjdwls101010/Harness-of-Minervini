"""Two ways this capability's honesty leaked back out.

`ticker.fundamentals` on a past session points at `ticker.cik`, and `ticker.cik` refuses a past
session -- correctly, because today's symbol map is not evidence about who filed under it then.
Followed literally, the pointer therefore lands on the same refusal it came from. The pointer is
right: a CIK does come from here. What was missing is the step between them, so the refusal
carries it rather than leaving an analyst to infer that dropping the date is what works.

And the map this capability reads is a mutable current snapshot, which is the whole reason it
declines to answer for a past session. Cached without a lifetime it was frozen for the rest of
the completed session anyway -- the harness holding a current fact still while saying that being
current is what makes it unusable a day later. Every other current-only snapshot here already
carries the same fifteen minutes.
"""

from __future__ import annotations

from tests.providers import rows_snapshot

from datetime import datetime, timedelta, timezone
import pathlib
import tempfile
import unittest

from scripts.minervini.cache import ProviderCache
from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot


PAST = "2025-08-14"


def _snapshot(cik: str) -> ProviderSnapshot[dict[str, dict[str, str]]]:
    return rows_snapshot({"AAPL": {"cik": cik, "title": "Apple Inc."}}, provider="sec", retrieved_at=datetime(2026, 8, 28, tzinfo=timezone.utc), as_of=None, coverage={"kind": "mutable_current_only"}, content_sha256=cik * 6)


class ARefusalSaysWhatWorks(unittest.TestCase):
    def test_the_capability_the_gap_points_at_says_how_to_reach_an_answer(self) -> None:
        """Chained with the same request, the pointer lands here. It has to terminate."""

        pointed_at = execute("ticker.fundamentals", {"ticker": "AAPL", "as_of": PAST}, runtime=Runtime())
        self.assertEqual(pointed_at["next_capabilities"], ["ticker.cik"])

        followed = execute(
            "ticker.cik",
            {"ticker": "AAPL", "as_of": PAST},
            runtime=Runtime(company_tickers=lambda: _snapshot("0000320193")),
        )

        self.assertEqual(followed["status"], "unavailable")
        gap = followed["missing"][0]
        self.assertEqual(gap["reason"], "ticker_to_cik_map_is_current_only")
        self.assertIn("current session", gap["detail"])


class ACurrentSnapshotIsNotHeldStill(unittest.TestCase):
    def test_the_symbol_map_expires_the_way_every_other_current_snapshot_does(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            answers = iter(("0000000001", "0000000002"))
            clock = [datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)]
            cache = ProviderCache(pathlib.Path(temporary), now=lambda: clock[0])
            runtime = Runtime(company_tickers=lambda: _snapshot(next(answers)), cache=cache)

            first = execute("ticker.cik", {"ticker": "AAPL"}, runtime=runtime)
            cached = execute("ticker.cik", {"ticker": "AAPL"}, runtime=runtime)
            clock[0] += timedelta(seconds=901)
            refetched = execute("ticker.cik", {"ticker": "AAPL"}, runtime=runtime)

        self.assertEqual(first["data"]["cik"], "0000000001")
        self.assertEqual(cached["data"]["cik"], "0000000001", "the cache is still doing its job")
        self.assertEqual(refetched["data"]["cik"], "0000000002")


if __name__ == "__main__":
    unittest.main()
