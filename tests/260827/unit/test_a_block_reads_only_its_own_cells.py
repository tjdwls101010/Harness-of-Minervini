"""A guard covers the cells a block consumes -- not the ones its window merely spans.

The defect this pins is a false unavailable. A block that refuses because of a session it
never opened reports "nothing to measure here" about evidence that was fine, and a reader
cannot tell that refusal from the real one. The companion rule is the other half: a
statistic over a population reads every member, so it may not compute through a hole.
"""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from scripts.minervini.management_evidence import build_management_evidence


AS_OF = "2025-12-31"
ENTRY = "2025-11-20"
STAGE2 = "2025-11-06"


def frame(*, rows: int = 260, splits: bool = True) -> pd.DataFrame:
    index = pd.bdate_range(end=AS_OF, periods=rows)
    closes = pd.Series(100.0, index=index)
    built = pd.DataFrame(
        {"Open": closes, "High": closes + 1.0, "Low": closes - 1.0, "Close": closes, "Volume": np.full(rows, 1_000_000.0)},
        index=index,
    )
    if splits:
        built["Stock Splits"] = np.zeros(rows)
    return built


def break_cell(bars: pd.DataFrame, session: str, column: str) -> pd.DataFrame:
    broken = bars.copy()
    broken.loc[pd.Timestamp(session), column] = float("nan")
    return broken


def build(bars: pd.DataFrame, **kwargs: object) -> dict:
    return build_management_evidence(
        bars,
        entry_date=pd.Timestamp(ENTRY).date(),
        as_of=pd.Timestamp(AS_OF).date(),
        stage2_start=pd.Timestamp(STAGE2).date(),
        base_top=100.0,
        breakout_date=pd.Timestamp(ENTRY).date(),
        **kwargs,
    )


class ACellNoBlockOpensDoesNotVoidIt(unittest.TestCase):
    """Each case names the block, the untouched cell, and why that cell is outside it."""

    CASES = (
        # The advance's first change is measured from its own first session, so the close
        # before the anchor is outside every reading the block makes.
        ("largest_decline_since_stage2_start", "2025-11-05", "Close"),
        # Only the latest close is read; the highs of the held sessions are the other input.
        ("base_extension", "2025-11-21", "Close"),
        # The true range reads fourteen sessions plus the one before them.
        ("moving_average_extension", "2025-12-11", "High"),
        # One session's Open is compared with its own Close; no earlier Open is read.
        ("key_reversal", "2025-11-21", "Open"),
        # A gap is the Open against the previous Close, and the run is the last close
        # against the breakout's -- an intermediate close is spanned, never opened.
        ("gaps_since_breakout", "2025-11-21", "Close"),
        # The Low is read for the latest session's closing range and nothing else.
        ("climax", "2025-12-25", "Low"),
        # The volume baseline ends at the breakout, and the closes read are the sessions
        # after it: a session before the baseline is outside both.
        ("failed_volume_confirmation", "2025-11-19", "Close"),
        # Both true ranges read fourteen sessions each; the session before the earlier one
        # contributes only its close, which the slope guard already covers.
        ("stage3_transition", "2025-11-21", "Low"),
        # A twenty-session return opens two closes. This one sits between them.
        ("climax", "2025-12-30", "Close"),
        # The weekly reading opens one close per week, from the first week of the advance.
        ("largest_decline_since_stage2_start", "2025-10-31", "Close"),
    )

    def test_a_cell_outside_the_reading_leaves_the_block_reported(self) -> None:
        for block, session, column in self.CASES:
            with self.subTest(block=block, session=session, column=column):
                result = build(break_cell(frame(), session, column))
                self.assertEqual(result[block]["state"], "reported", result[block])

    def test_the_same_blocks_still_refuse_a_cell_they_do_read(self) -> None:
        for block, session, column in (
            ("base_extension", AS_OF, "Close"),
            ("moving_average_extension", AS_OF, "Close"),
            ("key_reversal", AS_OF, "Open"),
            # The only close this block opens on its own is the breakout's.
            ("gaps_since_breakout", ENTRY, "Close"),
            ("climax", AS_OF, "Close"),
            ("failed_volume_confirmation", ENTRY, "Close"),
        ):
            with self.subTest(block=block, session=session, column=column):
                result = build(break_cell(frame(), session, column))
                self.assertEqual(result[block]["state"], "unavailable", result[block])


