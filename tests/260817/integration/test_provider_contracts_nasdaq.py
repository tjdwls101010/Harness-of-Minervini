"""Behavior checks for provider contracts nasdaq."""

from __future__ import annotations

import unittest
from scripts.minervini.providers import ProviderUnavailable
from scripts.minervini.providers.nasdaq import historical_security_master, parse_current_security_master
from ._provider_fixtures import FIXTURES


class ProviderContractTests(unittest.TestCase):

    def test_nasdaq_current_parser_marks_only_supported_common_and_adr_instruments_eligible(self) -> None:
        document = FIXTURES.joinpath("nasdaqlisted.txt").read_text()

        records = parse_current_security_master(document)
        by_symbol = {record.symbol: record for record in records}

        self.assertTrue(by_symbol["AAPL"].eligible)
        self.assertTrue(by_symbol["NIO"].eligible)
        self.assertTrue(by_symbol["NIO"].is_adr)
        self.assertFalse(by_symbol["TQQQ"].eligible)
        self.assertEqual(by_symbol["TQQQ"].exclusion_reason, "etf")
        self.assertFalse(by_symbol["SPACU"].eligible)
        self.assertEqual(by_symbol["SPACU"].exclusion_reason, "unit")

    def test_nasdaq_historical_security_master_is_honestly_unavailable(self) -> None:
        with self.assertRaises(ProviderUnavailable) as raised:
            historical_security_master("2026-08-12")

        self.assertEqual(raised.exception.reason, "historical_security_master_unavailable")
