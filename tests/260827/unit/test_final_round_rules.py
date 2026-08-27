"""What the final review round changed: coordinates, conjunctions, and who a verdict belongs to."""

from __future__ import annotations

from datetime import date, datetime, timezone
import unittest

import numpy as np
import pandas as pd

from scripts.minervini.management_evidence import build_management_evidence
from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot, SnapshotMeta
from scripts.minervini.risk import reduce_risk


AS_OF = "2025-12-31"
FAILED_VOLUME = "management.low_volume_breakout_then_high_volume_selling"


def frame(rows: list[tuple[float, float, float, float, int]], *, splits: dict[int, float] | None = None) -> pd.DataFrame:
    index = pd.bdate_range(end=AS_OF, periods=len(rows))
    bars = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"], index=index)
    events = np.zeros(len(rows))
    for position, factor in (splits or {}).items():
        events[position] = factor
    # The provider always hands over the event column, so the fixtures do too: a frame
    # without it means something different, and has its own tests.
    bars["Stock Splits"] = events
    return bars


def flat(sessions: int, close: float = 100.0, volume: int = 1_000_000) -> list[tuple[float, float, float, float, int]]:
    return [(close, close * 1.01, close * 0.99, close, volume)] * sessions


def snapshot(bars: pd.DataFrame) -> ProviderSnapshot[pd.DataFrame]:
    return ProviderSnapshot(bars, SnapshotMeta(provider="fixture-prices", retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc), as_of=date.fromisoformat(AS_OF), coverage={"completed_only": True, "adjusted": False}))


class ASplitIsTwoCoordinateSystems(unittest.TestCase):
    """Unadjusted prices across a split are two different shares, so nothing is measured across it."""

    def bars(self) -> pd.DataFrame:
        return frame(flat(60, 100.0) + flat(20, 50.0), splits={60: 2.0})

    def test_the_stop_audit_refuses_rather_than_selling_on_the_arithmetic(self) -> None:
        bars = self.bars()
        payload = execute(
            "ticker.risk",
            {"ticker": "TEST", "mode": "active", "as_of": AS_OF, "entry_price": 100.0, "entry_date": bars.index[40].date().isoformat(), "stop_price": 94.0},
            runtime=Runtime(price_history=lambda ticker, as_of: snapshot(bars)),
        )

        path = payload["data"]["completed_price_path"]
        self.assertEqual(path["state"], "unavailable")
        self.assertEqual(path["reason"], "share_split_inside_stop_window")
        self.assertEqual(payload["data"]["verdict"], "INCOMPLETE")

    def test_the_declared_average_does_not_sell_across_the_split(self) -> None:
        bars = self.bars()
        result = build_management_evidence(bars, entry_date=bars.index[40].date(), as_of=bars.index[-1].date(), management_average="ema21")

        trail = result["moving_average_trail"]
        self.assertEqual(trail["state"], "unavailable")
        self.assertEqual(trail["reason"], "share_split_inside_window")


class TheDeclineBelongsToTheAdvance(unittest.TestCase):
    def test_a_change_that_starts_before_the_advance_is_not_its_largest_decline(self) -> None:
        # The fall from 100 to 80 happened on the session before the declared start.
        rows = flat(40, 100.0) + [(100.0, 100.0, 80.0, 80.0, 1_000_000)] + flat(9, 80.0)
        bars = frame(rows)
        # The advance is declared to begin on the session that fell: its change is measured
        # from the session before, which is outside the advance.
        result = build_management_evidence(bars, entry_date=bars.index[45].date(), as_of=bars.index[-1].date(), stage2_start=bars.index[40].date())

        daily = result["largest_decline_since_stage2_start"]["daily"]
        self.assertIsNone(daily["largest_pct"])
        self.assertIs(daily["last_session_is_largest"], False)


class TheFailedVolumeEventNamesWhatItCouldNotSettle(unittest.TestCase):
    """The source's "low volume" and "high volume" have no boundary, so the bars do not claim them."""

    def measure(self, breakout_volume: int, selling_volume: int) -> dict:
        rows = flat(50) + [(100.0, 101.0, 99.0, 105.0, breakout_volume), (105.0, 106.0, 104.0, 106.0, 1_000_000), (106.0, 106.0, 102.0, 103.0, selling_volume)] + flat(2, 103.0)
        bars = frame(rows)
        return build_management_evidence(bars, entry_date=bars.index[50].date(), as_of=bars.index[-1].date(), breakout_date=bars.index[50].date())["failed_volume_confirmation"]

    def test_the_comparison_the_bars_can_make_is_published_as_the_only_settled_one(self) -> None:
        block = self.measure(500_000, 2_000_000)

        self.assertIs(block["selling_volume_exceeded_breakout_volume"], True)
        self.assertIs(block["resolved_by_bars"], False)
        self.assertEqual(block["qualitative_conditions_unresolved"], ["breakout_was_on_low_volume", "selling_was_on_high_volume"])
        self.assertEqual(block["volume_convention"]["source"], "[TL]")
        self.assertIs(block["volume_convention"]["binds"], False)

    def test_both_sessions_carry_their_distance_to_the_practice_marker(self) -> None:
        block = self.measure(500_000, 2_000_000)

        self.assertEqual(block["breakout_volume_signal"]["role"], "marker")
        self.assertEqual(block["heaviest_down_session"]["signal"]["role"], "marker")

    def test_selling_no_heavier_than_the_breakout_is_not_the_event(self) -> None:
        block = self.measure(2_000_000, 1_500_000)

        self.assertIs(block["selling_volume_exceeded_breakout_volume"], False)


class AVerdictBelongsToWhoeverDeclaredIt(unittest.TestCase):
    def test_the_declared_average_sell_names_the_contract_and_the_measurement_separately(self) -> None:
        result = reduce_risk(
            {
                "mode": "active",
                "as_of": "2026-08-21",
                "entry_price": 100.0,
                "entry_date": "2026-08-10",
                "stop_price": 90.0,
                "current_price": 95.0,
                "management_average": "ema21",
                "completed_price_path": {"state": "clear", "checked_level": 90.0, "from": "2026-08-10", "through": "2026-08-21", "bars_checked": 9},
                "management": {"moving_average_trail": {"ema21": {"state": "breached", "breach_date": "2026-08-20"}, "selected": "ema21"}},
            }
        )

        self.assertEqual(result["verdict"], "SELL")
        self.assertEqual(result["failed"], ["management_average_exit"])
        plan = result["management_evidence"]["declared_exit_plan"]
        self.assertEqual(plan["doctrine_id"], "contract.declared_exit_plan_is_audited")
        self.assertIs(plan["binds"], True)
        self.assertEqual(plan["measurement_doctrine_id"], "management.ema21_sma50_roles")
        self.assertIs(plan["measurement_binds"], False)
        self.assertEqual(plan["measurement_source"], "[TL]")


if __name__ == "__main__":
    unittest.main()
