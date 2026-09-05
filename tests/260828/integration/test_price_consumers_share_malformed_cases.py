"""Every price consumer faces the same malformed histories under its own reader contract."""

import unittest
from datetime import date

from scripts.minervini.peer_collection import _price_evidence
from scripts.minervini.setup_structure import read_bars, read_price_kinds
from tests.malformed import AS_OF, CASES
from .test_qualify_reads_the_bars_the_rest_of_the_harness_reads import qualify
from .test_risk_reads_the_bars_the_rest_of_the_harness_reads import risk
from . import test_the_market_reads_the_bars_the_rest_of_the_harness_reads as market_tests


class EveryPriceConsumerRespectsItsReader(unittest.TestCase):
    pass


def case_test(surface, build, whole_reason, narrow_reason):
    def test(self):
        history = build()
        self.assertEqual(read_bars(history)[1], whole_reason)
        if surface == "qualify":
            payload = qualify(history)
            self.assertEqual(payload["status"], "unavailable")
            self.assertEqual(payload["data"]["eligibility_state"], "incomplete")
            self.assertEqual([item["reason"] for item in payload["missing"]], [whole_reason])
        elif surface == "peer":
            self.assertIsNone(_price_evidence(history, date.fromisoformat(AS_OF)))
        elif surface == "market":
            payload = market_tests.TheRegimeIsNotReducedFromUnreadableBars().snapshot_from(history)
            self.assertEqual(payload["data"]["leaders"][0]["behavior"]["state"], "unavailable")
            self.assertEqual([item["reason"] for item in payload["missing"] if item.get("ticker") == "LEAD"], [whole_reason])
        else:
            self.assertEqual(read_price_kinds(history, columns=("Open", "High", "Low", "Close"))[1], narrow_reason)
            payload = risk(history)
            named = [item["reason"] for item in payload["missing"] if item["id"] == "usable_daily_bars"]
            if narrow_reason is None:
                self.assertEqual(named, [])
                self.assertEqual(payload["data"]["verdict"], "HOLD")
                self.assertEqual(payload["data"]["completed_price_path"]["state"], "clear")
            else:
                self.assertNotIn(payload["data"]["verdict"], {"HOLD", "SELL"})
                self.assertEqual(named, [narrow_reason])
    return test


for case, (build, whole_reason, narrow_reason) in CASES.items():
    for surface in ("qualify", "peer", "market", "risk"):
        setattr(EveryPriceConsumerRespectsItsReader, "test_" + surface + "_" + case, case_test(surface, build, whole_reason, narrow_reason))
