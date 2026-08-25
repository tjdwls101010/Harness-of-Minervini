"""The command line teaches the five tactics by only accepting them.

A parameter that takes five named values says what the five are every time it is read, in a place
no session can miss and no compaction drops. Leaving "tl_early" spellable would leave the shape
this slice removed reachable from the outside.
"""

from __future__ import annotations

import unittest

from scripts.minervini.cli import build_parser


TACTICS = (
    "key_support_level_reclaim",
    "consolidation_pivot_breakout",
    "key_moving_average_pullback",
    "oops_reversal",
    "key_support_level_pullback",
)


def entry_kind_choices() -> tuple[str, ...]:
    parser = build_parser()
    for action in parser._subparsers._group_actions[0].choices["ticker"]._subparsers._group_actions[0].choices["setup"]._actions:
        if action.dest == "entry_kind":
            return tuple(action.choices)
    raise AssertionError("ticker setup has no --entry-kind")


class TheChoicesAreTheTactics(unittest.TestCase):
    def test_every_defined_tactic_can_be_declared(self) -> None:
        self.assertEqual([name for name in TACTICS if name not in entry_kind_choices()], [])

    def test_the_two_measured_routes_are_still_there(self) -> None:
        choices = entry_kind_choices()
        self.assertIn("completed_pivot", choices)
        self.assertIn("vcp_cheat", choices)

    def test_the_word_that_names_no_tactic_is_not_spellable(self) -> None:
        self.assertNotIn("tl_early", entry_kind_choices())

    def test_the_labels_the_source_only_captioned_are_not_offered(self) -> None:
        choices = entry_kind_choices()
        for label in ("upside_reversal", "range_breakout", "inside_day"):
            with self.subTest(label=label):
                self.assertNotIn(label, choices)

    def test_the_intraday_tactics_are_not_offered(self) -> None:
        choices = entry_kind_choices()
        for label in ("opening_range_breakout", "intraday_base", "high_volume_close_pivot"):
            with self.subTest(label=label):
                self.assertNotIn(label, choices)


class TheConditionsAreDeclarableFromOutside(unittest.TestCase):
    """A route only the test suite can complete is not a route the harness offers.

    One repeatable flag rather than eleven, because the eleven belong to five different tactics
    and only one of them is in play at a time. Naming the condition is what the flag is for, so a
    name the declared tactic does not have is refused rather than carried.
    """

    def test_ticker_setup_takes_tactic_evidence(self) -> None:
        parser = build_parser()
        setup = parser._subparsers._group_actions[0].choices["ticker"]._subparsers._group_actions[0].choices["setup"]
        self.assertIn("tactic_evidence", {action.dest for action in setup._actions})

    def test_it_can_be_given_more_than_once(self) -> None:
        parsed = build_parser().parse_args([
            "ticker", "setup", "TEST",
            "--entry-kind", "oops_reversal",
            "--tactic-evidence", "prior_day_low=yesterday's low, 98.00",
            "--tactic-evidence", "gap_below_prior_low=opened below it and reclaimed it",
        ])

        self.assertEqual(len(parsed.tactic_evidence), 2)


class AConditionTheTacticDoesNotHaveIsRefused(unittest.TestCase):
    """A typo that goes nowhere is worse than a typo that stops you.

    Silently dropped, a misspelled condition leaves the caller looking at a gap they believe they
    filled. The tactic's claim knows its condition names, so the boundary can say which ones.
    """

    def _request(self, *evidence):
        from scripts.minervini.cli import _operation, _request

        parsed = build_parser().parse_args([
            "ticker", "setup", "TEST", "--entry-kind", "oops_reversal",
            *[item for pair in (("--tactic-evidence", text) for text in evidence) for item in pair],
        ])
        return _request(parsed, _operation(parsed))

    def test_a_name_the_declared_tactic_does_not_have_is_refused(self) -> None:
        from scripts.minervini.contracts import RequestError

        with self.assertRaises(RequestError) as caught:
            self._request("prior_day_lo=observed:yesterday's low")

        self.assertIn("prior_day_low", str(caught.exception))

    def test_a_name_it_does_have_is_carried(self) -> None:
        request = self._request("prior_day_low=observed:yesterday's low")

        self.assertEqual(request["entry"]["prior_day_low"]["condition"], "yesterday's low")


class TheCallerSaysWhichReadingItWas(unittest.TestCase):
    """Free text cannot be graded, so the flag asks for the grade separately.

    Injecting `pass` for whatever was typed made the reducer's denial path unreachable from the
    outside: "the stock did not gap below it" arrived as evidence that it did. Three words settle
    it, and asking for one of them is cheaper than pretending prose can be read.
    """

    def _entry(self, *evidence):
        from scripts.minervini.cli import _operation, _request

        parsed = build_parser().parse_args([
            "ticker", "setup", "TEST", "--entry-kind", "oops_reversal",
            *[item for pair in (("--tactic-evidence", text) for text in evidence) for item in pair],
        ])
        return _request(parsed, _operation(parsed))["entry"]

    def test_an_observed_condition_reads_as_one(self) -> None:
        entry = self._entry("prior_day_low=observed:yesterday's low at 98.20")

        self.assertEqual(entry["prior_day_low"]["state"], "pass")
        self.assertEqual(entry["prior_day_low"]["condition"], "yesterday's low at 98.20")

    def test_an_absent_condition_is_carried_as_a_denial(self) -> None:
        entry = self._entry("gap_below_prior_low=absent:the stock did not gap below it")

        self.assertEqual(entry["gap_below_prior_low"]["state"], "fail")

    def test_an_unclear_reading_is_carried_as_unresolved(self) -> None:
        entry = self._entry("gap_below_prior_low=unclear:the open is ambiguous at this scale")

        self.assertEqual(entry["gap_below_prior_low"]["state"], "needs_chart")

    def test_a_reading_with_no_verdict_word_is_refused(self) -> None:
        from scripts.minervini.contracts import RequestError

        with self.assertRaises(RequestError) as caught:
            self._entry("prior_day_low=yesterday's low at 98.20")

        self.assertIn("observed", str(caught.exception))

    def test_the_same_condition_twice_is_a_contradiction_rather_than_a_correction(self) -> None:
        from scripts.minervini.contracts import RequestError

        with self.assertRaises(RequestError) as caught:
            self._entry("prior_day_low=observed:first reading", "prior_day_low=absent:second reading")

        self.assertIn("prior_day_low", str(caught.exception))
