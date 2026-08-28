"""BUY-READY is reached from component envelopes or it is not reached.

The unit seam settles what the reducer will accept. This one settles the channel: what
`ticker.risk` does with the envelopes a caller attaches, and what it does with the ones that
look right and are not. An envelope about another stock and an envelope from another session
are the two ways a real one goes wrong -- both were produced by a capability that worked, and
neither is distinguishable from a good one without comparing it to the request it is being
attached to.
"""

from __future__ import annotations

import unittest

from scripts.minervini.contracts import RequestError
from scripts.minervini.operations import execute


TICKER = "TEST"
AS_OF = "2025-12-31"


def envelope(operation: str, data: dict, *, as_of: str = AS_OF, status: str = "ok") -> dict:
    """A component envelope in the shape its capability returns one."""

    return {
        "schema_version": "2.0.0",
        "operation": operation,
        "request": {"ticker": data.get("ticker")},
        "as_of": {"mode": "explicit", "date": as_of, "timezone": "America/New_York", "completed_session": True},
        "status": status,
        "data": data,
    }


def market(judgment: str = "favorable", **kwargs) -> dict:
    return envelope("market.snapshot", {"regime": {"judgment": judgment}}, **kwargs)


def qualify(state: str = "eligible", *, ticker: str = TICKER, **kwargs) -> dict:
    return envelope("ticker.qualify", {"ticker": ticker, "eligibility_state": state}, **kwargs)


def setup(state: str = "ready", *, ticker: str = TICKER, **kwargs) -> dict:
    return envelope("ticker.setup", {"ticker": ticker, "setup_state": state}, **kwargs)


def fundamentals(state: str = "supports_convergence", *, ticker: str = TICKER, **kwargs) -> dict:
    return envelope("ticker.fundamentals", {"ticker": ticker, "fundamentals_state": state}, **kwargs)


def risk(evidence: list[dict], **overrides) -> dict:
    request = {
        "ticker": TICKER,
        "as_of": AS_OF,
        "evidence": evidence,
        "entry_price": 200.0,
        "stop_price": 188.0,
        "upside_price": 224.0,
        "average_gain_pct": 24.0,
    }
    request.update(overrides)
    return execute("ticker.risk", request)


class AVerdictIsReducedFromEnvelopes(unittest.TestCase):
    def test_the_four_envelopes_reach_buy_ready(self) -> None:
        payload = risk([market(), qualify(), setup(), fundamentals()])

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["data"]["verdict"], "BUY-READY")
        self.assertEqual(payload["missing"], [])

    def test_the_request_echoes_which_capability_vouched_for_each_plane(self) -> None:
        """A reader auditing the verdict needs the references, not four whole envelopes."""

        payload = risk([market(), qualify(), setup(), fundamentals()])

        self.assertEqual(
            [(item["plane"], item["operation"], item["as_of"]) for item in payload["request"]["evidence"]],
            [
                ("market", "market.snapshot", AS_OF),
                ("eligibility", "ticker.qualify", AS_OF),
                ("setup", "ticker.setup", AS_OF),
                ("fundamentals", "ticker.fundamentals", AS_OF),
            ],
        )

    def test_an_envelope_about_another_stock_leaves_its_plane_unattested(self) -> None:
        payload = risk([market(), qualify(ticker="OTHER"), setup(), fundamentals()])

        self.assertEqual(payload["data"]["verdict"], "INCOMPLETE")
        self.assertIn("eligibility", payload["data"]["unattested"])
        refused = [item for item in payload["request"]["evidence"] if item.get("refused")]
        self.assertEqual([item["refused"] for item in refused], ["envelope_is_about_another_ticker"])

    def test_an_envelope_from_another_session_leaves_its_plane_unattested(self) -> None:
        payload = risk([market(), qualify(), setup(as_of="2025-12-30"), fundamentals()])

        self.assertEqual(payload["data"]["verdict"], "INCOMPLETE")
        self.assertIn("setup", payload["data"]["unattested"])

    def test_the_envelope_word_wins_over_the_word_typed_beside_it(self) -> None:
        """The caller declares eligible; the envelope they attached says avoid."""

        payload = risk([market(), qualify("avoid"), setup(), fundamentals()], eligibility={"state": "eligible"})

        self.assertEqual(payload["data"]["verdict"], "AVOID")
        self.assertIn("eligibility", payload["data"]["failed"])

    def test_a_capability_that_settles_no_plane_is_refused_by_name(self) -> None:
        with self.assertRaises(RequestError) as raised:
            risk([envelope("ticker.peers", {"ticker": TICKER})])

        self.assertEqual(raised.exception.field, "evidence")
        self.assertIn("ticker.peers", raised.exception.message)


if __name__ == "__main__":
    unittest.main()
