"""Compose provider snapshots and pure evaluators into public v2 operations."""

from __future__ import annotations

# Preserve the former module namespace while handlers own capability composition.

import re
import sys
import math
from dataclasses import dataclass
from datetime import date
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from collections.abc import Sequence
from typing import Any, Callable, Mapping
import pandas as pd
from ..dates import request_date as _request_date
from ..cache import ProviderCache
from ..capabilities import CAPABILITIES
from ..clock import AnalysisClock, resolve_as_of
from ..contracts import RequestError, envelope
from ..doctrine import get_claim, has_claim, list as list_doctrine, validate as validate_doctrine
from ..eligibility import EligibilityEvidence, evaluate_eligibility
from ..fundamentals import ACCOUNTING_INTEGRITY_WORDS as FUNDAMENTALS_ACCOUNTING_INTEGRITY, GOING_CONCERN_WORDS as FUNDAMENTALS_GOING_CONCERN, LEADER_CATEGORIES as FUNDAMENTALS_LEADER_CATEGORIES, MARKET_REGIMES as FUNDAMENTALS_MARKET_REGIMES, evaluate_fundamentals
from ..market import build_market_candidates, evaluate_market_snapshot, evidence_quality
from ..market_evidence import build_market_evidence, carries_a_readable_bar
from ..peer_collection import collect_same_industry_peer_rows
from ..peers import compare_same_industry_peers
from ..providers import DETAIL_LIMIT, ProviderSnapshot, ProviderUnavailable, SnapshotMeta, redact
from ..providers.nasdaq import SecurityRecord
from ..providers.rs import REQUIRED_PACKAGE_VERSION
from ..power_play import FLAG_STILL_FORMING, evaluate_power_play
from ..power_play_evidence import ASKED_UNDER, CHART_READING_WORDS, build_power_play_evidence
from ..management_evidence import AVERAGES as MANAGEMENT_AVERAGES, BLOCKS as MANAGEMENT_BLOCKS, build_management_evidence
from ..risk import AUDIT_BASIS as _AUDIT_BASIS, crosses as _crosses, declares_exit_plan, reduce_risk, settled_breach, supplied_price_path, triggered_state as _triggered_state
from ..runtime import Runtime, _local_configuration
from ..setup import evaluate_setup
from ..swings import canonical_chain
from ..setup_evidence import build_setup_evidence
from ..setup_structure import read_bars, read_price_kinds, session_index
from ..stop_audit import _positive, _check_declared_shapes, _UNCROSSABLE_REASONS, _COVERAGE_FIELDS, _combine_audits, _max_high_since, _completed_stop_path, _attest_components, _AUDITED_COLUMNS
from ..technical import build_eligibility_evidence


def _clock(value: Any) -> AnalysisClock:
    try:
        return resolve_as_of(value)
    except ValueError as error:
        raise RequestError(str(error), "as_of") from error


def _as_of(clock: AnalysisClock) -> dict[str, Any]:
    return {
        "mode": clock.mode,
        "date": clock.date.isoformat(),
        "timezone": clock.timezone,
        "completed_session": clock.completed_session,
    }


def _cached_provider(
    runtime: Runtime,
    request: Mapping[str, Any],
    clock: AnalysisClock,
    *,
    capability: str,
    provider: str,
    operation: str,
    params: Mapping[str, Any],
    fetch: Callable[[], ProviderSnapshot[Any]],
    ttl_seconds: float | None = None,
) -> ProviderSnapshot[Any]:
    if runtime.cache is None:
        return fetch()
    return runtime.cache.call(
        provider,
        f"{capability}:{operation}",
        {**params, "as_of": clock.date.isoformat()},
        clock.date,
        fetch,
        ttl_seconds=ttl_seconds,
        no_cache=request.get("no_cache") is True,
    )


def _clean_request(request: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in request.items() if value is not None}


def _ticker(value: Any) -> str:
    ticker = str(value or "").strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", ticker):
        raise RequestError("ticker must be a US-listed symbol", "ticker")
    return ticker


