"""Provider boundaries and replaceable runtime dependencies."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from hashlib import sha256
from typing import Any, Callable, Mapping

from .cache import ProviderCache
from .clock import resolve_as_of
from .ledger import Ledger
from .providers import ProviderSnapshot, ProviderUnavailable, SnapshotMeta, fetch_with_one_retry
from .providers.finviz import raw_snapshot as finviz_raw_snapshot
from .providers.nasdaq import SecurityRecord, current_security_master, historical_security_master
from .providers.rs import industry_ranking_snapshot, industry_top_snapshot, rating_snapshot, sector_ranking_snapshot, top_snapshot
from .providers.sec import fetch_company_facts, fetch_company_submissions, fetch_company_tickers, normalize_filed_facts
from .providers.yfinance import completed_daily_bars, current_classification_snapshot, next_earnings_snapshot


PriceHistory = Callable[[str, str | None], ProviderSnapshot[Any]]
RatingSnapshot = Callable[[str, str | None], ProviderSnapshot[dict[str, Any]]]
SecurityMaster = Callable[[str | None], ProviderSnapshot[list[SecurityRecord]]]
LedgerFactory = Callable[[], Ledger]
FundamentalsEvidence = Callable[[str, str, str | None], ProviderSnapshot[dict[str, Any]]]
RankedRows = Callable[[str], ProviderSnapshot[list[dict[str, Any]]]]
MarketLeaders = Callable[[str, int], ProviderSnapshot[list[dict[str, Any]]]]
FinvizBreadth = Callable[[str], ProviderSnapshot[str]]
CurrentClassification = Callable[[str], ProviderSnapshot[dict[str, str]]]
EarningsCalendar = Callable[[str], ProviderSnapshot[dict[str, Any]]]
CompanyTickers = Callable[[], ProviderSnapshot[dict[str, dict[str, str]]]]
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


def _default_company_tickers() -> ProviderSnapshot[dict[str, dict[str, str]]]:
    """The SEC's own current symbol-to-registrant list, whole.

    The same fetch `_default_fundamentals_evidence` makes on the way to the filings when no
    `--cik` was given. It was only ever reachable as a step inside something else, which is
    how a value the interface requires came to have nowhere to come from.
    """

    user_agent = os.environ.get("MINERVINI_SEC_USER_AGENT", "")
    if not user_agent:
        raise ProviderUnavailable("sec", "identifiable_user_agent_required", operation="company_tickers")
    try:
        import requests
    except Exception as error:
        raise ProviderUnavailable("sec", "requests_package_unavailable", operation="company_tickers") from error

    return fetch_company_tickers(request_get=requests.get, user_agent=user_agent)


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


def _default_earnings_calendar(ticker: str) -> ProviderSnapshot[dict[str, Any]]:
    return next_earnings_snapshot(ticker)


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
    earnings_calendar: EarningsCalendar = field(default_factory=lambda: _default_earnings_calendar)
    company_tickers: CompanyTickers = field(default_factory=lambda: _default_company_tickers)
    industry_top: IndustryTop = field(default_factory=lambda: _default_industry_top)
    ledger_factory: LedgerFactory = field(default_factory=lambda: Ledger)
    reachability_probes: Mapping[str, Callable[[], None]] = field(default_factory=_default_reachability_probes)
    cache: ProviderCache | None = None
