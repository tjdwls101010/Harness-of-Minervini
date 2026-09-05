"""The command line spells one answer per flag, and nothing else.

A key names the whole question -- the bars, the criterion, the reading of the tops and the
measurement -- so the flag carries a key and a word. What a reading may say, and what it is
refused for saying, lives at the request boundary rather than here: parsing it in two places
would let the shape a programmatic caller is held to drift from the shape this flag spells.
"""

from __future__ import annotations

import unittest

from scripts.minervini.cli import build_parser


def readings(*given: str) -> list[str]:
    from scripts.minervini.cli import _request

    parser = build_parser()
    args = parser.parse_args(
        ["ticker", "power-play", "TEST", *[flag for one in given for flag in ("--chart-reading", one)]]
    )
    return _request(args, "ticker.power-play").get("chart_readings", [])


class OneAnswerPerFlag(unittest.TestCase):
    def test_the_flag_repeats(self) -> None:
        self.assertEqual(
            readings("aaaaaaaaaaaaaaaa=observed", "bbbbbbbbbbbbbbbb=absent"),
            ["aaaaaaaaaaaaaaaa=observed", "bbbbbbbbbbbbbbbb=absent"],
        )

    def test_answering_nothing_declares_nothing(self) -> None:
        self.assertEqual(readings(), [])


if __name__ == "__main__":
    unittest.main()
