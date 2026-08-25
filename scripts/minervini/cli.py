from __future__ import annotations

import argparse
from copy import deepcopy
import json
import math
import sys
from typing import Any

from .capabilities import CAPABILITIES
from .contracts import RequestError, envelope, error_envelope
from .operations import Runtime, execute
from .providers import redact


def positive_number(value: str) -> float:
    """Reject a value JSON cannot carry before it can reach an envelope."""

    try:
        number = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not a number") from None
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError(f"{value!r} must be a finite positive number")
    return number


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise RequestError(message=message, field="arguments")


# Every value that decided something already travels in a signal, so the raw measurement
# table and the anchor list are detail rather than meaning.
_COMPACT_OMIT_KEYS = frozenset({"basis", "source_basis", "source_row", "quarterly", "annual_growth", "discrepancies", "measurements", "anchors", "contractions"})


def _compact_data(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _compact_data(item) for key, item in value.items() if key not in _COMPACT_OMIT_KEYS}
    if isinstance(value, list):
        return [_compact_data(item) for item in value]
    return value


def format_payload(payload: dict[str, Any], mode: str) -> dict[str, Any]:
    """Reduce verbose evidence detail without changing verdict, signals, or missing evidence."""

    if mode not in {"compact", "full"}:
        raise ValueError("format must be compact or full")
    formatted = deepcopy(payload)
    if mode == "full":
        return formatted
    if "data" in formatted:
        formatted["data"] = _compact_data(formatted["data"])
    if isinstance(formatted.get("sources"), list):
        formatted["sources"] = [
            {key: source.get(key) for key in ("provider", "as_of", "stale")}
            for source in formatted["sources"]
            if isinstance(source, dict)
        ]
    return formatted


class DetailedHelpFormatter(argparse.RawDescriptionHelpFormatter, argparse.ArgumentDefaultsHelpFormatter):
    pass


def _input_help(capability: str, name: str) -> str:
    return str(CAPABILITIES[capability].inputs[name]["description"])


def _capability_parser(subparsers: Any, command: str, capability: str) -> argparse.ArgumentParser:
    contract = CAPABILITIES[capability]
    return subparsers.add_parser(
        command,
        help=contract.summary,
        description=contract.summary,
        epilog=contract.help_epilog(),
        formatter_class=DetailedHelpFormatter,
    )


def _group_parser(subparsers: Any, command: str, *, summary: str, details: str) -> argparse.ArgumentParser:
    return subparsers.add_parser(
        command,
        help=summary,
        description=summary,
        epilog=f"{details}\n\nRun 'scripts/.venv/bin/python scripts/pipeline {command} <command> --help' for the complete leaf-command contract.",
        formatter_class=DetailedHelpFormatter,
    )


def _common(parser: argparse.ArgumentParser, capability: str) -> None:
    parser.add_argument("--as-of", metavar="YYYY-MM-DD", help=_input_help(capability, "as_of"))
    parser.add_argument("--format", choices=("compact", "full"), default="full", help=_input_help(capability, "format"))
    if "no_cache" in CAPABILITIES[capability].inputs:
        parser.add_argument("--no-cache", action="store_true", help=_input_help(capability, "no_cache"))


