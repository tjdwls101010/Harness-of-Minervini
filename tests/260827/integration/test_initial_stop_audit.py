"""The stop the trade started with stays evidence: before a raise it governed, and it is never widened."""

from __future__ import annotations

from datetime import date, datetime, timezone
import unittest

import numpy as np
import pandas as pd

from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot, SnapshotMeta


AS_OF = "2025-12-31"
POSITION = {"ticker": "TEST", "mode": "active", "entry_price": 100.0, "entry_date": "2025-12-01", "as_of": AS_OF}


def bars(rows: list[tuple[float, float, float, float]], *, index: pd.DatetimeIndex | None = None) -> ProviderSnapshot[pd.DataFrame]:
    if index is None:
        index = pd.bdate_range(end=AS_OF, periods=len(rows))
    frame = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"], index=index, dtype=float)
    frame["Volume"] = np.full(len(frame), 1_000_000)
    return ProviderSnapshot(frame, SnapshotMeta(provider="fixture-prices", retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc), as_of=date.fromisoformat(AS_OF), coverage={"completed_only": True}))


def quiet(sessions: int, close: float = 101.0) -> list[tuple[float, float, float, float]]:
    return [(close, close + 1.0, close - 1.5, close)] * sessions


def run(rows, **request):
    return execute("ticker.risk", {**POSITION, **request}, runtime=Runtime(price_history=lambda ticker, as_of: bars(rows) if not isinstance(rows, ProviderSnapshot) else rows))


class TheInitialStopGovernedUntilTheRaise(unittest.TestCase):
    def test_a_low_that_breached_the_initial_stop_before_the_raise_is_a_sell(self) -> None:
        # 44 bars: Low 93 prints on 2025-12-10, the stop is raised to 97 on 2025-12-15.
        index = pd.bdate_range(start="2025-11-03", end=AS_OF)
        rows = []
        for stamp in index:
            low = 93.0 if stamp.date().isoformat() == "2025-12-10" else 99.5
            rows.append((101.0, 102.0, low, 101.0))
        payload = execute("ticker.risk", {**POSITION, "stop_price": 97.0, "stop_effective_date": "2025-12-15", "initial_stop_price": 94.0}, runtime=Runtime(price_history=lambda ticker, as_of: bars(rows, index=index)))

        self.assertEqual(payload["data"]["verdict"], "SELL")
        path = payload["data"]["completed_price_path"]
        self.assertEqual(path["state"], "breached")
        self.assertEqual(path["breach_date"], "2025-12-10")
        self.assertEqual(path["checked_level"], 94.0)

    def test_clear_before_the_raise_and_clear_after_it_is_a_hold(self) -> None:
        payload = run(quiet(44), stop_price=97.0, stop_effective_date="2025-12-15", initial_stop_price=94.0)

        self.assertEqual(payload["data"]["verdict"], "HOLD")
        roles = {audit["role"] for audit in payload["data"]["completed_price_path"]["audits"]}
        self.assertIn("initial_stop", roles)

    def test_the_initial_stop_audit_ends_where_the_raise_begins(self) -> None:
        # Low 95 on 2025-12-22 sits below nothing in force: the initial 94 stopped governing
        # on the 15th and the raised 97... would catch it. Use initial 96, raised 97:
        # a Low of 96.5 before the raise breaches neither; after the raise it breaches 97.
        index = pd.bdate_range(start="2025-11-03", end=AS_OF)
        rows = []
        for stamp in index:
            low = 96.5 if stamp.date().isoformat() == "2025-12-10" else 99.5
            rows.append((101.0, 102.0, low, 101.0))
        payload = execute("ticker.risk", {**POSITION, "stop_price": 97.0, "stop_effective_date": "2025-12-15", "initial_stop_price": 96.0}, runtime=Runtime(price_history=lambda ticker, as_of: bars(rows, index=index)))

        self.assertEqual(payload["data"]["verdict"], "HOLD")


class AStopIsNeverWidened(unittest.TestCase):
    def test_a_low_between_the_widened_stop_and_the_initial_stop_is_a_sell(self) -> None:
        # Initial 94, later "stop" 90: widening the doctrine forbids. Low 92 breaches the
        # stop that never stopped governing.
        index = pd.bdate_range(start="2025-11-03", end=AS_OF)
        rows = []
        for stamp in index:
            low = 92.0 if stamp.date().isoformat() == "2025-12-22" else 99.5
            rows.append((101.0, 102.0, low, 101.0))
        payload = execute("ticker.risk", {**POSITION, "stop_price": 90.0, "stop_effective_date": "2025-12-15", "initial_stop_price": 94.0}, runtime=Runtime(price_history=lambda ticker, as_of: bars(rows, index=index)))

        self.assertEqual(payload["data"]["verdict"], "SELL")
        self.assertEqual(payload["data"]["completed_price_path"]["breach_date"], "2025-12-22")


class TheRequestContractHoldsAtTheOperationSeam(unittest.TestCase):
    def test_a_different_initial_stop_without_an_effective_date_is_incomplete_through_the_operation(self) -> None:
        payload = run(quiet(44), stop_price=97.0, initial_stop_price=94.0)

        self.assertEqual(payload["data"]["verdict"], "INCOMPLETE")
        self.assertIn("stop_effective_date", [item["id"] for item in payload["missing"]])

    def test_a_non_positive_initial_stop_is_a_request_error_not_a_hold(self) -> None:
        from scripts.minervini.contracts import RequestError

        with self.assertRaises(RequestError) as caught:
            run(quiet(44), stop_price=97.0, stop_effective_date="2025-12-15", initial_stop_price=-1.0)

        self.assertEqual(caught.exception.field, "initial_stop_price")


