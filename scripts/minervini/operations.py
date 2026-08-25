"""Compose provider snapshots and pure evaluators into public v2 operations."""

from __future__ import annotations

import re
import os
import sys
import math
from dataclasses import dataclass, field
from datetime import date
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Callable, Mapping

import pandas as pd

from .cache import ProviderCache
from .clock import AnalysisClock, resolve_as_of
from .contracts import RequestError, envelope
from .doctrine import get_claim, validate as validate_doctrine
from .eligibility import EligibilityEvidence, evaluate_eligibility
from .fundamentals import evaluate_fundamentals
from .ledger import Ledger
from .market import build_market_candidates, evaluate_market_snapshot
from .market_evidence import build_market_evidence
from .peer_collection import collect_same_industry_peer_rows
from .peers import compare_same_industry_peers
from .providers import DETAIL_LIMIT, ProviderSnapshot, ProviderUnavailable, SnapshotMeta, fetch_with_one_retry, redact
from .providers.finviz import raw_snapshot as finviz_raw_snapshot
from .providers.nasdaq import SecurityRecord, current_security_master, historical_security_master
from .providers.rs import REQUIRED_PACKAGE_VERSION, industry_ranking_snapshot, industry_top_snapshot, rating_snapshot, sector_ranking_snapshot, top_snapshot
from .providers.sec import fetch_company_facts, fetch_company_submissions, fetch_company_tickers, normalize_filed_facts
from .providers.yfinance import completed_daily_bars, current_classification_snapshot
from .risk import declares_exit_plan, reduce_risk, settled_breach
from .setup import evaluate_setup
from .setup_evidence import build_setup_evidence
from .technical import build_eligibility_evidence


PriceHistory = Callable[[str, str | None], ProviderSnapshot[Any]]
RatingSnapshot = Callable[[str, str | None], ProviderSnapshot[dict[str, Any]]]
SecurityMaster = Callable[[str | None], ProviderSnapshot[list[SecurityRecord]]]
LedgerFactory = Callable[[], Ledger]
FundamentalsEvidence = Callable[[str, str, str | None], ProviderSnapshot[dict[str, Any]]]
RankedRows = Callable[[str], ProviderSnapshot[list[dict[str, Any]]]]
MarketLeaders = Callable[[str, int], ProviderSnapshot[list[dict[str, Any]]]]
FinvizBreadth = Callable[[str], ProviderSnapshot[str]]
CurrentClassification = Callable[[str], ProviderSnapshot[dict[str, str]]]
IndustryTop = Callable[[str, str, int], ProviderSnapshot[list[dict[str, Any]]]]


def _default_price_history(ticker: str, as_of: str | None) -> ProviderSnapshot[Any]:
    return completed_daily_bars(ticker, as_of=as_of)


def _default_rs_rating(ticker: str, as_of: str | None) -> ProviderSnapshot[dict[str, Any]]:
    return rating_snapshot(ticker, as_of=as_of)


def _default_security_master(as_of: str | None) -> ProviderSnapshot[list[SecurityRecord]]:
    if as_of is not None and resolve_as_of(as_of).date != resolve_as_of().date:
        return historical_security_master(as_of)
    try:
        import requests
    except Exception as error:
        raise ProviderUnavailable("nasdaq", "requests_package_unavailable", operation="security_master") from error

    def request(url: str) -> str:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.text

    return current_security_master(request)


def _default_fundamentals_evidence(ticker: str, as_of: str, cik: str | None) -> ProviderSnapshot[dict[str, Any]]:
    user_agent = os.environ.get("MINERVINI_SEC_USER_AGENT", "")
    if not user_agent:
        raise ProviderUnavailable("sec", "identifiable_user_agent_required", operation="filed_facts")
    try:
        import requests
    except Exception as error:
        raise ProviderUnavailable("sec", "requests_package_unavailable", operation="filed_facts") from error

    snapshots: list[ProviderSnapshot[Any]] = []
    resolved_cik = cik
    if resolved_cik is None:
        ticker_lookup = fetch_company_tickers(request_get=requests.get, user_agent=user_agent)
        snapshots.append(ticker_lookup)
        record = ticker_lookup.data.get(ticker)
        if record is None:
            raise ProviderUnavailable("sec", "ticker_not_found", operation="company_tickers")
        resolved_cik = record["cik"]
    facts = fetch_company_facts(resolved_cik, request_get=requests.get, user_agent=user_agent)
    submissions = fetch_company_submissions(resolved_cik, request_get=requests.get, user_agent=user_agent)
    snapshots.extend((facts, submissions))
    evidence = normalize_filed_facts(facts.data, submissions.data, as_of=as_of)
    content_hashes = [snapshot.meta.content_sha256 for snapshot in snapshots if snapshot.meta.content_sha256]
    return ProviderSnapshot(
        evidence,
        SnapshotMeta(
            provider="sec",
            retrieved_at=max(snapshot.meta.retrieved_at for snapshot in snapshots),
            as_of=date.fromisoformat(as_of),
            coverage={
                "kind": "filed_facts_as_of",
                "cik": resolved_cik,
                "documents": [dict(snapshot.meta.coverage) for snapshot in snapshots],
            },
            content_sha256=sha256("|".join(content_hashes).encode()).hexdigest() if content_hashes else None,
        ),
    )


def _default_finviz_breadth(as_of: str) -> ProviderSnapshot[str]:
    try:
        import requests
    except Exception as error:
        raise ProviderUnavailable("finviz", "requests_package_unavailable", operation="raw_snapshot") from error

    def fetch() -> str:
        response = requests.get(
            "https://finviz.com/",
            headers={"User-Agent": "Mozilla/5.0 (compatible; MinerviniHarness/2.0)"},
            timeout=30,
        )
        response.raise_for_status()
        return response.text

    return finviz_raw_snapshot(fetch=fetch, as_of=as_of)


def _default_sector_ranking(as_of: str) -> ProviderSnapshot[list[dict[str, Any]]]:
    return sector_ranking_snapshot(as_of)


def _default_industry_ranking(as_of: str) -> ProviderSnapshot[list[dict[str, Any]]]:
    return industry_ranking_snapshot(as_of)


def _default_market_leaders(as_of: str, limit: int) -> ProviderSnapshot[list[dict[str, Any]]]:
    return top_snapshot(as_of, n=limit)


def _default_current_classification(ticker: str) -> ProviderSnapshot[dict[str, str]]:
    return current_classification_snapshot(ticker)


def _default_industry_top(industry: str, as_of: str, limit: int) -> ProviderSnapshot[list[dict[str, Any]]]:
    return industry_top_snapshot(industry, as_of, n=limit)


def _probe_rs() -> None:
    from .providers.rs import _client

    fetch_with_one_retry("ibd-rs-rating", "dates", _client().dates)


