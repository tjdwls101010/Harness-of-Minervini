"""A component word nobody measured cannot mint the harness's terminal buy verdict.

`ticker.risk` mints the only BUY-READY this harness produces, and it reads four component
planes -- market, eligibility, setup, fundamentals -- from whatever the caller handed it.
Today each of those is one word. Typed together they reach BUY-READY on a ticker that does
not exist, and the envelope's own `sources` list is empty beside the verdict: it reports
that it read nothing and rules anyway.

The rule that closes it is one sentence: a word the caller supplies may only move the
verdict toward no-trade. A declared failure still fails and a declared wait still waits --
both are conservative, and doctrine already produces AVOID from a known failure. What a
bare word can never do is pass, because passing is the one direction where being wrong
costs money. A pass has to come from the capability that measured it, carried in as a
reference to that envelope and cross-checked here against the ticker and the session being
reduced -- which is why the attestation is a reference and not a flag. `attested: true`
would be the same defect one level up: another word the caller can type.

This is the general case of the hole `tests/unit/risk/test_power_play_waiver.py` closed
for one plane. `waived_by_exception` was removed because "no reducer that reads
caller-supplied state words is in a position to check that it was" earned -- an argument
that was never about that one word.
"""

from __future__ import annotations

import unittest

from scripts.minervini.risk import reduce_risk


TICKER = "NVDA"
AS_OF = "2026-08-21"

_ATTESTING_OPERATION = {
    "market": "market.snapshot",
    "eligibility": "ticker.qualify",
    "setup": "ticker.setup",
    "fundamentals": "ticker.fundamentals",
}


def attested(plane: str, state: str, **overrides) -> dict:
    """The shape `ticker.risk` builds from a component envelope it verified."""

    reference = {
        "operation": _ATTESTING_OPERATION[plane],
        # The market is not measured per ticker, so its envelope names none.
        "ticker": None if plane == "market" else TICKER,
        "as_of": AS_OF,
        "status": "ok",
    }
    reference.update(overrides)
    return {"state": state, "attested_by": reference}


def prospective(**overrides) -> dict:
    evidence = {
        "mode": "prospective",
        "ticker": TICKER,
        "as_of": AS_OF,
        "market": attested("market", "favorable"),
        "eligibility": attested("eligibility", "eligible"),
        "setup": attested("setup", "ready"),
        "fundamentals": attested("fundamentals", "supports_convergence"),
        "entry_price": 100.0,
        "stop_price": 94.0,
        "upside_price": 112.0,
        "average_gain_pct": 12.0,
    }
    evidence.update(overrides)
    return reduce_risk(evidence)


class AWordIsNotAMeasurement(unittest.TestCase):
    def test_four_typed_words_do_not_reach_buy_ready(self) -> None:
        verdict = prospective(
            market="favorable",
            eligibility="eligible",
            setup="ready",
            fundamentals="supports_convergence",
        )

        self.assertNotEqual(verdict["verdict"], "BUY-READY")
        for plane in ("market", "eligibility", "setup", "fundamentals"):
            self.assertIn(plane, verdict["missing"], f"{plane} passed on a word alone")

    def test_the_attested_route_reaches_the_verdict_the_words_could_not(self) -> None:
        """The route that was always earned is untouched."""

        verdict = prospective()

        self.assertEqual(verdict["verdict"], "BUY-READY")
        self.assertEqual(verdict["missing"], [])

    def test_an_unattested_word_still_moves_the_verdict_toward_no_trade(self) -> None:
        """The direction a caller's word keeps: it can hurt, and only hurt.

        A trader who has read the market themselves and calls it defensive is telling the
        truth about their own judgment, and refusing that would make the harness argue a
        position more bullish than the person holding it.
        """

        self.assertEqual(prospective(eligibility="avoid")["verdict"], "AVOID")
        self.assertEqual(prospective(market="defensive")["verdict"], "WAIT")

    def test_an_attestation_for_another_ticker_does_not_vouch_for_this_one(self) -> None:
        verdict = prospective(eligibility=attested("eligibility", "eligible", ticker="AMD"))

        self.assertNotEqual(verdict["verdict"], "BUY-READY")
        self.assertIn("eligibility", verdict["unattested"])

    def test_an_attestation_from_another_session_does_not_vouch_for_this_one(self) -> None:
        verdict = prospective(setup=attested("setup", "ready", as_of="2026-08-20"))

        self.assertNotEqual(verdict["verdict"], "BUY-READY")
        self.assertIn("setup", verdict["unattested"])

    def test_one_plane_cannot_vouch_for_another(self) -> None:
        """A setup envelope says nothing about eligibility, whatever word it carries."""

        verdict = prospective(eligibility=attested("setup", "eligible"))

        self.assertNotEqual(verdict["verdict"], "BUY-READY")
        self.assertIn("eligibility", verdict["unattested"])

    def test_an_envelope_that_could_not_measure_vouches_for_nothing(self) -> None:
        verdict = prospective(fundamentals=attested("fundamentals", "supports_convergence", status="unavailable"))

        self.assertNotEqual(verdict["verdict"], "BUY-READY")
        self.assertIn("fundamentals", verdict["unattested"])


if __name__ == "__main__":
    unittest.main()