def _source(meta: SnapshotMeta) -> dict[str, Any]:
    return {
        "provider": meta.provider,
        "retrieved_at": meta.retrieved_at.isoformat(),
        "as_of": meta.as_of.isoformat() if meta.as_of is not None else None,
        "provider_version": meta.provider_version,
        "coverage": dict(meta.coverage),
        "stale": meta.stale,
        "content_sha256": meta.content_sha256,
    }


def _stale_price_gap(meta: SnapshotMeta) -> dict[str, Any] | None:
    """Report price history that could not reach the requested completed session.

    A verdict computed from the previous session but stamped with this one is
    indistinguishable from a current verdict, so callers withhold the judgment
    rather than qualifying it.
    """

    if not meta.stale:
        return None
    return {
        "id": "completed_price_evidence",
        "provider": meta.provider,
        "reason": "session_behind_as_of",
        "required": True,
        "attempts": 1,
        "retryable": True,
        "detail": f"last completed bar {meta.coverage.get('last_completed_bar')} is behind requested session {meta.coverage.get('requested_session')}",
    }


def _missing_provider(error: ProviderUnavailable, *, required: bool = True) -> dict[str, Any]:
    gap = {
        "id": error.operation or error.provider,
        "provider": error.provider,
        "reason": error.reason,
        "required": required,
        "attempts": error.attempts,
        "retryable": error.retryable,
    }
    if error.detail:
        gap["detail"] = error.detail
    return gap


@dataclass(frozen=True)
class PriceRead:
    capability: str
    stub: Mapping[str, Any] | None = None
    next_capabilities: list[str] | None = None
    partial_extra: Callable[[SnapshotMeta], Mapping[str, Any]] | None = None


def _price_read(
    runtime: Runtime, request: Mapping[str, Any], clock: AnalysisClock, ticker: str, spec: PriceRead
) -> tuple[ProviderSnapshot[Any] | None, dict[str, Any] | None, list[dict[str, Any]]]:
    try:
        prices = _cached_provider(
            runtime,
            request,
            clock,
            capability=spec.capability,
            provider="yfinance",
            operation="daily_bars",
            params={"ticker": ticker},
            fetch=lambda: runtime.price_history(ticker, clock.date.isoformat()),
        )
    except ProviderUnavailable as error:
        if spec.stub is None:
            raise
        gap = _missing_provider(error)
        prices = None
        sources = []
    else:
        sources = [_source(prices.meta)]
        if spec.stub is None:
            return prices, None, sources
        gap = _stale_price_gap(prices.meta)
        if gap is None:
            return prices, None, sources
    data = {"ticker": ticker, **spec.stub}
    kwargs = {}
    if prices is not None:
        kwargs["sources"] = sources
        if spec.partial_extra is not None:
            data.update(spec.partial_extra(prices.meta))
    if spec.next_capabilities is not None:
        kwargs["next_capabilities"] = spec.next_capabilities
    return prices, envelope(
        spec.capability,
        request=_clean_request({**request, "ticker": ticker}),
        as_of=_as_of(clock),
        status="partial" if prices is not None else "unavailable",
        data=data,
        missing=[gap],
        **kwargs,
    ), sources


def _reducer_named_doctrine_ids(data: Mapping[str, Any], request: Mapping[str, Any]) -> set[str]:
    """The claims the payload names, minus everything the caller sent and the payload echoes.

    A citation says this harness applied a claim, so a caller must not be able to add one. Both
    `ticker.setup` and `ticker.risk` hand parts of the request straight back -- the entry
    object, the completed price path, the reasons a high was withheld -- and a `doctrine_id`
    planted in any of them was harvested and published as doctrine the verdict was reached
    under. Decision 301 accepts it because it resolves, and the read-and-cited guard accepts it
    because it only looks for citations that are missing.

    A top-level key the caller sent that comes back in `data` is the definition of an echo, so
    that is the rule rather than a list of the fields found by hand -- a list of those is a list
    that goes stale by one the next time a field is added.
    """

    return _named_doctrine_ids({key: value for key, value in data.items() if key not in request})