def _probe_sec() -> None:
    user_agent = os.environ.get("MINERVINI_SEC_USER_AGENT", "")
    if not user_agent:
        raise ProviderUnavailable("sec", "identifiable_user_agent_required", operation="company_tickers")
    import requests

    fetch_company_tickers(request_get=requests.get, user_agent=user_agent)


def _local_configuration() -> dict[str, dict[str, Any]]:
    """Report the local settings that silently disable a provider when absent.

    Both were dead here without the runtime saying so: an unpopulated CA bundle
    kills every stdlib-TLS provider, and an unset SEC User-Agent stops filed
    fundamentals before a request is made.
    """

    import ssl

    ca_certificates = ssl.create_default_context().cert_store_stats()["x509_ca"]
    user_agent = os.environ.get("MINERVINI_SEC_USER_AGENT", "")
    return {
        "tls_ca_bundle": {
            "ready": ca_certificates > 0,
            "required": True,
            "detail": None if ca_certificates else "the interpreter loaded no CA certificates; stdlib TLS cannot verify any host",
        },
        "sec_user_agent": {
            "ready": bool(user_agent),
            "required": False,
            "detail": None if user_agent else "MINERVINI_SEC_USER_AGENT is unset; ticker fundamentals cannot reach SEC",
        },
    }


def _probe_yfinance() -> None:
    import yfinance as yf

    frame = fetch_with_one_retry("yfinance", "daily_bars", lambda: yf.Ticker("SPY").history(period="5d", interval="1d"))
    if frame is None or frame.empty:
        raise ProviderUnavailable("yfinance", "no_completed_daily_bars", operation="daily_bars")


def _default_reachability_probes() -> dict[str, Callable[[], None]]:
    """Name the cheapest decisive call per probed provider.

    Nasdaq's security master is a multi-megabyte download, so it is deliberately
    not probed; its failures surface loudly in the operations that need it.
    """

    return {"yfinance": _probe_yfinance, "ibd-rs-rating": _probe_rs, "sec": _probe_sec}


@dataclass(frozen=True)
class Runtime:
    """Replace only external boundaries in deterministic integration tests."""

    price_history: PriceHistory = field(default_factory=lambda: _default_price_history)
    rs_rating: RatingSnapshot = field(default_factory=lambda: _default_rs_rating)
    security_master: SecurityMaster = field(default_factory=lambda: _default_security_master)
    fundamentals_evidence: FundamentalsEvidence = field(default_factory=lambda: _default_fundamentals_evidence)
    sector_ranking: RankedRows = field(default_factory=lambda: _default_sector_ranking)
    industry_ranking: RankedRows = field(default_factory=lambda: _default_industry_ranking)
    market_leaders: MarketLeaders = field(default_factory=lambda: _default_market_leaders)
    finviz_breadth: FinvizBreadth = field(default_factory=lambda: _default_finviz_breadth)
    current_classification: CurrentClassification = field(default_factory=lambda: _default_current_classification)
    industry_top: IndustryTop = field(default_factory=lambda: _default_industry_top)
    ledger_factory: LedgerFactory = field(default_factory=lambda: Ledger)
    reachability_probes: Mapping[str, Callable[[], None]] = field(default_factory=_default_reachability_probes)
    cache: ProviderCache | None = None


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


def _clock_operation(request: Mapping[str, Any]) -> dict[str, Any]:
    clock = _clock(request.get("as_of"))
    return envelope(
        "clock",
        request=_clean_request(request),
        as_of=_as_of(clock),
        data={"date": clock.date.isoformat(), "mode": clock.mode},
    )


def _health(request: Mapping[str, Any], runtime: Runtime) -> dict[str, Any]:
    clock = _clock(request.get("as_of"))
    dependencies: dict[str, dict[str, Any]] = {}
    for distribution, required in (("ibd-rs-rating", REQUIRED_PACKAGE_VERSION), ("yfinance", None)):
        try:
            installed = version(distribution)
        except PackageNotFoundError:
            installed = None
        dependencies[distribution] = {
            "installed": installed,
            "required": required,
            "ready": installed is not None and (required is None or installed == required),
        }
    doctrine = validate_doctrine()
    configuration = _local_configuration()
    ready = doctrine["valid"] and all(item["ready"] for item in dependencies.values())
    ready = ready and all(item["ready"] for item in configuration.values() if item["required"])
    missing = [
        {"id": name, "reason": "package_missing_or_version_mismatch", "required": True}
        for name, item in dependencies.items()
        if not item["ready"]
    ]
    missing.extend(
        {"id": name, "reason": "local_configuration_missing", "required": item["required"], "detail": item["detail"]}
        for name, item in configuration.items()
        if not item["ready"]
    )
    data: dict[str, Any] = {
        "ready": ready,
        "python": sys.version.split()[0],
        "dependencies": dependencies,
        "configuration": configuration,
        "doctrine": doctrine,
        "reachability": {"checked": False, "providers": {}},
    }
    if request.get("probe") is True:
        probed: dict[str, Any] = {}
        for name, probe in runtime.reachability_probes.items():
            try:
                probe()
            except ProviderUnavailable as error:
                probed[name] = {"reachable": False, "reason": error.reason, "detail": error.detail}
                missing.append(_missing_provider(error))
            except Exception as error:  # A diagnostic must diagnose, never become the failure.
                detail = redact(f"{type(error).__name__}: {error}")[:DETAIL_LIMIT]
                probed[name] = {"reachable": False, "reason": "probe_failed", "detail": detail}
                missing.append({"id": name, "provider": name, "reason": "probe_failed", "required": True, "attempts": 1, "retryable": True, "detail": detail})
            else:
                probed[name] = {"reachable": True, "reason": None, "detail": None}
        ready = ready and all(item["reachable"] for item in probed.values())
        data["ready"] = ready
        data["reachability"] = {"checked": True, "providers": probed}
    return envelope(
        "health",
        request=_clean_request(request),
        as_of=_as_of(clock),
        status="ok" if ready else "partial",
        data=data,
        missing=missing,
    )


def _doctrine_show(request: Mapping[str, Any]) -> dict[str, Any]:
    claim_id = request.get("claim_id")
    if not isinstance(claim_id, str) or not claim_id:
        raise RequestError("claim_id is required", "claim_id")
    try:
        result = get_claim(claim_id)
    except KeyError as error:
        raise RequestError(str(error), "claim_id") from error
    clock = _clock(request.get("as_of"))
    return envelope(
        "doctrine.show",
        request=_clean_request(request),
        as_of=_as_of(clock),
        data={"claim": result["claim"]},
        sources=[{"provider": "doctrine_registry", "provenance": result["provenance"]}],
        doctrine_ids=[claim_id],
    )


