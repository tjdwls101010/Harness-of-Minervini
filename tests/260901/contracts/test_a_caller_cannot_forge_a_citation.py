"""A citation says this harness applied a claim, so a caller must not be able to add one.

`_named_doctrine_ids` harvests every registered claim id the payload names, which is right for
blocks the reducers built and wrong for anything that arrived from the caller and is echoed
back. `ticker.setup` publishes the caller's `entry` object verbatim, so harvesting the whole
payload let a request name any registered claim and have the envelope report it as doctrine
the setup was decided under. Decision 301 accepts it, because it resolves; the read-and-cited
guard accepts it, because it only looks for citations that are missing.

The fix is to harvest the reducer's own evidence rather than the published payload, so this
test is about which object the harvest reads and would go green again the moment that widens.
"""

from __future__ import annotations

import importlib
import pathlib
import tempfile
import unittest

from scripts.minervini.operations import execute


_VOCABULARY = importlib.import_module("tests.260828.contracts.test_a_declared_vocabulary_matches_the_envelopes")

# Registered, resolvable, and nothing to do with a setup: the shape a forgery would take.
_UNRELATED = "risk.hard_stop_and_no_average_down"


class ACallerCannotForgeACitation(unittest.TestCase):
    def _setup(self, **extra: object) -> dict:
        with tempfile.TemporaryDirectory() as temporary:
            runtime = _VOCABULARY.measured(pathlib.Path(temporary) / "ledger.sqlite3")
            return execute("ticker.setup", {**_VOCABULARY.REQUESTS["ticker.setup"], **extra}, runtime=runtime)

    def test_a_claim_named_in_a_callers_entry_is_not_cited(self) -> None:
        payload = self._setup(entry={"doctrine_id": _UNRELATED})

        self.assertEqual(payload["data"]["entry"]["doctrine_id"], _UNRELATED, "the caller's object is still echoed")
        self.assertNotIn(_UNRELATED, payload["doctrine_ids"])

    def test_the_practitioners_the_reducer_read_are_still_cited(self) -> None:
        """The narrowing has to keep what it was widened for: the contrast block is the
        reducer's own reading and its claims were the gap that started this."""

        cited = set(self._setup()["doctrine_ids"])
        self.assertLessEqual(
            {
                "practitioners.breakout_volume.ryan_25pct_min_100_200pct_ideal",
                "practitioners.breakout_volume.zanger_50pct_over_20day_avg",
                "setup.closing_range_formula",
            },
            cited,
        )

    def test_a_forged_citation_does_not_displace_a_real_one(self) -> None:
        plain = set(self._setup()["doctrine_ids"])
        forged = set(self._setup(entry={"doctrine_id": _UNRELATED})["doctrine_ids"])
        self.assertEqual(forged - plain, set())


if __name__ == "__main__":
    unittest.main()