class AReadingRefusesOnlyItsOwnHole(unittest.TestCase):
    def test_a_broken_close_at_the_anchor_voids_the_daily_reading_and_not_the_block(self) -> None:
        result = build(break_cell(frame(), STAGE2, "Close"))["largest_decline_since_stage2_start"]

        self.assertEqual(result["state"], "reported")
        self.assertEqual(result["daily"]["state"], "unavailable")

    def test_the_close_before_the_anchor_is_outside_both_readings(self) -> None:
        # The advance's first change is measured from its own first session, and the week
        # this Wednesday belongs to is read at its Friday.
        result = build(break_cell(frame(), "2025-11-05", "Close"))["largest_decline_since_stage2_start"]

        self.assertEqual(result["daily"]["state"], "reported")
        self.assertEqual(result["weekly"]["state"], "reported")

    def test_a_down_session_the_volume_cannot_be_read_for_voids_the_volume_block(self) -> None:
        bars = frame()
        fell = pd.Timestamp("2025-12-08")
        bars.loc[fell, ["Open", "High", "Low", "Close"]] = [100.0, 100.0, 97.0, 98.0]
        result = build(break_cell(bars, "2025-12-08", "Volume"))["failed_volume_confirmation"]

        self.assertEqual(result["state"], "unavailable")
        self.assertEqual(result["date"], "2025-12-08")


class APopulationIsReadWhole(unittest.TestCase):
    def decline(self, bars: pd.DataFrame) -> dict:
        marked = bars.copy()
        marked.loc[pd.Timestamp(AS_OF), ["Open", "High", "Low", "Close"]] = [100.0, 100.0, 89.0, 90.0]
        marked.loc[pd.Timestamp(AS_OF), "Volume"] = 1_500_000.0
        return build(marked)["largest_decline_since_stage2_start"]["daily"]

    def test_a_hole_in_the_volume_baseline_leaves_no_ratio(self) -> None:
        result = self.decline(break_cell(frame(), "2025-11-06", "Volume"))

        self.assertIsNone(result["volume_ratio"])
        self.assertIn("volume_baseline", result["missing_inputs"])

    def test_a_split_inside_the_volume_baseline_leaves_no_ratio(self) -> None:
        # Before the advance began, so the block's own window does not span it -- but inside
        # the fifty sessions the ratio averages.
        bars = frame()
        split_at = pd.Timestamp("2025-10-23")
        bars.loc[split_at, "Stock Splits"] = 2.0
        bars.loc[bars.index >= split_at, "Volume"] = 2_000_000.0
        result = self.decline(bars)

        self.assertIsNone(result["volume_ratio"])

    def test_a_split_inside_the_percentile_population_leaves_no_percentile(self) -> None:
        bars = frame()
        split_at = pd.Timestamp("2025-05-22")
        bars.loc[split_at, "Stock Splits"] = 2.0
        bars.loc[bars.index >= split_at, "Volume"] = 2_000_000.0
        bars.loc[pd.Timestamp(AS_OF), "Volume"] = 1_500_000.0
        result = build(bars)["climax"]

        self.assertIsNone(result.get("last_volume_percentile"))


class TheVocabularyNamesTheRightAbsence(unittest.TestCase):
    def test_a_history_too_short_for_the_baseline_names_the_baseline(self) -> None:
        bars = frame(rows=40)
        bars.loc[pd.Timestamp(AS_OF), ["Open", "High", "Low", "Close"]] = [100.0, 100.0, 89.0, 90.0]
        result = build(bars)["largest_decline_since_stage2_start"]["daily"]

        self.assertIsNone(result["volume_ratio"])
        self.assertEqual(result["missing_inputs"], ["volume_baseline"])

    def test_a_cited_claim_input_the_reading_never_consumes_is_named(self) -> None:
        result = build(frame(), management_average="ema21")

        self.assertIn("weekly_context", result["moving_average_trail"].get("claim_inputs_not_read", []))
        self.assertIn("stop_price", result["twenty_day_average"].get("claim_inputs_not_read", []))


class EveryNamedAbsenceComesFromACitedClaim(unittest.TestCase):
    """The field is a subtraction, so nothing may appear in it that no citation asked for."""

    def test_no_block_names_an_input_its_own_citations_never_require(self) -> None:
        from scripts.minervini import doctrine

        result = build(frame(), management_average="ema21")
        for name, block in result.items():
            if not isinstance(block, dict) or "claim_inputs_not_read" not in block:
                continue
            cited = [block["doctrine_id"]] if block.get("doctrine_id") else []
            cited += list(block.get("doctrine_ids") or [])
            required = {item for claim_id in cited for item in doctrine.required_inputs(claim_id)}
            with self.subTest(block=name):
                self.assertTrue(cited, block)
                self.assertLessEqual(set(block["claim_inputs_not_read"]), required, block["claim_inputs_not_read"])


class AVectorWithNoConstituentIsNotAReading(unittest.TestCase):
    def test_stage_three_is_unavailable_when_neither_measurement_exists(self) -> None:
        bars = frame(rows=10)
        result = build_management_evidence(bars, entry_date=bars.index[0].date(), as_of=bars.index[-1].date())["stage3_transition"]

        self.assertEqual(result["state"], "unavailable")


if __name__ == "__main__":
    unittest.main()