def _qualify(request: Mapping[str, Any], runtime: Runtime) -> dict[str, Any]:
    ticker = _ticker(request.get("ticker"))
    clock = _clock(request.get("as_of"))
    requested_as_of = clock.date.isoformat()
    try:
        prices = _cached_provider(
            runtime,
            request,
            clock,
            capability="ticker.qualify",
            provider="yfinance",
            operation="daily_bars",
            params={"ticker": ticker},
            fetch=lambda: runtime.price_history(ticker, requested_as_of),
        )
    except ProviderUnavailable as error:
        return envelope(
            "ticker.qualify",
            request=_clean_request({**request, "ticker": ticker}),
            as_of=_as_of(clock),
            status="unavailable",
            data={"ticker": ticker, "eligibility_state": "incomplete"},
            missing=[_missing_provider(error)],
            next_capabilities=[],
        )

    sources = [_source(prices.meta)]
    stale_price = _stale_price_gap(prices.meta)
    if stale_price is not None:
        return envelope(
            "ticker.qualify",
            request=_clean_request({**request, "ticker": ticker}),
            as_of=_as_of(clock),
            status="partial",
            data={"ticker": ticker, "eligibility_state": "incomplete", "price_as_of": prices.meta.as_of.isoformat() if prices.meta.as_of else None},
            missing=[stale_price],
            sources=sources,
            next_capabilities=[],
        )
    missing: list[dict[str, Any]] = []
    rating: int | None = None
    rating_date: str | None = None
    try:
        rs = _cached_provider(
            runtime,
            request,
            clock,
            capability="ticker.qualify",
            provider="ibd-rs-rating",
            operation="rating",
            params={"ticker": ticker},
            fetch=lambda: runtime.rs_rating(ticker, requested_as_of),
        )
    except ProviderUnavailable as error:
        missing.append(_missing_provider(error))
    else:
        rating = int(rs.data["rating"])
        rating_date = str(rs.data["rating_date"])
        sources.append(_source(rs.meta))

    measured = build_eligibility_evidence(
        prices.data,
        rs_rating=rating,
        primary_base_quality=request.get("primary_base_quality"),
        primary_base_emergence=request.get("primary_base_emergence"),
        primary_base_long_correction=request.get("primary_base_long_correction"),
    )
    result = evaluate_eligibility(EligibilityEvidence.from_mapping(measured)).to_dict()
    # A band the harness measured has to reach the caller, or the rule that every band
    # is reported with its range is prose nothing carries out.
    primary_base = measured.get("primary_base") or {}
    bands = {"primary_base.depth": primary_base["depth_band"]} if primary_base.get("depth_band") else {}
    next_capabilities = ["ticker.setup", "ticker.fundamentals"] if result["eligibility_state"] == "eligible" else []
    if result["eligibility_state"] == "incomplete" and result["route"] == "recent_ipo_primary_base":
        next_capabilities = ["ticker.chart"]
    return envelope(
        "ticker.qualify",
        request=_clean_request({**request, "ticker": ticker}),
        as_of=_as_of(clock),
        status="partial" if missing else "ok",
        data={
            "ticker": ticker,
            "route": result["route"],
            "eligibility_state": result["eligibility_state"],
            "completed_session_count": len(prices.data),
            "price_as_of": measured["as_of"],
            "rs_rating": rating,
            "rs_rating_date": rating_date,
            "bands": bands,
        },
        signals=result["signals"],
        missing=missing,
        sources=sources,
        doctrine_ids=result["doctrine_ids"],
        next_capabilities=next_capabilities,
    )


def _setup(request: Mapping[str, Any], runtime: Runtime) -> dict[str, Any]:
    ticker = _ticker(request.get("ticker"))
    clock = _clock(request.get("as_of"))
    try:
        prices = _cached_provider(
            runtime,
            request,
            clock,
            capability="ticker.setup",
            provider="yfinance",
            operation="daily_bars",
            params={"ticker": ticker},
            fetch=lambda: runtime.price_history(ticker, clock.date.isoformat()),
        )
    except ProviderUnavailable as error:
        return envelope(
            "ticker.setup",
            request=_clean_request({**request, "ticker": ticker}),
            as_of=_as_of(clock),
            status="unavailable",
            data={"ticker": ticker, "setup_state": "incomplete"},
            missing=[_missing_provider(error)],
        )
    stale_price = _stale_price_gap(prices.meta)
    if stale_price is not None:
        return envelope(
            "ticker.setup",
            request=_clean_request({**request, "ticker": ticker}),
            as_of=_as_of(clock),
            status="partial",
            data={"ticker": ticker, "setup_state": "incomplete"},
            missing=[stale_price],
            sources=[_source(prices.meta)],
        )
    swings = request.get("swing")
    if swings is not None and not isinstance(swings, list):
        raise RequestError("swing must be a list of completed session dates", "swing")
    entry = request.get("entry")
    if entry is not None and not isinstance(entry, Mapping):
        raise RequestError("entry must be an object", "entry")
    evidence = build_setup_evidence(
        prices.data,
        swings or [],
        entry_kind=request.get("entry_kind") or "completed_pivot",
        tactic_opt_in=request.get("tactic_opt_in") is True,
        entry=entry,
        right_side_development=request.get("right_side_development"),
        chain_completeness=request.get("chain_completeness"),
        completeness_source=request.get("completeness_source"),
        entry_proximity=request.get("entry_proximity"),
    )
    result = evaluate_setup(evidence)
    missing = [{"id": item, "reason": "evidence_required", "required": True} for item in result["missing"]]
    status = "needs_input" if result["setup_state"] == "incomplete" else "ok"
    return envelope(
        "ticker.setup",
        request=_clean_request({**request, "ticker": ticker}),
        as_of=_as_of(clock),
        status=status,
        # Contrast evidence rides in the payload, never in `signals`: a reducer or a caller
        # scanning signal states would read another practitioner's disagreement as this
        # harness's own missing evidence.
        data={"ticker": ticker, **result, "contrast": evidence["contrast"]},
        signals=result["signals"],
        missing=missing,
        sources=[_source(prices.meta)],
        doctrine_ids=sorted({str(item["doctrine_id"]) for item in result["signals"] if item.get("doctrine_id")}),
        next_capabilities=["ticker.chart"] if status == "needs_input" else ["ticker.risk"],
    )


