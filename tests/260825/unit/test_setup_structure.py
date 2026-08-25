"""The caller declares coordinates the bars can contradict, not a verdict they cannot.

`--price-geometry pass` was an assertion nothing could check. A chain of swing dates is
also the caller's reading, but every claim in it is falsifiable against completed bars:
the date exists, the order holds, and the bar named as a swing high really is the highest
bar in the span its neighbours bound. A wrong reading now produces a contradiction with
the offending date in it, where a wrong flag produced READY.
"""

from __future__ import annotations

import unittest

from scripts.minervini.setup_structure import resolve_structure
from tests.series import anchor_dates, base_series


class ValidChainTests(unittest.TestCase):
    def test_an_alternating_chain_resolves_into_the_contractions_the_source_would_count(self) -> None:
        frame, anchors = base_series(depths=(25.0, 10.0, 5.0))

        structure = resolve_structure(frame, anchor_dates(frame, anchors))

        self.assertEqual(structure["state"], "resolved")
        self.assertEqual([round(item["depth_pct"], 4) for item in structure["contractions"]], [25.0, 10.0, 5.0])
        self.assertEqual(structure["base"]["high"], 100.0)

    def test_each_contraction_carries_the_span_its_volume_can_be_measured_over(self) -> None:
        """"Volume on the final contraction" has no meaning until the window has an end."""

        frame, anchors = base_series()

        structure = resolve_structure(frame, anchor_dates(frame, anchors))

        final = structure["contractions"][-1]
        self.assertLess(final["high_date"], final["low_date"])
        self.assertLess(final["low_date"], final["recovery_end"])


class ContradictedChainTests(unittest.TestCase):
    def test_a_bar_that_is_not_the_extreme_of_its_span_is_refused_by_name(self) -> None:
        frame, anchors = base_series()
        dates = anchor_dates(frame, anchors)
        # Move the second swing low one session earlier, where the bar is not the low.
        moved = frame.index[anchors[1].position - 1].date().isoformat()
        dates[1] = moved

        structure = resolve_structure(frame, dates)

        self.assertEqual(structure["state"], "contradicted")
        self.assertTrue(any(moved in problem for problem in structure["problems"]), structure["problems"])

    def test_a_chain_out_of_order_is_refused(self) -> None:
        frame, anchors = base_series()
        dates = anchor_dates(frame, anchors)
        dates[2], dates[3] = dates[3], dates[2]

        self.assertEqual(resolve_structure(frame, dates)["state"], "contradicted")

    def test_a_chain_that_does_not_end_on_a_high_cannot_name_a_pivot(self) -> None:
        frame, anchors = base_series()
        dates = anchor_dates(frame, anchors)[:-1]

        self.assertEqual(resolve_structure(frame, dates)["state"], "contradicted")

    def test_a_date_with_no_completed_bar_is_refused_rather_than_snapped_to_a_neighbour(self) -> None:
        frame, anchors = base_series()
        dates = anchor_dates(frame, anchors)
        dates[1] = "2026-04-04"

        structure = resolve_structure(frame, dates)

        self.assertEqual(structure["state"], "contradicted")
        self.assertTrue(any("2026-04-04" in problem for problem in structure["problems"]), structure["problems"])


class AbsentDeclarationTests(unittest.TestCase):
    def test_no_declaration_is_missing_evidence_rather_than_an_empty_base(self) -> None:
        frame, _ = base_series()

        structure = resolve_structure(frame, [])

        self.assertEqual(structure["state"], "unavailable")
        self.assertEqual(structure["contractions"], [])


if __name__ == "__main__":
    unittest.main()
