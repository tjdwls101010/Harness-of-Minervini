from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .capabilities import CAPABILITIES
from .contracts import RequestError, envelope, error_envelope


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
        if name == "chart":
            child.add_argument("--output-dir")
        _common(child)
    risk = ticker_sub.add_parser("risk", help="Evaluate prospective or active ticker risk.")
    risk.add_argument("ticker")
    risk.add_argument("--mode", choices=("prospective", "active"), default="prospective")
    risk.add_argument("--entry-price", type=float)
    risk.add_argument("--entry-date")
    risk.add_argument("--stop-price", type=float)
    risk.add_argument("--average-gain-pct", type=float)
    risk.add_argument("--live-stop-check", action="store_true")
    _common(risk)

    watchlist = sub.add_parser("watchlist", help="Explicit research-ledger operations.")
    watchlist_sub = watchlist.add_subparsers(dest="watchlist_command", required=True)
    for name in ("show", "history", "record", "annotate", "export"):
        child = watchlist_sub.add_parser(name, help=f"Run watchlist.{name}.")
        if name in {"history", "record", "annotate"}:
            child.add_argument("ticker")
        if name == "record":
            child.add_argument("--verdict", required=True)
            child.add_argument("--condition")
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


def _placeholder(args: argparse.Namespace, operation: str) -> dict[str, Any]:
    request = {key: value for key, value in vars(args).items() if not key.endswith("_command") and key != "command" and value is not None}
    return envelope(
        operation,
        request=request,
        status="unavailable",
        data={"reason": "capability implementation pending"},
        missing=[{"id": operation, "reason": "implementation_pending", "required": True}],
    )


def dispatch(args: argparse.Namespace) -> dict[str, Any]:
    operation = _operation(args)
    if operation == "capabilities":
        return envelope(operation, data={"capabilities": [CAPABILITIES[name].listing() for name in sorted(CAPABILITIES)]})
    if operation == "describe":
        capability = CAPABILITIES.get(args.capability)
        if capability is None:
            raise RequestError(f"unknown capability: {args.capability}", "capability")
        return envelope(operation, request={"capability": args.capability}, data=capability.description())
    return _placeholder(args, operation)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    operation = "request"
    try:
        args = parser.parse_args(argv)
        operation = _operation(args)
        payload = dispatch(args)
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