def _fundamentals(request: Mapping[str, Any], runtime: Runtime) -> dict[str, Any]:
    ticker = _ticker(request.get("ticker"))
    clock = _clock(request.get("as_of"))
    cik = request.get("cik")
    if cik is not None and (not isinstance(cik, str) or not cik.isdigit() or len(cik) > 10):
        raise RequestError("cik must contain at most ten digits", "cik")
    if request.get("as_of") is not None and cik is None:
        return envelope(
            "ticker.fundamentals",
            request=_clean_request({**request, "ticker": ticker}),
            as_of=_as_of(clock),
            status="needs_input",
            data={"ticker": ticker, "fundamentals_state": "incomplete"},
            missing=[{"id": "cik", "reason": "stable_historical_identity_required", "required": True}],
        )
    power_play = request.get("power_play")
    if power_play is not None and not isinstance(power_play, Mapping):
        raise RequestError("power_play must be an object", "power_play")
    try:
        snapshot = _cached_provider(
            runtime,
            request,
            clock,
            capability="ticker.fundamentals",
            provider="sec",
            operation="filed_facts",
            params={"ticker": ticker, "cik": cik},
            fetch=lambda: runtime.fundamentals_evidence(ticker, clock.date.isoformat(), cik),
        )
    except ProviderUnavailable as error:
        return envelope(
            "ticker.fundamentals",
            request=_clean_request({**request, "ticker": ticker}),
            as_of=_as_of(clock),
            status="unavailable",
            data={"ticker": ticker, "fundamentals_state": "incomplete"},
            missing=[_missing_provider(error)],
        )
    result = evaluate_fundamentals(snapshot.data, as_of=clock.date.isoformat(), power_play=power_play)
    missing = [{"id": item, "reason": "filed_evidence_missing", "required": True} for item in result["missing"]]
    status = "partial" if result["fundamentals_state"] == "incomplete" else "ok"
    doctrine_ids = ["scope.data_integrity"]
    if power_play is not None:
        doctrine_ids.append("fundamentals.power_play_exception")
    return envelope(
        "ticker.fundamentals",
        request=_clean_request({**request, "ticker": ticker}),
        as_of=_as_of(clock),
        status=status,
        data={"ticker": ticker, **result},
        signals=result["signals"],
        missing=missing,
        sources=[_source(snapshot.meta)],
        doctrine_ids=doctrine_ids,
        next_capabilities=["ticker.peers", "ticker.risk"],
    )


def _peers(request: Mapping[str, Any], runtime: Runtime) -> dict[str, Any]:
    ticker = _ticker(request.get("ticker"))
    clock = _clock(request.get("as_of"))
    current_clock = resolve_as_of()
    limit = request.get("limit", 10)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 20:
        raise RequestError("limit must be an integer from 1 to 20", "limit")
    if request.get("as_of") is not None and clock.date != current_clock.date:
        return envelope(
            "ticker.peers",
            request=_clean_request({**request, "ticker": ticker}),
            as_of=_as_of(clock),
            status="unavailable",
            data={"ticker": ticker, "comparison_state": "incomplete", "target": None, "peers": []},
            missing=[
                {
                    "id": "current_classification",
                    "provider": "yfinance",
                    "reason": "historical_classification_unavailable",
                    "required": True,
                    "attempts": 0,
                    "retryable": False,
                }
            ],
        )

    sources: list[dict[str, Any]] = []
    try:
        classification = _cached_provider(
            runtime,
            request,
            clock,
            capability="ticker.peers",
            provider="yfinance",
            operation="current_classification",
            params={"ticker": ticker},
            fetch=lambda: runtime.current_classification(ticker),
            ttl_seconds=900,
        )
        master = _cached_provider(
            runtime,
            request,
            clock,
            capability="ticker.peers",
            provider="nasdaq",
            operation="current_security_master",
            params={},
            fetch=lambda: runtime.security_master(None),
            ttl_seconds=900,
        )
        industry = str(classification.data["industry"])
        industry_rows = _cached_provider(
            runtime,
            request,
            clock,
            capability="ticker.peers",
            provider="ibd-rs-rating",
            operation="industry_top",
            params={"industry": industry, "limit": limit + 1},
            fetch=lambda: runtime.industry_top(industry, clock.date.isoformat(), limit + 1),
        )
    except ProviderUnavailable as error:
        return envelope(
            "ticker.peers",
            request=_clean_request({**request, "ticker": ticker}),
            as_of=_as_of(clock),
            status="unavailable",
            data={"ticker": ticker, "comparison_state": "incomplete", "target": None, "peers": []},
            missing=[_missing_provider(error)],
        )
    sources.extend((_source(classification.meta), _source(master.meta), _source(industry_rows.meta)))

    provider_missing: list[dict[str, Any]] = []
    target_rating: Mapping[str, Any] | int | float = {}
    try:
        rating = _cached_provider(
            runtime,
            request,
            clock,
            capability="ticker.peers",
            provider="ibd-rs-rating",
            operation="rating",
            params={"ticker": ticker},
            fetch=lambda: runtime.rs_rating(ticker, clock.date.isoformat()),
        )
    except ProviderUnavailable as error:
        provider_missing.append(_missing_provider(error))
    else:
        target_rating = rating.data
        sources.append(_source(rating.meta))

    symbols = [ticker]
    for row in industry_rows.data:
        symbol = row.get("ticker") if isinstance(row, Mapping) else None
        if isinstance(symbol, str) and symbol not in symbols:
            symbols.append(symbol)
    completed_prices: dict[str, Any] = {}
    for symbol in symbols:
        try:
            prices = _cached_provider(
                runtime,
                request,
                clock,
                capability="ticker.peers",
                provider="yfinance",
                operation="daily_bars",
                params={"ticker": symbol},
                fetch=lambda symbol=symbol: runtime.price_history(symbol, clock.date.isoformat()),
            )
        except ProviderUnavailable as error:
            missing = _missing_provider(error, required=symbol == ticker)
            missing["ticker"] = symbol
            provider_missing.append(missing)
        else:
            sources.append(_source(prices.meta))
            stale_price = _stale_price_gap(prices.meta)
            if stale_price is not None:
                stale_price["ticker"] = symbol
                stale_price["required"] = symbol == ticker
                provider_missing.append(stale_price)
            else:
                completed_prices[symbol] = prices.data

    try:
        collected = collect_same_industry_peer_rows(
            classification.data,
            master.data,
            industry_rows.data,
            target_rating,
            completed_prices,
            as_of=clock.date.isoformat(),
        )
    except ValueError as error:
        raise RequestError(str(error), "ticker") from error
    identity_missing = [
        {
            "id": f"peer_identity.{item['ticker']}",
            "ticker": item["ticker"],
            "reason": item["reason"],
            "required": item["ticker"] == ticker,
        }
        for item in collected["missing"]
    ]
    if collected["target"] is None:
        result = {
            "comparison_state": "incomplete",
            "target": None,
            "peer_count": 0,
            "peers": [],
            "rank_basis": [],
            "missing": [],
            "exclusions": [],
        }
    else:
        try:
            result = compare_same_industry_peers(collected["target"], collected["candidates"])
        except ValueError as error:
            raise RequestError(str(error), "ticker") from error
        result["peers"] = result["peers"][:limit]
        result["peer_count"] = len(result["peers"])
    evidence_missing = [
        {
            "id": f"peer_evidence.{item.get('ticker') or item.get('instrument_id')}",
            "ticker": item.get("ticker"),
            "reason": "required_peer_evidence_missing",
            "fields": item["fields"],
            "required": item.get("ticker") == ticker,
        }
        for item in result["missing"]
    ]
    missing = [*provider_missing, *identity_missing, *evidence_missing]
    status = "ok" if result["comparison_state"] == "complete" and not missing else "partial"
    return envelope(
        "ticker.peers",
        request=_clean_request({**request, "ticker": ticker}),
        as_of=_as_of(clock),
        status=status,
        data={
            "ticker": ticker,
            "sector": classification.data["sector"],
            "industry": classification.data["industry"],
            "industry_id": classification.data["industry_id"],
            **result,
        },
        missing=missing,
        sources=sources,
        doctrine_ids=["scope.data_integrity"],
        next_capabilities=["ticker.risk"],
    )


