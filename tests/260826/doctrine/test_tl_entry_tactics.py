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
        """Named on annotated charts, defined nowhere.

        "This includes highlighting early entries such as upside reversals, range breakouts, inside
        days and more" is the whole of what the source says about three of them, in a chapter of
        chart captions. Registering a tactic on that would put a trigger in the harness's mouth.
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