def build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(
        description="Harness of Minervini v2: composable, point-in-time evidence and decision contracts for US momentum-stock analysis.",
        epilog="Start with 'capabilities', inspect one contract with 'describe <capability>' or a leaf '--help', and compose only the evidence the question needs. Every non-help command prints exactly one JSON document. Run all examples from the repository root.",
        formatter_class=DetailedHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    _capability_parser(sub, "capabilities", "capabilities")
    describe = _capability_parser(sub, "describe", "describe")
    describe.add_argument("capability", help=_input_help("describe", "capability"))
    health = _capability_parser(sub, "health", "health")
    health.add_argument("--probe", action="store_true", help=_input_help("health", "probe"))
    _common(health, "health")
    clock = _capability_parser(sub, "clock", "clock")
    _common(clock, "clock")

    doctrine = _group_parser(sub, "doctrine", summary="Inspect executable doctrine claims.", details="Doctrine is a normalized runtime registry. It is intentionally smaller and more operational than the source corpus.")
    doctrine_sub = doctrine.add_subparsers(dest="doctrine_command", required=True, metavar="COMMAND")
    doctrine_show = _capability_parser(doctrine_sub, "show", "doctrine.show")
    doctrine_show.add_argument("claim_id", help=_input_help("doctrine.show", "claim_id"))
    _common(doctrine_show, "doctrine.show")

    market = _group_parser(sub, "market", summary="Inspect regime, groups, leadership, and the candidate universe.", details="Use snapshot for environment and leadership evidence, then candidates for paginated US common-stock and ADR discovery. Neither command prescribes portfolio allocation.")
    market_sub = market.add_subparsers(dest="market_command", required=True, metavar="COMMAND")
    snapshot = _capability_parser(market_sub, "snapshot", "market.snapshot")
    snapshot.add_argument("--trade-traction", choices=("supports", "contradicts", "mixed", "needs_input"), help=_input_help("market.snapshot", "trade_traction"))
    snapshot.add_argument("--leader-limit", type=int, default=20, metavar="N", help=_input_help("market.snapshot", "leader_limit"))
    _common(snapshot, "market.snapshot")
    candidates = _capability_parser(market_sub, "candidates", "market.candidates")
    candidates.add_argument("--limit", type=int, default=50, metavar="N", help=_input_help("market.candidates", "limit"))
    candidates.add_argument("--cursor", help=_input_help("market.candidates", "cursor"))
    _common(candidates, "market.candidates")

    ticker = _group_parser(sub, "ticker", summary="Compose named-ticker qualification, setup, fundamentals, peers, risk, and chart evidence.", details="A prospective decision normally flows qualify → setup/fundamentals/peers → risk. Active positions go directly to risk with actual entry and stop anchors. Each leaf remains independently inspectable.")
    ticker_sub = ticker.add_subparsers(dest="ticker_command", required=True, metavar="COMMAND")
    qualify = _capability_parser(ticker_sub, "qualify", "ticker.qualify")
    qualify.add_argument("ticker", help=_input_help("ticker.qualify", "ticker"))
    qualify.add_argument("--primary-base-quality", choices=("supports", "contradicts", "needs_chart"), help=_input_help("ticker.qualify", "primary_base_quality"))
    qualify.add_argument("--primary-base-emergence", choices=("near_high_consolidation", "needs_chart"), help=_input_help("ticker.qualify", "primary_base_emergence"))
    qualify.add_argument("--primary-base-long-correction", choices=("confirmed", "not_confirmed", "needs_chart"), help=_input_help("ticker.qualify", "primary_base_long_correction"))
    _common(qualify, "ticker.qualify")

    setup = _capability_parser(ticker_sub, "setup", "ticker.setup")
    setup.add_argument("ticker", help=_input_help("ticker.setup", "ticker"))
    setup.add_argument("--swing", action="append", default=[], metavar="YYYY-MM-DD", help=_input_help("ticker.setup", "swing"))
    setup.add_argument("--entry-kind", choices=("completed_pivot", "vcp_cheat", "tl_early"), help=_input_help("ticker.setup", "entry_kind"))
    setup.add_argument("--chain-completeness", choices=("complete", "partial", "needs_chart"), help=_input_help("ticker.setup", "chain_completeness"))
    setup.add_argument("--entry-price", type=positive_number, metavar="PRICE", help=_input_help("ticker.setup", "entry_price"))
    setup.add_argument("--pivot-reset", choices=("prompt_reset", "stale_reset", "needs_judgment"), help=_input_help("ticker.setup", "pivot_reset"))
    setup.add_argument("--entry-proximity", choices=("at_pivot", "chased", "needs_judgment"), help=_input_help("ticker.setup", "entry_proximity"))
    setup.add_argument("--right-side-development", choices=("constructive", "compressed", "needs_chart"), help=_input_help("ticker.setup", "right_side_development"))
    setup.add_argument("--invalidation-price", type=positive_number, metavar="PRICE", help=_input_help("ticker.setup", "invalidation_price"))
    setup.add_argument("--invalidation-condition", metavar="TEXT", help=_input_help("ticker.setup", "invalidation_condition"))
    setup.add_argument("--tactic-opt-in", action="store_true", help=_input_help("ticker.setup", "tactic_opt_in"))
    setup.add_argument("--confirmation-debt", action="append", default=[], metavar="TEXT", help=_input_help("ticker.setup", "confirmation_debt"))
    setup.add_argument("--later-pivot-price", type=positive_number, metavar="PRICE", help=_input_help("ticker.setup", "later_pivot_price"))
    setup.add_argument("--later-pivot-condition", metavar="TEXT", help=_input_help("ticker.setup", "later_pivot_condition"))
    _common(setup, "ticker.setup")

    fundamentals = _capability_parser(ticker_sub, "fundamentals", "ticker.fundamentals")
    fundamentals.add_argument("ticker", help=_input_help("ticker.fundamentals", "ticker"))
    fundamentals.add_argument("--cik", help=_input_help("ticker.fundamentals", "cik"))
    fundamentals.add_argument("--power-play-quality", choices=("textbook", "acceptable"), help=_input_help("ticker.fundamentals", "power_play_quality"))
    for option in ("fundamentals_exception", "technical_eligibility", "price_volume_structure", "market_alignment", "risk_controls"):
        field = f"power_play_{option}"
        fundamentals.add_argument(f"--{field.replace('_', '-')}", action="store_true", help=_input_help("ticker.fundamentals", field))
    _common(fundamentals, "ticker.fundamentals")

    peers = _capability_parser(ticker_sub, "peers", "ticker.peers")
    peers.add_argument("ticker", help=_input_help("ticker.peers", "ticker"))
    peers.add_argument("--limit", type=int, default=10, metavar="N", help=_input_help("ticker.peers", "limit"))
    _common(peers, "ticker.peers")

    risk = _capability_parser(ticker_sub, "risk", "ticker.risk")
    risk.add_argument("ticker", help=_input_help("ticker.risk", "ticker"))
    risk.add_argument("--mode", choices=("prospective", "active"), default="prospective", help=_input_help("ticker.risk", "mode"))
    for field in ("entry_price", "stop_price", "upside_price", "current_price", "average_gain_pct", "invalidation_price"):
        risk.add_argument(f"--{field.replace('_', '-')}", type=positive_number, metavar="NUMBER", help=_input_help("ticker.risk", field))
    risk.add_argument("--entry-date", metavar="YYYY-MM-DD", help=_input_help("ticker.risk", "entry_date"))
    risk.add_argument("--stop-effective-date", metavar="YYYY-MM-DD", help=_input_help("ticker.risk", "stop_effective_date"))
    risk.add_argument("--market-state", choices=("favorable", "cautious", "defensive", "incomplete"), help=_input_help("ticker.risk", "market_state"))
    risk.add_argument("--eligibility-state", choices=("eligible", "avoid", "incomplete"), help=_input_help("ticker.risk", "eligibility_state"))
    risk.add_argument("--setup-state", choices=("ready", "wait", "avoid", "incomplete"), help=_input_help("ticker.risk", "setup_state"))
    risk.add_argument("--fundamentals-state", choices=("supports_convergence", "does_not_support_convergence", "waived_by_exception", "incomplete"), help=_input_help("ticker.risk", "fundamentals_state"))
    risk.add_argument("--invalidation-condition", metavar="TEXT", help=_input_help("ticker.risk", "invalidation_condition"))
    for field in ("completed_stop_breach", "live_stop_check", "live_stop_breach"):
        risk.add_argument(f"--{field.replace('_', '-')}", action="store_true", help=_input_help("ticker.risk", field))
    _common(risk, "ticker.risk")

    chart = _capability_parser(ticker_sub, "chart", "ticker.chart")
    chart.add_argument("ticker", help=_input_help("ticker.chart", "ticker"))
    chart.add_argument("--output-dir", metavar="PATH", help=_input_help("ticker.chart", "output_dir"))
    _common(chart, "ticker.chart")

    watchlist = _group_parser(sub, "watchlist", summary="Read or explicitly mutate the local research ledger.", details="show and history never create a missing database. record, annotate, and export are the only explicit ledger/file writes. The ledger never stores portfolio allocation or account data.")
    watchlist_sub = watchlist.add_subparsers(dest="watchlist_command", required=True, metavar="COMMAND")
    for name in ("show", "history", "record", "annotate", "export"):
        capability = f"watchlist.{name}"
        child = _capability_parser(watchlist_sub, name, capability)
        if name in {"history", "record", "annotate"}:
            child.add_argument("ticker", help=_input_help(capability, "ticker"))
        if name == "record":
            child.add_argument("--instrument-id", required=True, help=_input_help(capability, "instrument_id"))
            child.add_argument("--output-hash", required=True, help=_input_help(capability, "output_hash"))
            child.add_argument("--verdict", required=True, help=_input_help(capability, "verdict"))
            child.add_argument("--condition", help=_input_help(capability, "condition"))
            child.add_argument("--invalidation", help=_input_help(capability, "invalidation"))
            child.add_argument("--doctrine-id", action="append", dest="doctrine_ids", default=[], help=_input_help(capability, "doctrine_ids"))
            child.add_argument("--evidence-quality", help=_input_help(capability, "evidence_quality"))
            child.add_argument("--note", help=_input_help(capability, "note"))
        if name == "annotate":
            child.add_argument("--note", required=True, help=_input_help(capability, "note"))
        if name == "export":
            child.add_argument("--output", required=True, help=_input_help(capability, "output"))
        _common(child, capability)
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
        invalidation_price = request.pop("invalidation_price", None)
        invalidation_condition = request.pop("invalidation_condition", None)
        confirmation_debt = request.pop("confirmation_debt", [])
        later_pivot_price = request.pop("later_pivot_price", None)
        later_pivot_condition = request.pop("later_pivot_condition", None)
        entry: dict[str, Any] = {}
        if confirmation_debt:
            entry["confirmation_debt"] = confirmation_debt
        if later_pivot_price is not None or later_pivot_condition is not None:
            entry["minervini_later_pivot"] = {"price": later_pivot_price, "condition": later_pivot_condition}
        if invalidation_price is not None or invalidation_condition is not None:
            entry["invalidation"] = {"price": invalidation_price, "condition": invalidation_condition}
        if entry:
            request["entry"] = entry
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
    output_format = "full"
    try:
        args = parser.parse_args(argv)
        operation = _operation(args)
        output_format = getattr(args, "format", "full")
        payload = dispatch(args, runtime=runtime)
        code = 0
    except RequestError as error:
        payload = error_envelope(operation, error)
        code = 2
    except Exception as error:
        payload = envelope(
            operation,
            status="unavailable",
            data={"error": {"code": "internal_error", "message": redact(str(error)), "field": None, "retryable": False}},
        )
        code = 3
    payload = format_payload(payload, output_format)
    print(json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