def _candidate_row(record: SecurityRecord) -> dict[str, Any]:
    exchange = record.exchange.upper()
    exchange = {
        "NYSE AMERICAN": "NYSEAMERICAN",
        "NYSE NATIONAL": "NYSE",
        "CBOE BZX": "CBOE",
    }.get(exchange, exchange)
    return {
        "instrument_id": record.instrument_id,
        "ticker": record.symbol,
        "exchange": exchange,
        "listing_country": "US",
        "instrument_type": record.instrument_type,
        "is_adr": record.is_adr,
        "origins": ["nasdaq_security_master"],
        "recommendation_state": "not_recommended",
    }


def _market_candidates(request: Mapping[str, Any], runtime: Runtime) -> dict[str, Any]:
    clock = _clock(request.get("as_of"))
    limit = request.get("limit", 50)
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise RequestError("limit must be a positive integer", "limit")
    try:
        historical = request.get("as_of") is not None and clock.date != resolve_as_of().date
        snapshot = _cached_provider(
            runtime,
            request,
            clock,
            capability="market.candidates",
            provider="nasdaq",
            operation="historical_security_master" if historical else "current_security_master",
            params={"historical": historical},
            fetch=lambda: runtime.security_master(request.get("as_of")),
            ttl_seconds=None if historical else 900,
        )
    except ProviderUnavailable as error:
        return envelope(
            "market.candidates",
            request=_clean_request(request),
            as_of=_as_of(clock),
            status="unavailable",
            data={"candidates": [], "exclusions": {"total_count": 0, "reason_counts": {}, "samples": [], "sample_limit": 0}, "page": {}},
            missing=[_missing_provider(error)],
        )
    try:
        result = build_market_candidates(
            (_candidate_row(record) for record in snapshot.data),
            limit=limit,
            cursor=request.get("cursor"),
        )
    except ValueError as error:
        raise RequestError(str(error), "cursor") from error
    return envelope(
        "market.candidates",
        request=_clean_request(request),
        as_of=_as_of(clock),
        data=result,
        sources=[_source(snapshot.meta)],
        next_capabilities=["ticker.qualify"] if result["candidates"] else [],
    )


