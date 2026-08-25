"""What an approval would be bound to has to include what the verdict turns on.

The shared bars fingerprint covers the five price columns, which is the right answer for the three
surfaces that share a chain: they measure price. This capability also measures events -- a split
inside the span leaves it deciding nothing, and a payout inside it withholds the criteria it
decided -- and two histories with identical prices and different events digest the same under it.
An approval bound to that digest would not be bound to the evidence the verdict was reached on.
"""

from __future__ import annotations

import unittest

from scripts.minervini.power_play_evidence import power_play_fingerprint
from scripts.minervini.setup_structure import bars_fingerprint
from tests.series import power_play_series


class TheEventsArePartOfTheInput(unittest.TestCase):
    def _pair(self):
        plain = power_play_series()
        split = power_play_series()
        split.iloc[-8, split.columns.get_loc("Stock Splits")] = 2.0
        return plain, split

    def test_the_shared_digest_cannot_tell_them_apart(self) -> None:
        plain, split = self._pair()

        self.assertEqual(bars_fingerprint(plain), bars_fingerprint(split))

    def test_this_capability_s_digest_can(self) -> None:
        plain, split = self._pair()

        self.assertNotEqual(power_play_fingerprint(plain), power_play_fingerprint(split))

    def test_a_payout_changes_it_too(self) -> None:
        plain = power_play_series()
        paying = power_play_series()
        paying.iloc[-8, paying.columns.get_loc("Dividends")] = 0.42

        self.assertNotEqual(power_play_fingerprint(plain), power_play_fingerprint(paying))

    def test_the_same_history_digests_the_same(self) -> None:
        self.assertEqual(power_play_fingerprint(power_play_series()), power_play_fingerprint(power_play_series()))

    def test_a_history_with_no_event_columns_has_no_digest_to_give(self) -> None:
        """Absent columns are a gap, not a promise that nothing happened.

        Digesting them as zeroes would make a history that never said whether a split occurred
        indistinguishable from one that said none did -- the same substitution the reducer already
        refuses to make when it decides.
        """
        bare = power_play_series().drop(columns=["Stock Splits", "Dividends"])

        self.assertIsNone(power_play_fingerprint(bare))


class TheDigestTravelsWithTheAnswer(unittest.TestCase):
    def test_the_envelope_names_the_input_an_approval_would_be_bound_to(self) -> None:
        """Reported before anything can be approved against it.

        A caller cannot bind an approval to bars they were never told the name of, and a reader
        auditing an approval later needs the name the verdict was reached under, not the one the
        chart happened to be drawn from.
        """
        from datetime import datetime, timezone

        from scripts.minervini.operations import Runtime, execute
        from scripts.minervini.providers import ProviderSnapshot, SnapshotMeta

        frame = power_play_series()
        prices = ProviderSnapshot(
            frame,
            SnapshotMeta(
                provider="fixture-prices",
                retrieved_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
                as_of=frame.index[-1].date(),
                coverage={"completed_only": True, "corporate_actions": True, "distributions": True},
            ),
        )
        payload = execute(
            "ticker.power-play",
            {"ticker": "TEST", "as_of": prices.meta.as_of.isoformat(), "no_cache": True},
            runtime=Runtime(price_history=lambda ticker, requested: prices),
        )

        self.assertEqual(payload["data"]["measured_bars"], power_play_fingerprint(frame))
