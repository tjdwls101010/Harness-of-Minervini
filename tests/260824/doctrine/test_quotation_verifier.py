"""The verifier must be harder to satisfy than the thing it checks.

Every case here is a way a quotation could look verified without being the author's
words. They exist because an adversarial review walked straight through two of them.
"""

from __future__ import annotations

import copy
import json
import pathlib
import sys
import unittest


sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "scripts"))
import verify_doctrine_quotations as verifier


REGISTRY = pathlib.Path(__file__).resolve().parents[3] / "doctrine" / "claims.json"


def registry() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def one_claim(text: str, **extra: object) -> dict:
    quotation = {"corpus": "Minervini", "row": 11, "text": text, "supports": "probe"}
    quotation.update(extra)
    source = next(item for item in registry()["claims"] if item["id"] == "eligibility.standard_trend_template")
    probe = copy.deepcopy(source)
    probe["provenance"]["quotations"] = [quotation]
    probe["thresholds"] = {}
    return {"claims": [probe]}


class VerifierIntegrityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = verifier.load_rows()
        if not self.rows:
            self.skipTest("build-time corpus is absent")

    def test_a_fabricated_sentence_is_a_defect(self) -> None:
        defects, _, _ = verifier.verify(one_claim("This sentence was never in the corpus at all, not once."), self.rows)

        self.assertEqual(len(defects), 1)

    def test_declaring_an_assembly_does_not_excuse_a_fabricated_sentence(self) -> None:
        probe = one_claim(
            "This sentence was never in the corpus at all, not once.",
            assembled_from="claimed repair",
        )

        defects, _, _ = verifier.verify(probe, self.rows)

        self.assertEqual(len(defects), 1, "a declaration may explain non-adjacency, never invent text")

    def test_a_declared_assembly_of_real_sentences_is_accepted(self) -> None:
        real = (
            "It's important to point out that a stock must meet all eight of the Trend Template criteria "
            "to be considered in a confirmed stage 2 uptrend. "
            "You should avoid buying during stage 1 no matter how tempting it may be; even if the company's "
            "fundamentals look appealing, wait and buy only in stage 2."
        )
        probe = one_claim(real, assembled_from="two passages from the same chapter")

        defects, assembled, declared = verifier.verify(probe, self.rows)

        self.assertEqual(defects, [])
        self.assertEqual(assembled, [])
        self.assertEqual(len(declared), 1)

    def test_a_decimal_point_is_not_erased_by_normalisation(self) -> None:
        self.assertNotEqual(verifier.collapse("7.5 percent"), verifier.collapse("75 percent"))

    def test_altering_a_number_in_a_real_quotation_is_a_defect(self) -> None:
        altered = one_claim(
            "The current stock price is at least 300 percent above its 52-week low"
        )

        defects, _, _ = verifier.verify(altered, self.rows)

        self.assertEqual(len(defects), 1, "changing 30 to 300 must not read as the author's number")

    def test_a_thousands_separator_does_not_make_two_numbers_differ(self) -> None:
        self.assertEqual(verifier.collapse("1,000 shares"), verifier.collapse("1000 shares"))


if __name__ == "__main__":
    unittest.main()
