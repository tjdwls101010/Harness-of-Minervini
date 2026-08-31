"""A claim's `context` says which analysis it is doctrine for. The envelope has to agree.

`_named_doctrine_ids` publishes every claim a result names, and nothing checked those names
against the contexts the registry registered them under. An active verdict cited the
base-count claims, which were registered `prospective_entry` and `setup` only -- so the
registry was short two contexts. Counting bases is perspective on where a stage 2 advance
stands, and the source says so without reference to whether anybody holds the stock.

Both modes are also a `risk` analysis, which is how a prospective verdict reporting the 3R
breakeven trigger is in context for a claim registered `active_position` and `risk`: the
control it publishes is part of the plan being proposed, and the claim covers it.
"""

from __future__ import annotations

import unittest

from scripts.minervini import doctrine
from scripts.minervini.operations import Runtime, execute


AS_OF = "2026-08-28"
# Which registry contexts each ticker.risk mode is an instance of.
MODE_CONTEXTS = {
    "prospective": {"prospective_entry", "risk"},
    "active": {"active_position", "trade_management", "risk"},
}
REQUESTS = {
    "prospective": {
        "ticker": "AAPL",
        "as_of": AS_OF,
        "base_count": 4,
        "entry_price": 100.0,
        "stop_price": 94.0,
        "upside_price": 112.0,
        "average_gain_pct": 20.0,
    },
    "active": {"ticker": "AAPL", "as_of": AS_OF, "mode": "active", "base_count": 4},
}


class EveryCitationSitsInsideItsOwnRegisteredContext(unittest.TestCase):
    def test_no_verdict_cites_a_claim_registered_for_some_other_analysis(self) -> None:
        drift = set()
        for mode, request in REQUESTS.items():
            payload = execute("ticker.risk", request, runtime=Runtime())
            self.assertTrue(payload["doctrine_ids"], f"{mode} cited nothing")
            for claim_id in payload["doctrine_ids"]:
                registered = set(doctrine.get_claim(claim_id)["claim"]["context"])
                if not registered & MODE_CONTEXTS[mode]:
                    drift.add((mode, claim_id))

        self.assertEqual(drift, set())

    def test_the_base_count_claims_are_registered_for_both_analyses(self) -> None:
        """They are cited by an entry decision and by a position being held, and are doctrine for both."""

        for claim_id in ("basecount.role_and_disclaimer", "basecount.typical_top_after_3_to_5_bases"):
            with self.subTest(claim=claim_id):
                registered = set(doctrine.get_claim(claim_id)["claim"]["context"])

                self.assertLessEqual({"prospective_entry", "setup", "active_position", "trade_management"}, registered)


if __name__ == "__main__":
    unittest.main()
