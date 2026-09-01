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

# Registered, resolvable, and nothing the capability under test reads: the shape a forgery
# takes. One per capability, because a claim the reducer cites on its own proves nothing --
# `risk.hard_stop_and_no_average_down` is the active mode's own base and would be in the list
# whether the forgery worked or not.
_UNRELATED_TO_A_SETUP = "risk.hard_stop_and_no_average_down"
_UNRELATED_TO_AN_ACTIVE_POSITION = "risk.initial_stop_and_reward"


class ACallerCannotForgeACitation(unittest.TestCase):
    def _setup(self, **extra: object) -> dict:
        with tempfile.TemporaryDirectory() as temporary:
            runtime = _VOCABULARY.measured(pathlib.Path(temporary) / "ledger.sqlite3")
            return execute("ticker.setup", {**_VOCABULARY.REQUESTS["ticker.setup"], **extra}, runtime=runtime)

    def test_a_claim_named_in_a_callers_entry_is_not_cited(self) -> None:
        payload = self._setup(entry={"doctrine_id": _UNRELATED_TO_A_SETUP})

        self.assertEqual(payload["data"]["entry"]["doctrine_id"], _UNRELATED_TO_A_SETUP, "the caller's object is still echoed")
        self.assertNotIn(_UNRELATED_TO_A_SETUP, payload["doctrine_ids"])

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

    def test_the_citation_list_is_the_same_with_the_forgery_and_without(self) -> None:
        """Equality rather than a subset in either direction: a forged claim must not be added,
        and the attempt must not knock a real one out either."""

        self.assertEqual(
            set(self._setup()["doctrine_ids"]),
            set(self._setup(entry={"doctrine_id": _UNRELATED_TO_A_SETUP})["doctrine_ids"]),
        )

    def _risk(self, **extra: object) -> dict:
        with tempfile.TemporaryDirectory() as temporary:
            runtime = _VOCABULARY.measured(pathlib.Path(temporary) / "ledger.sqlite3")
            return execute("ticker.risk", {**_VOCABULARY.REQUESTS["ticker.risk"], **extra}, runtime=runtime)

    def test_a_claim_named_in_a_callers_price_path_is_not_cited(self) -> None:
        """`ticker.setup` was narrowed and `ticker.risk` was not, which is the same hole in the
        capability that publishes a verdict about a live position. The audit a caller supplies
        for the completed price path is echoed back into `data` and was harvested from there."""

        forged = {
            "state": "breached",
            "basis": "completed_daily_low",
            "breach_date": "2025-12-01",
            "checked_level": 85.0,
            "governing_role": "stop",
            "breach_low": 84.0,
            "doctrine_id": _UNRELATED_TO_AN_ACTIVE_POSITION,
        }
        payload = self._risk(completed_price_path=forged)

        self.assertEqual(payload["data"]["completed_price_path"]["doctrine_id"], _UNRELATED_TO_AN_ACTIVE_POSITION)
        self.assertNotIn(_UNRELATED_TO_AN_ACTIVE_POSITION, payload["doctrine_ids"])

    def test_a_claim_named_in_any_echoed_request_field_is_not_cited(self) -> None:
        """Not one field. Every top-level key the caller sent that the payload sends back is an
        echo, and a blacklist of the two found by hand is a list that goes stale by one."""

        for field in ("max_high_withheld_reason", "max_high_withheld_date"):
            with self.subTest(field=field):
                payload = self._risk(**{field: {"doctrine_id": _UNRELATED_TO_AN_ACTIVE_POSITION}})
                self.assertNotIn(_UNRELATED_TO_AN_ACTIVE_POSITION, payload["doctrine_ids"])

    def test_the_claims_the_risk_reducer_read_are_still_cited(self) -> None:
        cited = set(self._risk()["doctrine_ids"])
        self.assertLessEqual(
            {"risk.hard_stop_and_no_average_down", "management.market_defense_tightens_stops", "setup.closing_range_formula"},
            cited,
        )


if __name__ == "__main__":
    unittest.main()