def _named_doctrine_ids(data: Mapping[str, Any]) -> set[str]:
    """Every registered claim the payload names, anywhere in it."""

    named: set[str] = set()

    def collect(value: Any) -> None:
        if isinstance(value, Mapping):
            # Every key that names a claim, not only the one called doctrine_id: a block
            # naming the claim a disclaimer came from cites it just as much, and a citation
            # the envelope leaves out is a claim the result used and did not admit to.
            # Caller-supplied evidence travels through the payload, so a name counts only
            # if the registry holds it: an id nobody can look up cites nothing.
            for key, claim in value.items():
                if not isinstance(key, str) or not key.endswith("doctrine_id"):
                    continue
                if isinstance(claim, str) and has_claim(claim):
                    named.add(claim)
            # A block that reads more than one claim -- a measurement plus the convention
            # that sized its window -- names them all, and each is checked the same way.
            for key, extras in value.items():
                if not isinstance(key, str) or not key.endswith("doctrine_ids"):
                    continue
                for extra in extras or []:
                    if isinstance(extra, str) and has_claim(extra):
                        named.add(extra)
            for item in value.values():
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(data)
    return named


def execute(operation: str, request: Mapping[str, Any], *, runtime: Runtime | None = None) -> dict[str, Any]:
    """Execute one composable capability without printing or mutating implicit state."""

    if not isinstance(request, Mapping):
        raise RequestError("request must be an object", "request")
    # The registry pair answers from the registry alone, so they take no runtime and reach no
    # provider. They live here rather than only in the CLI because `execute` is a public seam
    # too, and routed in one place and not the other they came back from this one as the
    # unimplemented-operation envelope -- under their own operation name. They answer before
    # the default runtime is built, not merely without using it: these two are what an analyst
    # runs when something else is already broken, and a cache directory this process cannot
    # resolve would otherwise turn reading the interface into an internal error.
    if operation == "capabilities":
        return envelope(operation, data={"capabilities": [CAPABILITIES[name].listing() for name in sorted(CAPABILITIES)]})
    if operation == "describe":
        return _describe(request)
    if operation == "doctrine.list":
        return _doctrine_list(request)
    runtime = runtime if runtime is not None else Runtime(cache=ProviderCache())
    if operation == "clock":
        return _clock_operation(request)
    if operation == "health":
        return _health(request, runtime)
    if operation == "doctrine.show":
        return _doctrine_show(request)
    if operation == "ticker.qualify":
        return _qualify(request, runtime)
    if operation == "ticker.swings":
        return _swings(request, runtime)
    if operation == "ticker.setup":
        return _setup(request, runtime)
    if operation == "ticker.power-play":
        return _power_play(request, runtime)
    if operation == "ticker.cik":
        return _ticker_cik(request, runtime)
    if operation == "ticker.fundamentals":
        return _fundamentals(request, runtime)
    if operation == "ticker.peers":
        return _peers(request, runtime)
    if operation == "ticker.risk":
        return _risk(request, runtime)
    if operation == "ticker.chart":
        return _chart(request, runtime)
    if operation == "market.candidates":
        return _market_candidates(request, runtime)
    if operation == "market.snapshot":
        return _market_snapshot(request, runtime)
    if operation.startswith("watchlist."):
        return _watchlist(request, operation, runtime)
    return envelope(
        operation,
        request=_clean_request(request),
        status="unavailable",
        data={"reason": "capability implementation pending"},
        missing=[{"id": operation, "reason": "implementation_pending", "required": True}],
    )


from .chart import _chart, _chart_envelope, _render
from .company import _fundamentals, _peers, _ticker_cik, _valuation_closes
from .discovery import _clock_operation, _describe, _doctrine_list, _doctrine_show, _health
from .market import _candidate_row, _leaders_within_limit, _market_candidates, _market_snapshot, _ohlcv_rows, _optional_leader_read, _ranked_groups, _ranked_leaders
from .risk import _risk, _risk_doctrine_ids
from .ticker import _CHAIN_COMPLETENESS, _CHART_READING_CONVENTION, _SEGMENTATION_CONVENTION, _TRADING_WEEK_CONVENTION, _VOLUME_STATE_CONVENTION, _chart_digest, _chart_readings, _missing_reason, _power_play, _qualify, _refuse_unusable_setup_request, _segmentation_reason, _setup, _swings
from .watchlist import _watchlist


__all__ = ["Runtime", "execute"]
