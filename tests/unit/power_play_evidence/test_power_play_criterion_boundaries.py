"""The two lines the bars decide, read exactly on the line.

Both criteria hand the chart everything above a line and settle everything below it themselves,
so where the line falls is the whole of what the bars contribute. Neither strictness had a reading
standing on it, and the two differ by a verdict: a volume ratio of exactly one is either the
absence of expansion the bars can call a failure, or a question a reader is asked.
"""

from __future__ import annotations

import unittest

from scripts.minervini import doctrine
from scripts.minervini.power_play_evidence import _CLAIM, _tightness_state, _volume_state


class NoExpandedSessionAnywhereInTheAdvance(unittest.TestCase):
    """The source says huge and names no magnitude, so no ratio passes on measurement. What the
    bars can still say is that nothing expanded at all -- and the heaviest session of the advance
    matching its own baseline exactly is that, not a question."""

    def test_a_ratio_of_exactly_one_is_the_absence_of_expansion(self) -> None:
        self.assertEqual(_volume_state(1.0), "fail")

    def test_the_first_ratio_above_it_is_the_chart_s(self) -> None:
        self.assertEqual(_volume_state(1.0000001), "needs_chart")

    def test_nothing_measured_is_neither(self) -> None:
        self.assertEqual(_volume_state(None), "unavailable")


class AFlagExactlyAtTheTightLimit(unittest.TestCase):
    """The source's ten percent is the inside of the tight branch, not the outside. A flag
    correcting exactly that much has not left it, and the alternative branch -- VCP character over
    twelve to thirty sessions -- is what a reader is asked about only once the flag is outside."""

    def setUp(self) -> None:
        self.limit = float(doctrine.threshold(_CLAIM, "tight_action_maximum_pct"))

    def test_a_flag_at_the_limit_is_satisfied_on_measurement(self) -> None:
        self.assertEqual(_tightness_state(self.limit, self.limit), "pass")

    def test_the_first_depth_past_it_falls_to_the_other_branch(self) -> None:
        self.assertEqual(_tightness_state(self.limit + 0.0000001, self.limit), "needs_chart")

    def test_nothing_measured_is_neither(self) -> None:
        self.assertEqual(_tightness_state(None, self.limit), "unavailable")


if __name__ == "__main__":
    unittest.main()
