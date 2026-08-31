"""A key every verdict carries has to be required, or its disappearance is legal.

`data_core` is what `schema_sync` turns into the schema's `required` list, and the live
sweep in tests/260828 only checks that emitted keys were declared -- it runs producer to
declaration and never back. So a declared-but-optional key is exactly the shape of the
defect this slice fixed: the reducer could stop emitting `base_count_context` and every
guard in the harness would still pass.
"""

from __future__ import annotations

import copy
import unittest

from scripts.minervini.capabilities import CAPABILITIES
from scripts.minervini.operations import Runtime, execute
from tests.schemas import validator


AS_OF = "2026-08-28"
ENTRY = {
    "ticker": "AAPL",
    "as_of": AS_OF,
    "entry_price": 100.0,
    "stop_price": 94.0,
    "upside_price": 112.0,
    "average_gain_pct": 20.0,
    "base_count": 4,
}


class ABaseCountBlockThatVanishesMustNotValidate(unittest.TestCase):
    def test_the_declaration_calls_it_core(self) -> None:
        self.assertIn("base_count_context", CAPABILITIES["ticker.risk"].data_core)

    def test_the_schema_rejects_an_envelope_that_dropped_it(self) -> None:
        payload = execute("ticker.risk", ENTRY, runtime=Runtime())
        check = validator("ticker.risk")

        self.assertEqual(list(check.iter_errors(payload)), [])

        without = copy.deepcopy(payload)
        del without["data"]["base_count_context"]

        self.assertNotEqual(list(check.iter_errors(without)), [])

    def test_an_active_verdict_carries_it_too(self) -> None:
        """Both reducers emit it unconditionally, which is what makes requiring it honest."""

        payload = execute("ticker.risk", {"ticker": "AAPL", "as_of": AS_OF, "mode": "active"}, runtime=Runtime())

        self.assertEqual(list(validator("ticker.risk").iter_errors(payload)), [])
        self.assertIn("base_count_context", payload["data"])


if __name__ == "__main__":
    unittest.main()
