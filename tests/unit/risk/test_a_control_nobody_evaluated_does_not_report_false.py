"""`breakeven_protection_required: false` meant two things, and one of them was a guess.

The three-R block sits inside the HOLD branch. A SELL never enters it, so the field keeps
the `False` it was initialised with and the envelope says protection was not required --
about a position nobody measured the favorable excursion of. `r_multiple_reached` and
`favorable_excursion_basis` come back `None` right beside it, which is what "not measured"
looks like everywhere else in the same block.

Found by the behavioral acceptance suite rather than by a unit test, and that is the point of
it: two analyst runs read the `false` as evidence that three R did not apply, and wrote a
chronology -- the stop was hit before the position reached three R -- that nothing in the
envelope establishes. A field that cannot tell "not required" from "not evaluated" invites
exactly that, and the constitution's line is that unavailable evidence stays unavailable
rather than becoming a guessed pass or fail.

False still means false where the block ran and the answer was no: three R not reached, or
reached with the stop already standing above entry so there is nothing left to require.
"""

from __future__ import annotations

import unittest

from scripts.minervini.risk import reduce_risk


AS_OF = "2026-08-21"


def position(**overrides: object) -> dict:
    payload = {
        "mode": "active",
        "as_of": AS_OF,
        "entry_price": 100.0,
        "entry_date": "2026-08-10",
        "stop_price": 94.0,
        "current_price": 103.0,
        "completed_price_path": {"state": "clear", "checked_level": 94.0, "from": "2026-08-10", "through": AS_OF, "bars_checked": 9},
    }
    payload.update(overrides)
    return payload


def sold(**overrides: object) -> dict:
    """The same position after the stop was taken out on the 18th."""

    return position(
        completed_price_path={
            "state": "breached",
            "checked_level": 94.0,
            "from": "2026-08-10",
            "through": AS_OF,
            "bars_checked": 9,
            "breach_date": "2026-08-18",
            "breach_price": 92.5,
        },
        **overrides,
    )


class AnUnevaluatedControlSaysSoRatherThanNo(unittest.TestCase):
    def test_a_sell_does_not_report_breakeven_protection_as_not_required(self) -> None:
        controls = reduce_risk(sold(max_high_since_entry=130.0))["risk_controls"]

        # Its two companions already say "not measured" in this branch. This one said "no".
        self.assertIsNone(controls["r_multiple_reached"])
        self.assertIsNone(controls["favorable_excursion_basis"])
        self.assertIsNone(controls["breakeven_protection_required"])

    def test_the_verdict_is_still_the_sell_the_bars_established(self) -> None:
        self.assertEqual(reduce_risk(sold(max_high_since_entry=130.0))["verdict"], "SELL")

    def test_an_incomplete_position_reports_the_same_gap(self) -> None:
        """No established position is no excursion to measure either."""

        controls = reduce_risk({"mode": "active", "as_of": AS_OF, "entry_price": 100.0})["risk_controls"]

        self.assertEqual(reduce_risk({"mode": "active", "as_of": AS_OF, "entry_price": 100.0})["verdict"], "INCOMPLETE")
        self.assertIsNone(controls["breakeven_protection_required"])


class FalseStillMeansFalseWhereTheBlockRan(unittest.TestCase):
    def test_a_hold_short_of_three_r_reports_it_as_not_required(self) -> None:
        controls = reduce_risk(position(max_high_since_entry=104.0))["risk_controls"]

        self.assertEqual(controls["r_multiple_reached"], 0.6666666667)
        self.assertIs(controls["breakeven_protection_required"], False)

    def test_a_hold_past_three_r_reports_it_as_required(self) -> None:
        controls = reduce_risk(position(max_high_since_entry=125.0))["risk_controls"]

        self.assertIs(controls["breakeven_protection_required"], True)


if __name__ == "__main__":
    unittest.main()