class DuplicateSessionsReadTheSameEverywhere(unittest.TestCase):
    def test_a_superseded_print_s_low_does_not_breach_the_stop(self) -> None:
        # The provider repeated 2025-12-05; the final print of that session has Low 99.
        index = pd.bdate_range(start="2025-08-01", end=AS_OF)
        rows = [(101.0, 102.0, 99.5, 101.0)] * len(index)
        frame_index = index.insert(list(index).index(pd.Timestamp("2025-12-05")), pd.Timestamp("2025-12-05"))
        rows.insert(list(index).index(pd.Timestamp("2025-12-05")), (101.0, 102.0, 80.0, 101.0))
        snapshot = bars(rows, index=frame_index)
        payload = execute("ticker.risk", {**POSITION, "stop_price": 90.0}, runtime=Runtime(price_history=lambda ticker, as_of: snapshot))

        self.assertEqual(payload["data"]["verdict"], "HOLD")
        self.assertEqual(payload["data"]["management_evidence"]["moving_average_trail"]["ema21"]["state"], "clear")


class ABreachNamesTheLevelItCrossed(unittest.TestCase):
    """A price at or below one level says nothing about the levels below it."""

    def test_an_explicit_price_under_the_invalidation_is_not_a_stop_breach(self) -> None:
        payload = run(
            quiet(40),
            stop_price=90.0,
            invalidation={"price": 95.0, "condition": "close at or below 95"},
            current_price=94.0,
        )

        data = payload["data"]
        self.assertEqual(data["verdict"], "SELL")
        self.assertEqual(data["failed"], ["invalidation_breach"])
        path = data["completed_price_path"]
        self.assertEqual(path["governing_role"], "invalidation")
        self.assertEqual(path["checked_level"], 95.0)
        stop_audit = next(audit for audit in path["audits"] if audit["role"] == "stop")
        # No bar was read, so the stop is unaudited. Ninety-four today cannot say the Low
        # never reached ninety last week.
        self.assertEqual(stop_audit["state"], "unavailable")
        self.assertEqual(stop_audit["reason"], "not_audited_after_explicit_breach")

    def test_a_price_under_both_levels_is_named_by_the_one_it_crossed_first(self) -> None:
        # Price falls from above, so 95 was crossed before 90. Naming the lower level would
        # report the trade as ending at a line the market reached second.
        payload = run(quiet(40), stop_price=90.0, invalidation={"price": 95.0, "condition": "close at or below 95"}, current_price=88.0)

        data = payload["data"]
        self.assertEqual(data["failed"], ["invalidation_breach"])
        path = data["completed_price_path"]
        self.assertEqual(path["governing_role"], "invalidation")
        self.assertEqual(path["checked_level"], 95.0)
        self.assertEqual({audit["role"]: audit["state"] for audit in path["audits"]}, {"stop": "breached", "invalidation": "breached"})

    def test_an_expired_initial_stop_is_not_audited_by_a_price_printed_since(self) -> None:
        # The raise ended the initial stop's window on 2025-12-15. Today's 90 breaches the
        # stop that is actually in force, and says nothing about a window that closed.
        payload = run(quiet(40), stop_price=97.0, initial_stop_price=94.0, stop_effective_date="2025-12-15", current_price=90.0)

        path = payload["data"]["completed_price_path"]
        self.assertEqual(path["governing_role"], "stop")
        self.assertEqual(path["checked_level"], 97.0)
        self.assertEqual(path["from"], "2025-12-15")
        initial = next(audit for audit in path["audits"] if audit["role"] == "initial_stop")
        self.assertEqual(initial["reason"], "not_audited_after_explicit_breach")

    def test_a_widened_stop_publishes_the_initial_level_that_still_governs(self) -> None:
        # A stop is never widened, so 94 stayed in force. The 88 Low broke both; the record
        # is about the higher one, which is the one the session crossed first.
        rows = quiet(43)
        rows[-7] = (100.0, 101.0, 88.0, 100.0)
        payload = run(rows, stop_price=90.0, initial_stop_price=94.0, stop_effective_date="2025-12-15")

        data = payload["data"]
        self.assertEqual(data["verdict"], "SELL")
        self.assertEqual(data["completed_price_path"]["governing_role"], "initial_stop")
        self.assertEqual(data["completed_price_path"]["checked_level"], 94.0)

    def test_an_initial_stop_at_the_same_level_still_governed_its_own_window(self) -> None:
        # The levels being equal does not mean there was no earlier window: what makes one
        # is the later effective date, and a breach inside it is a breach.
        rows = quiet(43)
        rows[-16] = (100.0, 101.0, 89.0, 100.0)
        payload = run(rows, stop_price=90.0, initial_stop_price=90.0, stop_effective_date="2025-12-15")

        data = payload["data"]
        self.assertEqual(data["verdict"], "SELL")
        self.assertEqual(data["completed_price_path"]["state"], "breached")
        self.assertEqual(data["completed_price_path"]["checked_level"], 90.0)


if __name__ == "__main__":
    unittest.main()
