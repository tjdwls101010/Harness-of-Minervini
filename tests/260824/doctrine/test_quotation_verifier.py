"""The verifier must be harder to satisfy than the thing it checks.

Every case here is a way a quotation could look verified without being the author's
words. They exist because an adversarial review walked straight through two of them.
"""

from __future__ import annotations

from tests.paths import REGISTRY, ROOT, registry

import copy
import json
import sys
import unittest


sys.path.insert(0, str(ROOT / "scripts"))
import verify_doctrine_quotations as verifier


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

    def test_altering_a_number_in_a_real_quotation_is_never_silently_verified(self) -> None:
        # The tool cannot tell an altered digit from a genuine list join, so it reports
        # rather than classifies. What it must never do is pass the altered text.
        defects, assembled, declared = verifier.verify(
            one_claim("The current stock price is at least 300 percent above its 52-week low"), self.rows
        )

        self.assertEqual(len(defects) + len(assembled) + len(declared), 1)
        self.assertEqual(declared, [], "an undeclared alteration must not be accepted")

    def test_a_thousands_separator_does_not_make_two_numbers_differ(self) -> None:
        self.assertEqual(verifier.collapse("1,000 shares"), verifier.collapse("1000 shares"))


class NumericFidelityTests(unittest.TestCase):
    def test_a_range_dash_is_not_erased(self) -> None:
        # "30-40 percent" collapsing to "3040" would let a range read as one number.
        self.assertNotEqual(verifier.collapse("30-40 percent"), verifier.collapse("3040 percent"))

    def test_an_en_dash_range_reads_the_same_as_a_hyphen_range(self) -> None:
        self.assertEqual(verifier.collapse("30–40 percent"), verifier.collapse("30-40 percent"))

    def test_a_ratio_colon_is_not_erased(self) -> None:
        self.assertNotEqual(verifier.collapse("at least 2:1"), verifier.collapse("at least 21"))


class FragmentCoverageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = verifier.load_rows()
        if not self.rows:
            self.skipTest("build-time corpus is absent")

    def test_a_short_fabricated_sentence_appended_to_a_declared_quotation_is_a_defect(self) -> None:
        real = (
            "It's important to point out that a stock must meet all eight of the Trend Template criteria "
            "to be considered in a confirmed stage 2 uptrend."
        )
        probe = one_claim(real + " Buy now.", assembled_from="declared assembly")

        defects, _, _ = verifier.verify(probe, self.rows)

        self.assertEqual(len(defects), 1, "a short addition is still an addition")

    def test_the_same_quotation_without_the_addition_is_accepted(self) -> None:
        real = (
            "It's important to point out that a stock must meet all eight of the Trend Template criteria "
            "to be considered in a confirmed stage 2 uptrend."
        )

        defects, assembled, _ = verifier.verify(one_claim(real), self.rows)

        self.assertEqual((defects, assembled), ([], []))


class OperatorFidelityTests(unittest.TestCase):
    def test_reversing_a_comparison_operator_changes_the_text(self) -> None:
        self.assertNotEqual(verifier.collapse("RS 12M: > 69"), verifier.collapse("RS 12M: < 69"))

    def test_dropping_a_minus_sign_changes_the_text(self) -> None:
        self.assertNotEqual(verifier.collapse("% Off 52 Wk High: > -25.00%"), verifier.collapse("% Off 52 Wk High: > 25.00%"))

    def test_an_operator_still_reads_the_same_written_either_way(self) -> None:
        self.assertEqual(verifier.collapse("at least 30%"), verifier.collapse("at least 30 %"))


class ShortPieceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = verifier.load_rows()
        if not self.rows:
            self.skipTest("build-time corpus is absent")

    def test_a_declared_assembly_ending_in_a_short_genuine_piece_is_accepted(self) -> None:
        joined = (
            "It's important to point out that a stock must meet all eight of the Trend Template criteria "
            "to be considered in a confirmed stage 2 uptrend. "
            "wait and buy only in stage 2."
        )

        defects, _, declared = verifier.verify(one_claim(joined, assembled_from="two passages"), self.rows)

        self.assertEqual(defects, [])
        self.assertEqual(len(declared), 1)


class EmptyQuotationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = verifier.load_rows()
        if not self.rows:
            self.skipTest("build-time corpus is absent")

    def test_punctuation_long_enough_to_look_like_a_sentence_is_a_defect(self) -> None:
        defects, _, _ = verifier.verify(one_claim("." * 40), self.rows)

        self.assertEqual(len(defects), 1, "a citation with no words is not a citation")

    def test_the_registry_validator_also_refuses_a_wordless_citation(self) -> None:
        from scripts.minervini import doctrine

        broken = json.loads(REGISTRY.read_text(encoding="utf-8"))
        record = next(item for item in broken["claims"] if item["id"] == "eligibility.standard_trend_template")
        record["provenance"]["quotations"][0]["text"] = "." * 40

        result = doctrine.validate(broken)

        self.assertFalse(result["valid"])


if __name__ == "__main__":
    unittest.main()