def _qqq_rows(frame: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, row in frame.iterrows():
        timestamp = index.date().isoformat() if hasattr(index, "date") else str(index)
        rows.append(
            {
                "date": timestamp,
                "open": row.get("Open"),
                "high": row.get("High"),
                "low": row.get("Low"),
                "close": row.get("Close"),
                "volume": row.get("Volume"),
                "completed": True,
            }
        )
    return rows


def _ranked_groups(rows: list[dict[str, Any]], group_key: str, as_of: str) -> list[dict[str, Any]]:
    return [
        {
            **row,
            "name": row[group_key],
            "rank": rank,
            "rating": row.get("avg_rs"),
            "as_of": as_of,
        }
        for rank, row in enumerate(rows, start=1)
    ]


def _ranked_leaders(rows: list[dict[str, Any]], as_of: str) -> list[dict[str, Any]]:
    return [
        {
            **row,
            "rank": rank,
            "rating": row.get("rs_rating"),
            "as_of": as_of,
        }
        for rank, row in enumerate(rows, start=1)
    ]


def _market_snapshot(request: Mapping[str, Any], runtime: Runtime) -> dict[str, Any]:
    clock = _clock(request.get("as_of"))
    as_of = clock.date.isoformat()
    leader_limit = request.get("leader_limit", 20)
    if not isinstance(leader_limit, int) or isinstance(leader_limit, bool) or not 1 <= leader_limit <= 100:
        raise RequestError("leader_limit must be an integer from 1 to 100", "leader_limit")
    trade_traction = request.get("trade_traction")
    if trade_traction is not None and trade_traction not in {"supports", "contradicts", "mixed", "needs_input"}:
        raise RequestError("trade_traction must be supports, contradicts, mixed, or needs_input", "trade_traction")

    sources: list[dict[str, Any]] = []
    succeeded: list[ProviderSnapshot[Any]] = []
    provider_missing: list[dict[str, Any]] = []

    def collect(fetch: Callable[[], ProviderSnapshot[Any]]) -> ProviderSnapshot[Any] | None:
        try:
            snapshot = fetch()
        except ProviderUnavailable as error:
            provider_missing.append(_missing_provider(error, required=False))
            return None
        sources.append(_source(snapshot.meta))
        stale_price = _stale_price_gap(snapshot.meta)
        if stale_price is not None:
            provider_missing.append(stale_price)
            return None
        succeeded.append(snapshot)
        return snapshot

    qqq = collect(
        lambda: _cached_provider(
            runtime,
            request,
            clock,
            capability="market.snapshot",
            provider="yfinance",
            operation="daily_bars",
            params={"ticker": "QQQ"},
            fetch=lambda: runtime.price_history("QQQ", as_of),
        )
    )
    finviz = collect(
        lambda: _cached_provider(
            runtime,
            request,
            clock,
            capability="market.snapshot",
            provider="finviz",
            operation="raw_snapshot",
            params={},
            fetch=lambda: runtime.finviz_breadth(as_of),
            ttl_seconds=900,
        )
    )
    sectors = collect(
        lambda: _cached_provider(
            runtime,
            request,
            clock,
            capability="market.snapshot",
            provider="ibd-rs-rating",
            operation="sector_ranking",
            params={},
            fetch=lambda: runtime.sector_ranking(as_of),
        )
    )
    industries = collect(
        lambda: _cached_provider(
            runtime,
            request,
            clock,
            capability="market.snapshot",
            provider="ibd-rs-rating",
            operation="industry_ranking",
            params={},
            fetch=lambda: runtime.industry_ranking(as_of),
        )
    )
    leaders = collect(
        lambda: _cached_provider(
            runtime,
            request,
            clock,
            capability="market.snapshot",
            provider="ibd-rs-rating",
            operation="top",
            params={"limit": leader_limit},
            fetch=lambda: runtime.market_leaders(as_of, leader_limit),
        )
    )

    sector_rows = _ranked_groups(sectors.data, "sector", as_of) if sectors is not None else None
    industry_rows = _ranked_groups(industries.data, "industry", as_of) if industries is not None else None
    leader_rows = _ranked_leaders(leaders.data, as_of) if leaders is not None else None
    evidence = build_market_evidence(
        qqq_daily_ohlcv=_qqq_rows(qqq.data) if qqq is not None else None,
        finviz_html=finviz.data if finviz is not None else None,
        sector_rows=sector_rows,
        industry_rows=industry_rows,
        leader_rows=leader_rows,
        trade_traction={"state": trade_traction} if trade_traction is not None else None,
    )
    result = evaluate_market_snapshot(evidence)
    section_missing = [
        {
            "id": f"breadth.{name}",
            "reason": section.get("reason", "section_unavailable"),
            "required": False,
        }
        for name, section in evidence["breadth"].get("sections", {}).items()
        if section.get("state") == "unavailable"
    ]
    missing = [*provider_missing, *result["missing"], *section_missing]
    if trade_traction == "needs_input":
        missing.append({"id": "trade_traction", "reason": "user_feedback_required", "required": True})
    if not succeeded:
        # A snapshot that was fetched but discarded is provenance, not evidence.
        status = "unavailable"
    elif trade_traction in {None, "needs_input"}:
        status = "needs_input"
    elif missing:
        status = "partial"
    else:
        status = "ok"
    return envelope(
        "market.snapshot",
        request=_clean_request(request),
        as_of=_as_of(clock),
        status=status,
        data={**result, "leaders": leader_rows or []},
        signals=result["signal_vector"],
        missing=missing,
        sources=sources,
        doctrine_ids=["scope.data_integrity"],
        next_capabilities=["market.candidates", "ticker.qualify"] if succeeded else [],
    )


def _positive(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if value > 0 and math.isfinite(value) else None


def _combine_audits(audits: list[dict[str, Any]]) -> dict[str, Any]:
    """One path verdict over several levels, each audited from its own effective date.

    A breach anywhere is irreversible, so it outranks every clear audit; a level
    whose window could not be covered leaves the whole path unresolved.
    """

    breaches = [audit for audit in audits if audit["state"] == "breached"]
    if breaches:
        governing = min(breaches, key=lambda audit: audit["breach_date"])
    else:
        unresolved = [audit for audit in audits if audit["state"] != "clear"]
        governing = unresolved[0] if unresolved else max(audits, key=lambda audit: audit["level"])
    shared = {key: value for key, value in governing.items() if key not in {"level", "role", "effective_from"}}
    return {
        **shared,
        "checked_level": governing["level"],
        "from": governing["effective_from"],
        "audits": audits,
    }


def _completed_stop_path(frame: Any, *, effective_date: date, as_of: date, protective_level: float) -> tuple[dict[str, Any], float | None]:
    if not isinstance(frame, pd.DataFrame) or frame.empty or not {"Low", "Close"}.issubset(frame.columns):
        return {"state": "unavailable", "reason": "completed_ohlc_path_unavailable"}, None
    timestamps = pd.to_datetime(frame.index, errors="coerce")
    if timestamps.isna().any():
        return {"state": "unavailable", "reason": "invalid_completed_bar_date"}, None
    if timestamps.tz is not None:
        timestamps = timestamps.tz_convert("America/New_York").tz_localize(None)
    ordered = frame.copy()
    ordered.index = timestamps
    ordered = ordered.sort_index()
    dated_rows = [(timestamp.date(), row) for timestamp, row in ordered.iterrows() if timestamp.date() <= as_of]
    if not dated_rows:
        return {"state": "unavailable", "reason": "no_completed_bars_through_as_of"}, None

    latest_date, latest_row = dated_rows[-1]
    try:
        current_price = float(latest_row["Close"])
    except (TypeError, ValueError):
        current_price = None
    if current_price is not None and (not math.isfinite(current_price) or current_price <= 0):
        current_price = None

    first_available = dated_rows[0][0]
    if first_available > effective_date:
        return {
            "state": "unavailable",
            "reason": "history_starts_after_stop_effective_date",
            "requested_from": effective_date.isoformat(),
            "first_available": first_available.isoformat(),
            "through": latest_date.isoformat(),
        }, current_price
    path_rows = [(bar_date, row) for bar_date, row in dated_rows if bar_date >= effective_date]
    if not path_rows:
        return {"state": "unavailable", "reason": "no_completed_bars_in_stop_window"}, current_price
    for bar_date, row in path_rows:
        try:
            low = float(row["Low"])
        except (TypeError, ValueError):
            return {"state": "unavailable", "reason": "invalid_low_in_stop_window", "date": bar_date.isoformat()}, current_price
        if not math.isfinite(low) or low <= 0:
            return {"state": "unavailable", "reason": "invalid_low_in_stop_window", "date": bar_date.isoformat()}, current_price
        if low <= protective_level:
            return {
                "state": "breached",
                "basis": "completed_daily_low",
                "from": effective_date.isoformat(),
                "through": latest_date.isoformat(),
                "bars_checked": len(path_rows),
                "breach_date": bar_date.isoformat(),
                "breach_low": low,
            }, current_price
    if latest_date < as_of:
        # No breach in the bars that exist. A later missing bar cannot prove HOLD,
        # but it could never have erased a breach found above either.
        return {
            "state": "unavailable",
            "reason": "history_ends_before_as_of",
            "requested_from": effective_date.isoformat(),
            "last_available": latest_date.isoformat(),
            "requested_through": as_of.isoformat(),
            "bars_checked": len(path_rows),
        }, current_price
    return {
        "state": "clear",
        "basis": "completed_daily_low",
        "from": effective_date.isoformat(),
        "through": latest_date.isoformat(),
        "bars_checked": len(path_rows),
    }, current_price


def _risk(request: Mapping[str, Any], runtime: Runtime) -> dict[str, Any]:
    ticker = _ticker(request.get("ticker"))
    clock = _clock(request.get("as_of"))
    mode = request.get("mode", "prospective")
    if mode not in {"prospective", "active"}:
        raise RequestError("mode must be prospective or active", "mode")
    evidence = {key: value for key, value in request.items() if key not in {"ticker", "as_of", "format", "no_cache"}}
    evidence["mode"] = mode
    # The reducer measures every audit window against the decision date, so it
    # cannot be the one input the operation keeps to itself.
    evidence["as_of"] = clock.date.isoformat()
    sources: list[dict[str, Any]] = []
    provider_missing: list[dict[str, Any]] = []
    invalidation = evidence.get("invalidation")
    # The audit needs the date the position started and a plan to clear; what it
    # was bought at decides 3R protection, not whether a level was breached. Both
    # predicates come from the reducer so routing cannot drift from the verdict.
    has_position_anchors = evidence.get("entry_date") is not None and declares_exit_plan(evidence)
    raw_stop_price = evidence.get("stop_price")
    stop_price = _positive(raw_stop_price)
    raw_invalidation_price = invalidation.get("price") if isinstance(invalidation, Mapping) else None
    invalidation_price = _positive(raw_invalidation_price)
    for raw, resolved, field in ((raw_stop_price, stop_price, "stop_price"), (raw_invalidation_price, invalidation_price, "invalidation_price")):
        if raw is not None and resolved is None:
            raise RequestError(f"{field} must be a finite positive number", field)
    protective_level = max([level for level in (stop_price, invalidation_price) if level is not None], default=None)
    stop_effective_date: date | None = None
    entry_date: date | None = None
    if mode == "active" and evidence.get("entry_date") is not None:
        raw_effective_date = evidence.get("stop_effective_date") or evidence.get("entry_date")
        try:
            stop_effective_date = date.fromisoformat(str(raw_effective_date))
            entry_date = date.fromisoformat(str(evidence["entry_date"]))
        except ValueError as error:
            field = "stop_effective_date" if evidence.get("stop_effective_date") is not None else "entry_date"
            raise RequestError(f"{field} must be an ISO date", field) from error
        # Chronology is checked before any evidence is fetched: a position that does
        # not exist on the decision date cannot be sold, held, or audited.
        if entry_date > clock.date:
            raise RequestError("entry_date cannot be after as_of", "entry_date")
        if stop_effective_date < entry_date:
            raise RequestError("stop_effective_date cannot precede entry_date", "stop_effective_date")
        if stop_effective_date > clock.date:
            raise RequestError("stop_effective_date cannot be after as_of", "stop_effective_date")
        evidence["stop_effective_date"] = stop_effective_date.isoformat()

    # A stop raised later is only in force from its own date, while the structural
    # invalidation has stood since entry. Auditing both against one date would let
    # the later start hide a breach the earlier level already suffered.
    protective_plan: list[tuple[str, float, date]] = []
    if stop_price is not None and stop_effective_date is not None:
        protective_plan.append(("stop", stop_price, stop_effective_date))
    if invalidation_price is not None and entry_date is not None:
        protective_plan.append(("invalidation", invalidation_price, entry_date))

    explicit_current = evidence.get("current_price")
    explicit_completed_breach = protective_level is not None and isinstance(explicit_current, (int, float)) and not isinstance(explicit_current, bool) and float(explicit_current) <= protective_level
    if mode == "active" and explicit_completed_breach and stop_effective_date is not None:
        evidence["completed_price_path"] = {
            "state": "breached",
            "basis": "explicit_completed_price",
            "from": stop_effective_date.isoformat(),
            "through": clock.date.isoformat(),
            "checked_level": protective_level,
            "breach_date": clock.date.isoformat(),
            "breach_price": float(explicit_current),
            "audits": [
                {
                    "role": role,
                    "level": level,
                    "effective_from": effective.isoformat(),
                    "through": clock.date.isoformat(),
                    "state": "breached" if float(explicit_current) <= level else "clear",
                }
                for role, level, effective in protective_plan
            ],
        }
    # A breach that already settles the verdict needs no price history, and a
    # provider failure fetched for nothing would downgrade a terminal SELL to partial.
    if mode == "active" and has_position_anchors and not settled_breach(evidence):
        try:
            prices = _cached_provider(
                runtime,
                request,
                clock,
                capability="ticker.risk",
                provider="yfinance",
                operation="daily_bars",
                params={"ticker": ticker},
                fetch=lambda: runtime.price_history(ticker, clock.date.isoformat()),
            )
        except ProviderUnavailable as error:
            provider_missing.append(_missing_provider(error))
        else:
            sources.append(_source(prices.meta))
            stale_price = _stale_price_gap(prices.meta)
            if stale_price is not None:
                provider_missing.append(stale_price)
            current_price = None
            if protective_plan:
                # Runs even when the history stops early: a completed breach is
                # irreversible, and a later missing bar cannot undo one.
                audits: list[dict[str, Any]] = []
                path_price = None
                for role, level, effective in protective_plan:
                    audit, audit_price = _completed_stop_path(
                        prices.data,
                        effective_date=effective,
                        as_of=clock.date,
                        protective_level=level,
                    )
                    audits.append({**audit, "role": role, "level": level, "effective_from": effective.isoformat()})
                    path_price = audit_price if audit_price is not None else path_price
                price_path = _combine_audits(audits)
                evidence["completed_price_path"] = price_path
                if stale_price is None:
                    current_price = path_price
                if price_path.get("state") == "unavailable":
                    provider_missing.append(
                        {
                            "id": "completed_price_path",
                            "provider": prices.meta.provider,
                            "reason": price_path.get("reason", "completed_price_path_unavailable"),
                            "required": True,
                            "attempts": 1,
                            "retryable": False,
                        }
                    )
            elif stale_price is None:
                # A price from an earlier session can only make a position look
                # safer than the evidence supports, so it is withheld entirely.
                try:
                    current_price = float(prices.data["Close"].iloc[-1])
                except (AttributeError, KeyError, IndexError, TypeError, ValueError):
                    current_price = None
            if current_price is not None:
                evidence["current_price"] = current_price
    result = reduce_risk(evidence)
    status = "partial" if provider_missing else "needs_input" if result["verdict"] == "INCOMPLETE" else "ok"
    provider_missing_ids = {item["id"] for item in provider_missing}
    missing = [*provider_missing, *({"id": item, "reason": "evidence_required", "required": True} for item in result["missing"] if item not in provider_missing_ids)]
    return envelope(
        "ticker.risk",
        request=_clean_request({**request, "ticker": ticker}),
        as_of=_as_of(clock),
        status=status,
        data={"ticker": ticker, **result, "current_price": evidence.get("current_price")},
        signals=[
            {"id": item, "state": "fail"} for item in result["failed"]
        ] + [{"id": item, "state": "not_triggered"} for item in result["waiting"]],
        missing=missing,
        sources=sources,
        doctrine_ids=["risk.initial_stop_and_reward", "risk.hard_stop_and_no_average_down", "risk.profit_protection_at_3r"],
    )


def _chart(request: Mapping[str, Any], runtime: Runtime) -> dict[str, Any]:
    ticker = _ticker(request.get("ticker"))
    clock = _clock(request.get("as_of"))
    try:
        # Imported here so a machine without the plotting stack still runs discovery,
        # help, and every deterministic capability.
        from .chart import render_chart_artifacts
    except ImportError as error:
        return envelope(
            "ticker.chart",
            request=_clean_request({**request, "ticker": ticker}),
            as_of=_as_of(clock),
            status="unavailable",
            data={"ticker": ticker},
            missing=[
                {
                    "id": "chart_renderer",
                    "reason": f"plotting_stack_unavailable: {error}",
                    "required": True,
                    "retryable": False,
                }
            ],
        )
    try:
        prices = _cached_provider(
            runtime,
            request,
            clock,
            capability="ticker.chart",
            provider="yfinance",
            operation="daily_bars",
            params={"ticker": ticker},
            fetch=lambda: runtime.price_history(ticker, clock.date.isoformat()),
        )
    except ProviderUnavailable as error:
        return envelope(
            "ticker.chart",
            request=_clean_request({**request, "ticker": ticker}),
            as_of=_as_of(clock),
            status="unavailable",
            data={"ticker": ticker},
            missing=[_missing_provider(error)],
        )
    stale_price = _stale_price_gap(prices.meta)
    if stale_price is not None:
        return envelope(
            "ticker.chart",
            request=_clean_request({**request, "ticker": ticker}),
            as_of=_as_of(clock),
            status="partial",
            data={"ticker": ticker},
            missing=[stale_price],
            sources=[_source(prices.meta)],
        )
    output_dir = request.get("output_dir")
    if output_dir is not None and (not isinstance(output_dir, str) or not output_dir.strip()):
        raise RequestError("output_dir must be a non-empty path", "output_dir")
    destination = Path(output_dir) if output_dir else Path(__file__).resolve().parents[2] / ".artifacts" / "charts"
    result = render_chart_artifacts(
        prices.data,
        ticker=ticker,
        as_of=clock.date.isoformat(),
        output_dir=destination,
    )
    side_effects = [
        {
            "type": "chart_artifact",
            "path": artifact["path"],
            "as_of": result["as_of"],
            "input_sha256": result["input_sha256"],
        }
        for artifact in result["artifacts"]
    ]
    side_effects.append(
        {
            "type": "artifact_manifest",
            "path": result["manifest_path"],
            "as_of": result["as_of"],
            "input_sha256": result["input_sha256"],
        }
    )
    return envelope(
        "ticker.chart",
        request=_clean_request({**request, "ticker": ticker}),
        as_of=_as_of(clock),
        data=result,
        sources=[_source(prices.meta)],
        next_capabilities=["ticker.qualify", "ticker.setup"],
        side_effects=side_effects,
    )


def _watchlist(request: Mapping[str, Any], operation: str, runtime: Runtime) -> dict[str, Any]:
    clock = _clock(request.get("as_of"))
    ledger = runtime.ledger_factory()
    if operation == "watchlist.show":
        return envelope(operation, request=_clean_request(request), as_of=_as_of(clock), data={"records": ledger.show()})
    if operation == "watchlist.history":
        ticker = _ticker(request.get("ticker"))
        return envelope(operation, request=_clean_request({**request, "ticker": ticker}), as_of=_as_of(clock), data={"ticker": ticker, "events": ledger.history(ticker)})
    if operation == "watchlist.record":
        ticker = _ticker(request.get("ticker"))
        required = ("instrument_id", "output_hash", "verdict")
        for field_name in required:
            if not isinstance(request.get(field_name), str) or not str(request[field_name]).strip():
                raise RequestError(f"{field_name} is required", field_name)
        output_hash = str(request["output_hash"]).lower()
        if not re.fullmatch(r"[0-9a-f]{64}", output_hash):
            raise RequestError("output_hash must be a SHA-256 hex digest", "output_hash")
        doctrine_ids = request.get("doctrine_ids", [])
        if not isinstance(doctrine_ids, list) or not all(isinstance(item, str) for item in doctrine_ids):
            raise RequestError("doctrine_ids must be a list of claim IDs", "doctrine_ids")
        record = ledger.record(
            instrument_id=str(request["instrument_id"]),
            symbol=ticker,
            as_of=clock.date.isoformat(),
            output_hash=output_hash,
            verdict=str(request["verdict"]),
            condition=request.get("condition"),
            invalidation=request.get("invalidation"),
            doctrine_ids=doctrine_ids,
            evidence_quality=request.get("evidence_quality"),
            note=request.get("note"),
        )
        return envelope(
            operation,
            request=_clean_request({**request, "ticker": ticker}),
            as_of=_as_of(clock),
            data={"record": record},
            doctrine_ids=doctrine_ids,
            side_effects=[{"type": "sqlite_write", "path": str(ledger.path)}],
        )
    if operation == "watchlist.annotate":
        ticker = _ticker(request.get("ticker"))
        note = request.get("note")
        if not isinstance(note, str) or not note.strip():
            raise RequestError("note is required", "note")
        try:
            record = ledger.annotate(ticker, note)
        except KeyError as error:
            raise RequestError(f"no recorded research for {ticker}", "ticker") from error
        return envelope(
            operation,
            request=_clean_request({**request, "ticker": ticker, "note": note}),
            as_of=_as_of(clock),
            data={"record": record},
            side_effects=[{"type": "sqlite_write", "path": str(ledger.path)}],
        )
    if operation == "watchlist.export":
        output = request.get("output")
        if not isinstance(output, str) or not output.strip():
            raise RequestError("output is required", "output")
        result = ledger.export(Path(output))
        return envelope(
            operation,
            request=_clean_request(request),
            as_of=_as_of(clock),
            data=result,
            side_effects=[{"type": "file_write", "path": result["path"]}],
        )
    raise RequestError(f"unknown operation: {operation}", "operation")


def execute(operation: str, request: Mapping[str, Any], *, runtime: Runtime | None = None) -> dict[str, Any]:
    """Execute one composable capability without printing or mutating implicit state."""

    if not isinstance(request, Mapping):
        raise RequestError("request must be an object", "request")
    runtime = runtime if runtime is not None else Runtime(cache=ProviderCache())
    if operation == "clock":
        return _clock_operation(request)
    if operation == "health":
        return _health(request, runtime)
    if operation == "doctrine.show":
        return _doctrine_show(request)
    if operation == "ticker.qualify":
        return _qualify(request, runtime)
    if operation == "ticker.setup":
        return _setup(request, runtime)
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


__all__ = ["Runtime", "execute"]
