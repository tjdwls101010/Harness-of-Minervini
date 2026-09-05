"""Shared fixtures for power play evidence."""

from __future__ import annotations

from scripts.minervini.power_play_evidence import build_power_play_evidence
from tests.series import power_play_series


def evidence(**kwargs):
    return build_power_play_evidence(power_play_series(**kwargs))


def states(pack) -> dict:
    return {signal["id"]: signal["state"] for signal in pack["signals"]}
