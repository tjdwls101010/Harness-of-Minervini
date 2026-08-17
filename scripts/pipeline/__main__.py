#!/usr/bin/env python3
"""Canonical entry point for the Harness of Minervini v2 CLI."""

import pathlib
import sys


scripts_dir = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(scripts_dir))

from minervini.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
