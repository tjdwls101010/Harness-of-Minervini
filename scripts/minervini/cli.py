from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .capabilities import CAPABILITIES
from .contracts import RequestError, envelope, error_envelope
from .operations import Runtime, execute


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise RequestError(message=message, field="arguments")


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--as-of", metavar="YYYY-MM-DD", help="Use evidence available by this completed US session.")
    parser.add_argument("--format", choices=("compact", "full"), default="full", help="Control detail, never semantics.")
    parser.add_argument("--no-cache", action="store_true", help="Bypass cache reads and writes.")


def build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(description="Harness of Minervini v2 composable evidence CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("capabilities", help="List public capabilities.")
    describe = sub.add_parser("describe", help="Describe one public capability as JSON.")
    describe.add_argument("capability")
    health = sub.add_parser("health", help="Check runtime and provider readiness.")
    _common(health)
    clock = sub.add_parser("clock", help="Resolve the completed-session analysis clock.")
    _common(clock)

    doctrine = sub.add_parser("doctrine", help="Inspect normalized doctrine claims.")
    doctrine_sub = doctrine.add_subparsers(dest="doctrine_command", required=True)
    doctrine_show = doctrine_sub.add_parser("show", help="Show one doctrine claim.")
    doctrine_show.add_argument("claim_id")
    _common(doctrine_show)

    market = sub.add_parser("market", help="Market, sector, industry, and candidate evidence.")
    market_sub = market.add_subparsers(dest="market_command", required=True)
    snapshot = market_sub.add_parser("snapshot", help="Measure regime and group leadership.")
    snapshot.add_argument(
        "--trade-traction",
        choices=("supports", "contradicts", "mixed", "needs_input"),
        help="Report whether the user's recent pilot trades confirm the apparent market environment.",
    )
    snapshot.add_argument("--leader-limit", type=int, default=20, help="Maximum first-party RS leader observations to return (1-100).")
    _common(snapshot)
    candidates = market_sub.add_parser("candidates", help="Return a paginated candidate universe.")
    candidates.add_argument("--limit", type=int, default=50)
    candidates.add_argument("--cursor")
    _common(candidates)

    ticker = sub.add_parser("ticker", help="Composable named-ticker evidence.")
    ticker_sub = ticker.add_subparsers(dest="ticker_command", required=True)
    for name in ("qualify", "setup", "fundamentals", "peers", "chart"):
        child = ticker_sub.add_parser(name, help=f"Run ticker.{name}.")
        child.add_argument("ticker")
        if name == "qualify":
            child.add_argument(
                "--primary-base-quality",
                choices=("supports", "contradicts", "needs_chart"),
                help="Supply the model's weekly Primary Base chart judgment for a recent IPO.",
            )
        if name == "setup":
            child.add_argument("--price-geometry", choices=("pass", "fail", "needs_chart"))
            child.add_argument("--supply-evidence", choices=("pass", "fail", "needs_chart"))
            child.add_argument("--entry-kind", choices=("completed_pivot", "vcp_cheat", "tl_early"))
            child.add_argument("--entry-state", choices=("confirmed", "wait", "needs_chart"))
            child.add_argument("--invalidation-price", type=float)
            child.add_argument("--invalidation-condition")
            child.add_argument("--tactic-opt-in", action="store_true")
        if name == "fundamentals":
            child.add_argument("--cik", help="Stable SEC CIK; required with historical --as-of.")
            child.add_argument("--power-play-quality", choices=("textbook", "acceptable"))
            child.add_argument("--power-play-fundamentals-exception", action="store_true")
            child.add_argument("--power-play-technical-eligibility", action="store_true")
            child.add_argument("--power-play-price-volume-structure", action="store_true")
            child.add_argument("--power-play-market-alignment", action="store_true")
            child.add_argument("--power-play-risk-controls", action="store_true")
        if name == "peers":
            child.add_argument("--limit", type=int, default=10)
        if name == "chart":
            child.add_argument("--output-dir")
        _common(child)
    risk = ticker_sub.add_parser("risk", help="Evaluate prospective or active ticker risk.")
    risk.add_argument("ticker")
    risk.add_argument("--mode", choices=("prospective", "active"), default="prospective")
    risk.add_argument("--entry-price", type=float)
    risk.add_argument("--entry-date")
    risk.add_argument("--stop-price", type=float)
    risk.add_argument("--upside-price", type=float)
    risk.add_argument("--current-price", type=float)
    risk.add_argument("--average-gain-pct", type=float)
    risk.add_argument("--market-state")
    risk.add_argument("--eligibility-state")
    risk.add_argument("--setup-state")
    risk.add_argument("--fundamentals-state")
    risk.add_argument("--invalidation-price", type=float)
    risk.add_argument("--invalidation-condition")
    risk.add_argument("--completed-stop-breach", action="store_true")
    risk.add_argument("--live-stop-check", action="store_true")
    risk.add_argument("--live-stop-breach", action="store_true")
    _common(risk)

    watchlist = sub.add_parser("watchlist", help="Explicit research-ledger operations.")
    watchlist_sub = watchlist.add_subparsers(dest="watchlist_command", required=True)
    for name in ("show", "history", "record", "annotate", "export"):
        child = watchlist_sub.add_parser(name, help=f"Run watchlist.{name}.")
        if name in {"history", "record", "annotate"}:
            child.add_argument("ticker")
        if name == "record":
            child.add_argument("--instrument-id", required=True)
            child.add_argument("--output-hash", required=True)
            child.add_argument("--verdict", required=True)
            child.add_argument("--condition")
            child.add_argument("--invalidation")
            child.add_argument("--doctrine-id", action="append", dest="doctrine_ids", default=[])
            child.add_argument("--evidence-quality")
            child.add_argument("--note")
        if name == "annotate":
            child.add_argument("--note", required=True)
        if name == "export":
            child.add_argument("--output", required=True)
        _common(child)
    return parser


def _operation(args: argparse.Namespace) -> str:
    if args.command in {"doctrine", "market", "ticker", "watchlist"}:
        return f"{args.command}.{getattr(args, args.command + '_command')}"
    return args.command


def _request(args: argparse.Namespace, operation: str) -> dict[str, Any]:
    request = {
        key: value
        for key, value in vars(args).items()
        if not key.endswith("_command") and key != "command" and value is not None
    }
    if operation == "ticker.setup":
        geometry = request.pop("price_geometry", None)
        supply = request.pop("supply_evidence", None)
        entry_kind = request.pop("entry_kind", None)
        entry_state = request.pop("entry_state", None)
        invalidation_price = request.pop("invalidation_price", None)
        invalidation_condition = request.pop("invalidation_condition", None)
        judgments: dict[str, Any] = {}
        if geometry is not None:
            judgments["price_geometry"] = {"state": geometry}
        if supply is not None:
            judgments["supply_evidence"] = {"state": supply}
        if any(value is not None for value in (entry_kind, entry_state, invalidation_price, invalidation_condition)):
            entry: dict[str, Any] = {"kind": entry_kind, "state": entry_state}
            if invalidation_price is not None or invalidation_condition is not None:
                entry["invalidation"] = {"price": invalidation_price, "condition": invalidation_condition}
            judgments["entry"] = entry
        if judgments:
            request["chart_judgments"] = judgments
    if operation == "ticker.risk":
        invalidation_price = request.pop("invalidation_price", None)
        invalidation_condition = request.pop("invalidation_condition", None)
        if invalidation_price is not None or invalidation_condition is not None:
            request["invalidation"] = {"price": invalidation_price, "condition": invalidation_condition}
        if request.pop("completed_stop_breach", False):
            request["completed_stop"] = {"state": "triggered"}
        live_stop_breach = request.pop("live_stop_breach", False)
        if request.get("live_stop_check") or live_stop_breach:
            request["live_stop"] = {
                "state": "triggered" if live_stop_breach else "not_triggered",
                "partial_session": True,
            }
        for request_name, component_name in (
            ("market_state", "market"),
            ("eligibility_state", "eligibility"),
            ("setup_state", "setup"),
            ("fundamentals_state", "fundamentals"),
        ):
            state = request.pop(request_name, None)
            if state is not None:
                request[component_name] = {"state": state}
    if operation == "ticker.fundamentals":
        quality = request.pop("power_play_quality", None)
        exception = request.pop("power_play_fundamentals_exception", False)
        proof = {
            name.removeprefix("power_play_"): request.pop(name, False)
            for name in (
                "power_play_technical_eligibility",
                "power_play_price_volume_structure",
                "power_play_market_alignment",
                "power_play_risk_controls",
            )
        }
        if quality is not None or exception or any(proof.values()):
            request["power_play"] = {
                "detected": quality is not None,
                "quality": quality,
                "fundamentals_exception": {
                    "status": "map_authorized_only_for_this_vcp-qualified_setup" if exception else "not_authorized",
                    "may_omit": ["verified_fundamentals"] if exception else [],
                },
                **{name: "pass" if passed else "unavailable" for name, passed in proof.items()},
            }
    return request


def dispatch(args: argparse.Namespace, *, runtime: Runtime | None = None) -> dict[str, Any]:
    operation = _operation(args)
    if operation == "capabilities":
        return envelope(operation, data={"capabilities": [CAPABILITIES[name].listing() for name in sorted(CAPABILITIES)]})
    if operation == "describe":
        capability = CAPABILITIES.get(args.capability)
        if capability is None:
            raise RequestError(f"unknown capability: {args.capability}", "capability")
        return envelope(operation, request={"capability": args.capability}, data=capability.description())
    return execute(operation, _request(args, operation), runtime=runtime)


def main(argv: list[str] | None = None, *, runtime: Runtime | None = None) -> int:
    parser = build_parser()
    operation = "request"
    try:
        args = parser.parse_args(argv)
        operation = _operation(args)
        payload = dispatch(args, runtime=runtime)
        code = 0
    except RequestError as error:
        payload = error_envelope(operation, error)
        code = 2
    except Exception as error:
        payload = envelope(
            operation,
            status="unavailable",
            data={"error": {"code": "internal_error", "message": str(error), "field": None, "retryable": False}},
        )
        code = 3
    print(json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
