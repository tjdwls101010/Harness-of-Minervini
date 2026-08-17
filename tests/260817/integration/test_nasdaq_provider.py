from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from importlib import resources
import unittest

from scripts.minervini.providers.nasdaq import current_security_master


FIXTURES = resources.files("tests.260817.fixtures.providers.nasdaq")


class NasdaqSecurityMasterProviderTests(unittest.TestCase):
    def test_current_master_combines_official_lists_with_auditable_source_metadata(self) -> None:
        documents = {
            "nasdaqlisted.txt": FIXTURES.joinpath("nasdaqlisted.txt").read_text(),
            "otherlisted.txt": FIXTURES.joinpath("otherlisted.txt").read_text(),
        }
        requested_urls: list[str] = []

        def request(url: str) -> str:
            requested_urls.append(url)
            return documents[url.rsplit("/", 1)[-1]]

        retrieved_at = datetime(2026, 8, 17, 22, 0, tzinfo=timezone.utc)
        snapshot = current_security_master(request=request, retrieved_at=retrieved_at)
        records = {(record.exchange, record.symbol): record for record in snapshot.data}

        self.assertEqual(
            requested_urls,
            [
                "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
                "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
            ],
        )
        self.assertEqual(set(records), {("NASDAQ", "AAPL"), ("NASDAQ", "NIO"), ("NYSE", "IBM"), ("NYSE", "BABA"), ("NYSE Arca", "SPY")})
        self.assertEqual(records[("NYSE", "IBM")].instrument_id, "nasdaq-trader:NYSE:IBM")
        self.assertTrue(records[("NASDAQ", "NIO")].is_adr)
        self.assertTrue(records[("NYSE", "BABA")].is_adr)
        self.assertFalse(records[("NYSE Arca", "SPY")].eligible)
        self.assertEqual(records[("NYSE Arca", "SPY")].exclusion_reason, "etf")
        self.assertEqual(snapshot.meta.retrieved_at, retrieved_at)
        self.assertFalse(snapshot.meta.coverage["historical"])
        self.assertEqual(snapshot.meta.coverage["sources"]["otherlisted.txt"]["url"], requested_urls[1])
        self.assertEqual(snapshot.meta.coverage["sources"]["nasdaqlisted.txt"]["content_sha256"], sha256(documents["nasdaqlisted.txt"].encode()).hexdigest())

    def test_current_master_retries_the_two_document_request_boundary_once(self) -> None:
        documents = {
            "nasdaqlisted.txt": FIXTURES.joinpath("nasdaqlisted.txt").read_text(),
            "otherlisted.txt": FIXTURES.joinpath("otherlisted.txt").read_text(),
        }
        requested_urls: list[str] = []

        def request(url: str) -> str:
            requested_urls.append(url)
            if url.endswith("otherlisted.txt") and requested_urls.count(url) == 1:
                raise TimeoutError("frozen boundary timeout")
            return documents[url.rsplit("/", 1)[-1]]

        snapshot = current_security_master(request=request, retrieved_at=datetime(2026, 8, 17, 22, 0, tzinfo=timezone.utc))

        self.assertEqual(len(requested_urls), 4)
        self.assertEqual(requested_urls.count("https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"), 2)
        self.assertEqual(requested_urls.count("https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"), 2)
        self.assertEqual(len(snapshot.data), 5)


if __name__ == "__main__":
    unittest.main()
