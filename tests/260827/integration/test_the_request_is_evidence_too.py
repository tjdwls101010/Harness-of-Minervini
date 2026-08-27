"""What the caller hands in is read the way the bars are read.

A word outside the vocabulary is not a "no". A cell that will not parse is not a zero. A
number that is not a price does not become one by arriving in a price field. And a bar whose
close is under its own low is not a bar -- the audit reading its Low and the verdict reading
its Close would otherwise answer one question two ways.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import unittest

import numpy as np
import pandas as pd

from scripts.minervini.contracts import RequestError
from scripts.minervini.management_evidence import build_management_evidence
from scripts.minervini.operations import Runtime, execute
from scripts.minervini.risk import reduce_risk


AS_OF = "2025-12-31"
POSITION = {"ticker": "TEST", "mode": "active", "entry_price": 100.0, "entry_date": "2025-12-01", "as_of": AS_OF, "stop_price": 90.0}


def run(overrides=None, *, splits=None, split_column=None, start="2025-10-01", extra_rows=None, **request) -> dict:
    index = pd.bdate_range(start=start, end=AS_OF)
    rows = [(overrides or {}).get(stamp.date().isoformat(), (100.0, 101.0, 99.0, 100.0)) for stamp in index]
    data = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"], index=index, dtype=float)
    data["Volume"] = np.full(len(data), 1_000_000)
    if split_column is None:
        data["Stock Splits"] = np.zeros(len(data))
        for session, factor in (splits or {}).items():
            data.loc[pd.Timestamp(session), "Stock Splits"] = factor
    else:
        data["Stock Splits"] = [split_column] * len(data)
    for session, row in (extra_rows or {}).items():
        data.loc[pd.Timestamp(session)] = [*row, 1_000_000, 0.0]
    data = data.sort_index()
    snapshot = ProviderSnapshot(data, SnapshotMeta(provider="fixture-prices", retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc), as_of=date.fromisoformat(AS_OF), coverage={"completed_only": True}))
    return execute("ticker.risk", {**POSITION, **request}, runtime=Runtime(price_history=lambda ticker, as_of: snapshot))


from scripts.minervini.providers import ProviderSnapshot, SnapshotMeta  # noqa: E402


class APriceFieldHoldsAPrice(unittest.TestCase):
    def test_a_current_price_of_zero_is_refused_rather_than_taken_out(self) -> None:
        with self.assertRaises(RequestError) as caught:
            run(current_price=0)

        self.assertEqual(caught.exception.field, "current_price")

    def test_a_negative_current_price_is_refused(self) -> None:
        with self.assertRaises(RequestError) as caught:
            run(current_price=-1)

        self.assertEqual(caught.exception.field, "current_price")

    def test_an_infinite_current_price_is_refused_rather_than_dropped(self) -> None:
        with self.assertRaises(RequestError) as caught:
            run(current_price=float("inf"))

        self.assertEqual(caught.exception.field, "current_price")

    def test_a_price_written_as_a_string_is_refused_rather_than_dropped(self) -> None:
        with self.assertRaises(RequestError) as caught:
            run(current_price="100")

        self.assertEqual(caught.exception.field, "current_price")


class AStopIsBelowTheEntryItProtects(unittest.TestCase):
    def test_a_stop_in_force_from_entry_at_or_above_it_leaves_no_risk(self) -> None:
        with self.assertRaises(RequestError) as caught:
            run(stop_price=110.0)

        self.assertEqual(caught.exception.field, "stop_price")

    def test_a_stop_raised_above_entry_later_is_a_raise_and_not_a_contradiction(self) -> None:
        risen = {stamp.date().isoformat(): (120.0, 121.0, 119.0, 120.0) for stamp in pd.bdate_range(start="2025-12-10", end=AS_OF)}
        payload = run(risen, stop_price=110.0, initial_stop_price=90.0, stop_effective_date="2025-12-10", market={"state": "defensive"})

        self.assertEqual(payload["data"]["verdict"], "HOLD")
        defense = payload["data"]["management_evidence"]["market_defense"]
        # The stop defends a gain, so there is no loss below entry for the band to be about.
        self.assertIsNone(defense["stop_pct"])
        self.assertIsNone(defense["difficult_market_band"]["measured"])


class AWordOutsideTheVocabularyIsNotANo(unittest.TestCase):
    def test_an_unknown_market_state_is_refused_rather_than_published(self) -> None:
        with self.assertRaises(RequestError) as caught:
            run(market={"state": "banana"})

        self.assertEqual(caught.exception.field, "market")

    def test_an_unknown_completed_stop_state_is_refused_rather_than_read_as_untriggered(self) -> None:
        with self.assertRaises(RequestError) as caught:
            run(completed_stop={"state": "banana"})

        self.assertEqual(caught.exception.field, "completed_stop")

    def test_an_unknown_price_path_state_is_refused(self) -> None:
        with self.assertRaises(RequestError) as caught:
            run(completed_price_path={"state": "banana"})

        self.assertEqual(caught.exception.field, "completed_price_path")

    def test_a_list_where_a_mapping_belongs_is_refused_rather_than_ignored(self) -> None:
        with self.assertRaises(RequestError) as caught:
            run(invalidation=[])

        self.assertEqual(caught.exception.field, "invalidation")

    def test_a_market_component_that_is_not_a_mapping_is_refused(self) -> None:
        with self.assertRaises(RequestError) as caught:
            run(market=[])

        self.assertEqual(caught.exception.field, "market")


class ADateFieldHoldsADate(unittest.TestCase):
    def test_an_entry_date_written_as_a_number_is_refused_rather_than_half_parsed(self) -> None:
        with self.assertRaises(RequestError) as caught:
            run(entry_date=20251201)

        self.assertEqual(caught.exception.field, "entry_date")

    def test_a_breakout_date_written_as_a_number_is_refused(self) -> None:
        with self.assertRaises(RequestError) as caught:
            run(breakout_date=20251103)

        self.assertEqual(caught.exception.field, "breakout_date")

    def test_a_date_in_basic_form_is_refused_because_the_reducer_cannot_read_it(self) -> None:
        with self.assertRaises(RequestError) as caught:
            run(stage2_start="20251103")

        self.assertEqual(caught.exception.field, "stage2_start")


class ABarWhoseCloseIsBelowItsLowIsNotABar(unittest.TestCase):
    def test_an_impossible_relation_withholds_the_price_instead_of_selling_on_it(self) -> None:
        payload = run({AS_OF: (100.0, 101.0, 100.0, 50.0)})

        data = payload["data"]
        self.assertNotEqual(data["verdict"], "SELL")
        self.assertEqual(data["completed_price_path"]["state"], "unavailable")
        self.assertEqual(data["completed_price_path"]["reason"], "invalid_ohlc_history")

    def test_a_high_below_its_own_low_is_the_same_finding(self) -> None:
        payload = run({"2025-12-10": (100.0, 98.0, 99.0, 100.0)})

        self.assertEqual(payload["data"]["completed_price_path"]["state"], "unavailable")


class AnUnreadableSplitColumnIsNotAQuietTape(unittest.TestCase):
    def test_a_column_of_words_withholds_the_audit_rather_than_clearing_it(self) -> None:
        payload = run(split_column="garbage")

        data = payload["data"]
        self.assertEqual(data["verdict"], "INCOMPLETE")
        self.assertEqual(data["completed_price_path"]["reason"], "corporate_action_evidence_missing")


class AHandedInRecordCrossesTheLevelItNames(unittest.TestCase):
    def test_a_record_whose_basis_is_not_its_roles_basis_is_not_a_record(self) -> None:
        payload = run(completed_price_path={"state": "breached", "basis": "completed_daily_close", "governing_role": "stop", "checked_level": 90.0, "breach_date": "2025-12-10", "breach_low": 95.0})

        self.assertNotEqual(payload["data"]["verdict"], "SELL")

    def test_a_record_whose_price_never_reached_the_level_is_not_a_record(self) -> None:
        payload = run(completed_price_path={"state": "breached", "basis": "completed_daily_low", "governing_role": "stop", "checked_level": 90.0, "breach_date": "2025-12-10", "breach_low": 95.0})

        self.assertNotEqual(payload["data"]["verdict"], "SELL")


class AnUnreadableEventCellStopsTheStructureBlocksToo(unittest.TestCase):
    def test_a_management_block_names_the_missing_evidence_rather_than_a_split(self) -> None:
        # The audit and the structure blocks read one frame, so a blank cell has to mean the
        # same thing to both -- and it is evidence missing, not an event the provider declared.
        index = pd.bdate_range(start="2025-10-01", end=AS_OF)
        data = pd.DataFrame([(100.0, 101.0, 99.0, 100.0)] * len(index), columns=["Open", "High", "Low", "Close"], index=index, dtype=float)
        data["Volume"] = np.full(len(data), 1_000_000)
        data["Stock Splits"] = np.zeros(len(data))
        data.loc[pd.Timestamp("2025-12-15"), "Stock Splits"] = float("nan")
        result = build_management_evidence(data, entry_date=date(2025, 12, 1), as_of=date.fromisoformat(AS_OF))

        block = result["twenty_day_average"]
        self.assertEqual(block["state"], "unavailable")
        self.assertEqual(block["reason"], "corporate_action_evidence_missing")
        self.assertEqual(block["date"], "2025-12-15")


class ATrailStopsAtWhicheverTroubleComesFirst(unittest.TestCase):
    def bars(self, *, hole: str, split: str) -> pd.DataFrame:
        index = pd.bdate_range(start="2025-10-01", end=AS_OF)
        data = pd.DataFrame([(100.0, 101.0, 99.0, 100.0)] * len(index), columns=["Open", "High", "Low", "Close"], index=index, dtype=float)
        data["Volume"] = np.full(len(data), 1_000_000)
        data["Stock Splits"] = np.zeros(len(data))
        data.loc[pd.Timestamp(hole), "Close"] = float("nan")
        data.loc[pd.Timestamp(split), "Stock Splits"] = 2.0
        return data

    def trail(self, data: pd.DataFrame) -> dict:
        result = build_management_evidence(data, entry_date=date(2025, 12, 1), as_of=date.fromisoformat(AS_OF))
        return result["moving_average_trail"]

    def test_a_hole_before_the_split_is_the_session_the_audit_stops_at(self) -> None:
        trail = self.trail(self.bars(hole="2025-12-05", split="2025-12-19"))

        self.assertEqual(trail["reason"], "invalid_ohlc_history")
        self.assertEqual(trail["date"], "2025-12-05")

    def test_a_split_before_the_hole_is_the_session_the_audit_stops_at(self) -> None:
        trail = self.trail(self.bars(hole="2025-12-19", split="2025-12-05"))

        self.assertEqual(trail["reason"], "share_split_inside_window")
        self.assertEqual(trail["date"], "2025-12-05")


class AReducerReadsALevelTheWayItsOwnAuditDoes(unittest.TestCase):
    def test_a_last_price_exactly_at_the_stop_reached_the_order(self) -> None:
        result = reduce_risk({"mode": "active", "as_of": AS_OF, "entry_price": 100.0, "entry_date": "2025-12-01", "stop_price": 90.0, "current_price": 90.0})

        self.assertEqual(result["verdict"], "SELL")
        self.assertEqual(result["failed"], ["completed_stop_breach"])


class APriceTooSmallToPublishIsNotAPrice(unittest.TestCase):
    def test_a_measurement_that_overflows_is_withheld_rather_than_printed_as_infinite(self) -> None:
        # At the reducer's own seam: the operation refuses this scale before it gets here,
        # and the rule that no infinity reaches the page is the reducer's regardless.
        result = reduce_risk({
            "mode": "active",
            "as_of": AS_OF,
            "entry_price": 1e-300,
            "entry_date": "2025-12-01",
            "stop_price": 5e-301,
            "current_price": 1e300,
            "average_gain_pct": 20.0,
            "completed_price_path": {"state": "clear", "audits": [{"role": "stop", "level": 5e-301, "basis": "completed_daily_low", "state": "clear", "effective_from": "2025-12-01", "through": AS_OF, "bars_checked": 23}]},
        })

        strength = result["management_evidence"]["strength_references"]
        self.assertIsNone(strength["return_pct"])
        self.assertIsNone(strength["r_multiple"])

    def test_a_price_that_rounds_away_at_the_reported_precision_is_refused(self) -> None:
        # Every field built from it -- the loss percent, the R multiple, the excursion --
        # divides by a risk that publishes as zero, and the quotients come back infinite.
        with self.assertRaises(RequestError) as caught:
            run(entry_price=1e-323, stop_price=5e-324)

        self.assertEqual(caught.exception.field, "stop_price")


if __name__ == "__main__":
    unittest.main()
