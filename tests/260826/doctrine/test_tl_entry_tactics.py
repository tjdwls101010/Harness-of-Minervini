"""The named early-entry tactics, and the line between what the source defines and what it labels.

TraderLion states that every entry tactic has exactly two components -- a pivot that triggers the
entry and a risk-management level it is abandoned at -- and then defines five of them on the daily
timeframe. A tactic registered without both components would be a name the harness invented a rule
for, which is the shape a generic early entry already had.
"""

from __future__ import annotations

import json
import pathlib
import unittest


REGISTRY = pathlib.Path(__file__).resolve().parents[3] / "doctrine" / "claims.json"

# The five the source defines under "Launch-pad setup and base breakout". Its other three entry
# tactics -- the opening range breakout, the intraday base and the high-volume-close pivot -- are
# intraday and out of this harness's scope.
DEFINED = (
    "tactic.key_support_level_reclaim",
    "tactic.consolidation_pivot_breakout",
    "tactic.key_moving_average_pullback",
    "tactic.oops_reversal",
    "tactic.key_support_level_pullback",
)


def claims() -> dict[str, dict]:
    return {record["id"]: record for record in json.loads(REGISTRY.read_text(encoding="utf-8"))["claims"]}


class EveryNamedTacticIsRegistered(unittest.TestCase):
    def test_the_five_the_source_defines_are_all_present(self) -> None:
        self.assertEqual([name for name in DEFINED if name not in claims()], [])

    def test_none_of_them_is_quarantined_or_inactive(self) -> None:
        registry = claims()
        self.assertEqual(
            [name for name in DEFINED
             if registry[name]["status"] != "active" or registry[name]["quarantine"]["is_quarantined"]],
            [],
        )


class ATacticDeclaresBothOfItsComponents(unittest.TestCase):
    """A pivot with no risk level is half a tactic, and the half that loses money."""

    def test_every_tactic_names_its_trigger_and_its_invalidation(self) -> None:
        registry = claims()
        incomplete = []
        for name in DEFINED:
            required = set(registry[name]["required_inputs"])
            if not {"entry_trigger", "invalidation"}.issubset(required):
                incomplete.append(name)
        self.assertEqual(incomplete, [])

    def test_every_tactic_says_what_it_has_not_confirmed_yet(self) -> None:
        registry = claims()
        self.assertEqual([name for name in DEFINED if "confirmation_debt" not in registry[name]["required_inputs"]], [])


class TheSourceIsTheOnlyAuthorHere(unittest.TestCase):
    def test_every_tactic_quotes_traderlion_for_its_rule(self) -> None:
        registry = claims()
        unsourced = []
        for name in DEFINED:
            quotations = registry[name]["provenance"].get("quotations") or []
            if not any(item.get("corpus") == "TraderLion" for item in quotations):
                unsourced.append(name)
        self.assertEqual(unsourced, [])

    def test_the_labels_the_source_never_defined_are_not_registered_as_tactics(self) -> None:
        """Named often, given a contract nowhere.

        These three are not absent from the source -- they label annotated charts, and one trade
        post-mortem enters an upside reversal on the next day's push over the prior high. What
        none of them has is what makes the other five tactics: a stated trigger and a risk level
        that belong to the tactic rather than to the example. Registering one on a worked example
        would put a rule in the source's mouth that it never generalised.
        """
        invented = [name for name in claims()
                    if name.startswith("tactic.")
                    and any(word in name for word in ("upside_reversal", "range_breakout", "inside_day"))]
        self.assertEqual(invented, [])

    def test_the_intraday_tactics_stay_out_of_scope(self) -> None:
        invented = [name for name in claims()
                    if name.startswith("tactic.")
                    and any(word in name for word in ("opening_range", "intraday", "high_volume_close"))]
        self.assertEqual(invented, [])


class WhatMakesTheTacticItselfIsInItsClaim(unittest.TestCase):
    """The shared terms are shared, so a tactic made only of them is a tactic in name only.

    The reducer reads a route's conditions by subtracting what every early entry owes from what
    the claim requires. A claim whose whole list is shared terms comes back with nothing of its
    own, and the route stops being distinguishable from the generic one this replaced -- silently,
    because subtracting to empty raises nothing.
    """

    SHARED = {"technical_eligibility", "entry_trigger", "invalidation", "confirmation_debt", "tactic_opt_in"}

    def test_every_tactic_requires_something_no_other_early_entry_does(self) -> None:
        registry = claims()
        bare = [name for name in DEFINED if not set(registry[name]["required_inputs"]) - self.SHARED]
        self.assertEqual(bare, [])

    def test_no_two_tactics_are_made_of_the_same_conditions(self) -> None:
        registry = claims()
        own = {name: frozenset(registry[name]["required_inputs"]) - self.SHARED for name in DEFINED}
        duplicates = [
            (first, second)
            for index, first in enumerate(DEFINED)
            for second in DEFINED[index + 1:]
            if own[first] == own[second]
        ]
        self.assertEqual(duplicates, [])
