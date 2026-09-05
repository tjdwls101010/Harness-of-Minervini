import unittest

from scripts.minervini.cli import build_parser, dispatch, format_payload
from scripts.minervini.contracts import RequestError
from scripts.minervini.operations import execute
from tests.schemas import validator


AS_OF = "2025-12-31"


class AnAnalystCanDiscoverTheDoctrineToRead(unittest.TestCase):
    def test_list_publishes_runtime_claims_and_their_reading_contract(self) -> None:
        payload = execute("doctrine.list", {"as_of": AS_OF})
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["side_effects"], [])
        for mode in ("full", "compact"):
            with self.subTest(format=mode):
                output = format_payload(payload, mode)
                validator("doctrine.list").validate(output)
                rows = {row["id"]: row for row in output["data"]["claims"]}
                self.assertIn("scope.data_integrity", rows)
                self.assertTrue(set(rows).isdisjoint({"practitioners.activity.ryan_90pct_buys_in_uptrend", "practitioners.market_regime.zanger_sell_everything_on_signal_and_reduce_60_80pct", "practitioners.ftd.ryan_half_size_5pct_vs_10pct_before_uptrend_confirmed", "practitioners.ftd.zanger_50pct_cap_before_ftd_conviction"}))
                for row in rows.values():
                    self.assertEqual(set(row), {"id", "title", "kind", "layer", "computability", "roles", "consumers"})
                risk = rows["risk.initial_stop_and_reward"]
                self.assertEqual(risk["roles"], ["band", "gate", "reference"])
                self.assertEqual(risk["computability"], "deterministic")
                self.assertIn("ticker.risk", risk["consumers"])
                self.assertEqual(rows["setup.vcp_supply_contraction"]["computability"], "chart_assisted")

    def test_filters_intersect_and_an_empty_result_is_complete(self) -> None:
        result = execute("doctrine.list", {"as_of": AS_OF, "context": "prospective_entry", "family": "risk.", "layer": "canonical"})
        self.assertEqual(result["status"], "ok")
        rows = result["data"]["claims"]
        self.assertIn("risk.initial_stop_and_reward", [row["id"] for row in rows])
        self.assertTrue(all(row["id"].startswith("risk.") and row["layer"] == "canonical" for row in rows))
        empty = execute("doctrine.list", {"as_of": AS_OF, "context": "no_such_context"})
        self.assertEqual(empty["status"], "ok")
        self.assertEqual(empty["data"]["claims"], [])

    def test_bad_filters_are_rejected_at_the_public_execute_boundary(self) -> None:
        for name in ("context", "family", "layer"):
            for value in (42, "", " "):
                with self.subTest(field=name, value=value), self.assertRaises(RequestError):
                    execute("doctrine.list", {"as_of": AS_OF, name: value})

    def test_describe_and_cli_expose_the_same_filters(self) -> None:
        description = execute("describe", {"capability": "doctrine.list"})
        self.assertEqual(description["status"], "ok")
        self.assertTrue({"context", "family", "layer"} <= set(description["data"]["inputs"]))
        args = build_parser().parse_args(["doctrine", "list", "--as-of", AS_OF, "--context", "prospective_entry", "--family", "risk.", "--layer", "canonical"])
        self.assertEqual(dispatch(args), execute("doctrine.list", {"as_of": AS_OF, "format": "full", "context": "prospective_entry", "family": "risk.", "layer": "canonical"}))
