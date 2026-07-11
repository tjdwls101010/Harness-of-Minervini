#!/usr/bin/env python3
"""Minervini SEPA — composable tools for sector/ticker discovery and analysis.

Two subcommands, run as the evidence earns it — NOT a single closed pipeline, and
deliberately no "analyze everything at once" command:

  qualify TICKER  Tier-0 gate. Runs Trend Template (including RS) + Stage (low-cost) and
				  returns PROCEED, AVOID, or INCOMPLETE. Missing evidence is never
				  flattened into AVOID. Run this FIRST.
  discover        Market environment + RS leadership: breadth (new-high vs
                  new-low), RS leaders (top 20), sector/industry rankings,
                  leadership board, movers.

The hard gates (Stage 2 + Trend Template 8/8) are the only thing the tools decide
on their own — binary, non-negotiable. SEPA convergence, entry timing, leadership,
and risk are read by the analyst from the raw module outputs against the skill's
doctrine, not collapsed into a score. Past the gate, deepen by calling the modules
under modules/ directly as Tier-1/Tier-2 tools (e.g. vcp detect,
earnings_acceleration code33, rs_ranking screen, volume_analysis analyze) — one
question, one tool — rather than collecting everything at once.

All subcommands return JSON; errors are {"error": "..."} with exit code 1.
"""

import argparse
import os
import sys

# Ensure the repository's scripts/ tree is on sys.path for module imports.
_scripts_dir = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, _scripts_dir)
sys.path.insert(0, os.path.join(_scripts_dir, "modules"))

from pipeline._commands import cmd_qualify, cmd_discover
from utils import JsonArgumentParser


def main():
	parser = JsonArgumentParser(
		description="Minervini SEPA: composable discovery & analysis tools"
	)
	sub = parser.add_subparsers(dest="command", required=True)

	# qualify — Tier-0 low-cost hard gate (run first)
	sp_qualify = sub.add_parser("qualify", help="Tier-0 gate: Stage 2 + Trend Template including RS (low-cost, run first)")
	sp_qualify.add_argument("ticker", help="Stock ticker symbol")
	sp_qualify.add_argument("--no-cache", action="store_true", help="Bypass shared cache reads and writes")
	sp_qualify.set_defaults(func=cmd_qualify)

	# discover — market environment + RS leaders
	sp_discover = sub.add_parser("discover", help="Market environment + RS leader discovery")
	sp_discover.add_argument("--no-cache", action="store_true", help="Bypass shared cache reads and writes")
	sp_discover.set_defaults(func=cmd_discover)

	args = parser.parse_args()
	args.func(args)


if __name__ == "__main__":
	main()
