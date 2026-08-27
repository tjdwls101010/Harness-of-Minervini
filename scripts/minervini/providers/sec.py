from __future__ import annotations

from datetime import date, datetime, timezone
from hashlib import sha256
import json
import re
from typing import Any, Callable, Iterable, Mapping

from . import ProviderSnapshot, ProviderUnavailable, RequestThrottle, SnapshotMeta, fetch_with_one_retry


SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_PROVIDER = "sec"
MIN_REQUEST_INTERVAL_SECONDS = 0.15
_THROTTLE = RequestThrottle(MIN_REQUEST_INTERVAL_SECONDS)
_FORM_TYPES = {"10-Q", "10-K", "20-F"}
_QUARTERLY_METRICS = {
    "eps": ("EarningsPerShareDiluted", "BasicAndDilutedEarningsLossPerShare"),
    "revenue": ("RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet", "Revenues", "Revenue"),
    "net_income": ("NetIncomeLoss", "ProfitLoss"),
    "diluted_shares": ("WeightedAverageNumberOfDilutedSharesOutstanding",),
}
_ANNUAL_METRICS = {"eps": _QUARTERLY_METRICS["eps"], "revenue": _QUARTERLY_METRICS["revenue"]}
# Balances rather than flows. Inventory and receivables are reported as of a date, so a
# filing carries no `start` for them and the period they belong to is the one whose books
# close on that date -- never the fiscal year of the report, which for a comparative column
# is this year while the balance is last year's.
_ANNUAL_INSTANT_METRICS = {
    "inventory": ("InventoryNet", "InventoryFinishedGoodsNetOfReserves", "InventoryGross"),
    "accounts_receivable": ("AccountsReceivableNetCurrent", "ReceivablesNetCurrent", "AccountsReceivableNet"),
}


def _filed_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def select_filed_as_of(records: Iterable[Mapping[str, Any]], as_of: str | date) -> dict[str, Any] | None:
    """Return the latest fact filed on or before the audit boundary, never a future filing."""

    boundary = _filed_date(as_of)
    eligible: list[tuple[date, Mapping[str, Any]]] = []
    for record in records:
        filed_at = record.get("filed_at")
        if filed_at is None:
            continue
        filed = _filed_date(filed_at)
        if filed <= boundary:
            eligible.append((filed, record))
    if not eligible:
        return None
    return dict(max(eligible, key=lambda item: item[0])[1])


def fetch_company_tickers(
    *,
    request_get: Callable[..., Any],
    user_agent: str,
    retrieved_at: datetime | None = None,
) -> ProviderSnapshot[dict[str, dict[str, str]]]:
    """Fetch and validate SEC's current ticker-to-CIK lookup."""

    payload = _request_json("company_tickers", SEC_TICKERS_URL, request_get, user_agent)
    observed_at = retrieved_at or datetime.now(timezone.utc)
    return ProviderSnapshot(
        data=validate_company_tickers(payload),
        meta=SnapshotMeta(
            provider=SEC_PROVIDER,
            retrieved_at=observed_at,
            as_of=observed_at.date(),
            coverage={"kind": "current_company_ticker_lookup", "historical": False},
            content_sha256=_content_hash(payload),
        ),
    )


def fetch_company_facts(
    cik: str | int,
    *,
    request_get: Callable[..., Any],
    user_agent: str,
    retrieved_at: datetime | None = None,
) -> ProviderSnapshot[dict[str, Any]]:
    """Fetch and validate the SEC filed XBRL facts for one registrant."""

    normalized_cik = _normalize_cik(cik)
    payload = _request_json("companyfacts", SEC_COMPANYFACTS_URL.format(cik=normalized_cik), request_get, user_agent)
    observed_at = retrieved_at or datetime.now(timezone.utc)
    return ProviderSnapshot(
        data=validate_company_facts(payload, cik=normalized_cik),
        meta=SnapshotMeta(
            provider=SEC_PROVIDER,
            retrieved_at=observed_at,
            as_of=None,
            coverage={"kind": "filed_companyfacts", "historical": True},
            content_sha256=_content_hash(payload),
        ),
    )


def fetch_company_submissions(
    cik: str | int,
    *,
    request_get: Callable[..., Any],
    user_agent: str,
    retrieved_at: datetime | None = None,
) -> ProviderSnapshot[dict[str, Any]]:
    """Fetch and validate the SEC submission index used to date filed facts."""

    normalized_cik = _normalize_cik(cik)
    payload = _request_json("submissions", SEC_SUBMISSIONS_URL.format(cik=normalized_cik), request_get, user_agent)
    observed_at = retrieved_at or datetime.now(timezone.utc)
    return ProviderSnapshot(
        data=validate_company_submissions(payload, cik=normalized_cik),
        meta=SnapshotMeta(
            provider=SEC_PROVIDER,
            retrieved_at=observed_at,
            as_of=None,
            coverage={"kind": "filed_submission_index_recent_only", "historical": False, "older_indexes": "not_fetched"},
            content_sha256=_content_hash(payload),
        ),
    )


def validate_company_tickers(payload: Any) -> dict[str, dict[str, str]]:
    """Return a canonical ticker lookup or reject an unusable SEC payload."""

    if not isinstance(payload, Mapping):
        raise _invalid("invalid_company_tickers")
    tickers: dict[str, dict[str, str]] = {}
    for record in payload.values():
        if not isinstance(record, Mapping) or not isinstance(record.get("ticker"), str) or not isinstance(record.get("title"), str):
            raise _invalid("invalid_company_tickers")
        try:
            cik = _normalize_cik(record.get("cik_str"))
        except ValueError as error:
            raise _invalid("invalid_company_tickers") from error
        ticker = record["ticker"].strip().upper()
        if not ticker or ticker in tickers:
            raise _invalid("invalid_company_tickers")
        tickers[ticker] = {"cik": cik, "title": record["title"].strip()}
    if not tickers:
        raise _invalid("invalid_company_tickers")
    return tickers


def validate_company_facts(payload: Any, *, cik: str | int) -> dict[str, Any]:
    """Validate the minimal companyfacts structure used by the normalizer."""

    normalized_cik = _normalize_cik(cik)
    if not isinstance(payload, Mapping) or not isinstance(payload.get("facts"), Mapping):
        raise _invalid("invalid_companyfacts")
    try:
        payload_cik = _normalize_cik(payload.get("cik"))
    except ValueError as error:
        raise _invalid("invalid_companyfacts") from error
    if payload_cik != normalized_cik:
        raise _invalid("companyfacts_cik_mismatch")
    if not any(isinstance(payload["facts"].get(taxonomy), Mapping) for taxonomy in ("us-gaap", "ifrs-full")):
        raise _invalid("unsupported_companyfacts_taxonomy")
    return {**payload, "cik": payload_cik}


def validate_company_submissions(payload: Any, *, cik: str | int) -> dict[str, Any]:
    """Validate the submission rows needed to authenticate filing dates."""

    normalized_cik = _normalize_cik(cik)
    if not isinstance(payload, Mapping) or not isinstance(payload.get("filings"), Mapping):
        raise _invalid("invalid_submissions")
    try:
        payload_cik = _normalize_cik(payload.get("cik"))
    except ValueError as error:
        raise _invalid("invalid_submissions") from error
    recent = payload["filings"].get("recent")
    required = ("accessionNumber", "filingDate", "reportDate", "form")
    if payload_cik != normalized_cik:
        raise _invalid("submissions_cik_mismatch")
    if not isinstance(recent, Mapping) or any(not isinstance(recent.get(field), list) for field in required):
        raise _invalid("invalid_submissions")
    if len({len(recent[field]) for field in required}) != 1:
        raise _invalid("invalid_submissions")
    for filed_at in recent["filingDate"]:
        try:
            _filed_date(filed_at)
        except (TypeError, ValueError) as error:
            raise _invalid("invalid_submissions") from error
    return {**payload, "cik": payload_cik}


def normalize_filed_facts(
    company_facts: Mapping[str, Any],
    submissions: Mapping[str, Any],
    *,
    as_of: str | date,
) -> dict[str, Any]:
    """Normalize SEC facts filed by ``as_of`` for ``evaluate_fundamentals``.

    The submission index authenticates an accession's filing date. Facts with a
    later filing date or a mismatch between the two SEC documents are excluded.
    This provider intentionally does not infer narrative safety evidence.
    """

    boundary = _filed_date(as_of)
    try:
        facts_cik = _normalize_cik(company_facts.get("cik"))
        submissions_cik = _normalize_cik(submissions.get("cik"))
    except (AttributeError, ValueError) as error:
        raise ValueError("SEC companyfacts and submissions must identify a valid matching CIK.") from error
    if facts_cik != submissions_cik:
        raise ValueError("SEC companyfacts and submissions must identify the same CIK.")
    validate_company_facts(company_facts, cik=facts_cik)
    validate_company_submissions(submissions, cik=submissions_cik)

    submission_rows = _submission_rows(submissions)
    taxonomy, accounting_basis = _accounting_taxonomy(company_facts)
    filings: dict[str, dict[str, Any]] = {}
    for kind, metrics in (("quarterly", _QUARTERLY_METRICS), ("annual", _ANNUAL_METRICS), ("annual_instant", _ANNUAL_INSTANT_METRICS)):
        for metric, concepts in metrics.items():
            for record in _metric_records(taxonomy, concepts, kind):
                accession = record["accn"]
                submission = submission_rows.get(accession)
                if submission is None or not _is_supported_form(submission["form"]):
                    continue
                if record.get("form") != submission["form"]:
                    continue
                filed_at = _filed_date(submission["filed_at"])
                if filed_at > boundary:
                    continue
                if record.get("filed") != submission["filed_at"]:
                    raise ValueError(f"SEC fact filing date does not match submissions for {accession}.")
                filing = filings.setdefault(
                    accession,
                    {
                        "filed_at": submission["filed_at"],
                        "accounting_basis": accounting_basis,
                        "quarterly": {},
                        "annual": {},
                    },
                )
                bucket = "annual" if kind == "annual_instant" else kind
                fact = filing[bucket].setdefault(
                    record["period"],
                    {"period": record["period"], "end": record["end"]},
                )
                fact[metric] = record["val"]

    normalized_filings = []
    for filing in sorted(filings.values(), key=lambda item: item["filed_at"]):
        normalized_filings.append(
            {
                "filed_at": filing["filed_at"],
                "accounting_basis": filing["accounting_basis"],
                "quarterly": list(filing["quarterly"].values()),
                "annual": list(filing["annual"].values()),
            }
        )
    return {"source": "sec_filed_facts", "cik": facts_cik, "filings": normalized_filings}


def _request_json(operation: str, url: str, request_get: Callable[..., Any], user_agent: str) -> Mapping[str, Any]:
    _validate_user_agent(user_agent)

    def fetch() -> Mapping[str, Any]:
        _THROTTLE.wait()
        response = request_get(url, headers={"User-Agent": user_agent}, timeout=30)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, Mapping):
            raise ValueError("SEC response was not a JSON object.")
        return payload

    return fetch_with_one_retry(SEC_PROVIDER, operation, fetch)


def _validate_user_agent(user_agent: str) -> None:
    if not isinstance(user_agent, str) or not user_agent.strip() or "@" not in user_agent:
        raise _invalid("identifiable_user_agent_required")


def _invalid(reason: str) -> ProviderUnavailable:
    return ProviderUnavailable(SEC_PROVIDER, reason)


def _content_hash(payload: Mapping[str, Any]) -> str:
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _normalize_cik(value: Any) -> str:
    if isinstance(value, bool):
        raise ValueError("CIK must be numeric.")
    text = str(value).strip()
    if not text.isdigit() or len(text) > 10:
        raise ValueError("CIK must be numeric.")
    return text.zfill(10)


def _submission_rows(submissions: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    recent = submissions["filings"]["recent"]
    return {
        accession: {"filed_at": filed_at, "report_date": report_date, "form": form}
        for accession, filed_at, report_date, form in zip(
            recent["accessionNumber"], recent["filingDate"], recent["reportDate"], recent["form"], strict=True
        )
        if isinstance(accession, str) and isinstance(filed_at, str) and isinstance(report_date, str) and isinstance(form, str)
    }


def _accounting_taxonomy(company_facts: Mapping[str, Any]) -> tuple[Mapping[str, Any], str]:
    facts = company_facts["facts"]
    if isinstance(facts.get("us-gaap"), Mapping):
        return facts["us-gaap"], "US-GAAP"
    if isinstance(facts.get("ifrs-full"), Mapping):
        return facts["ifrs-full"], "IFRS"
    raise ValueError("SEC companyfacts must contain US-GAAP or IFRS facts.")


def _metric_records(taxonomy: Mapping[str, Any], concepts: tuple[str, ...], kind: str) -> Iterable[dict[str, Any]]:
    found: set[tuple[str, str]] = set()
    for concept_name in concepts:
        concept = taxonomy.get(concept_name)
        if not isinstance(concept, Mapping) or not isinstance(concept.get("units"), Mapping):
            continue
        for unit_records in concept["units"].values():
            if not isinstance(unit_records, list):
                continue
            for raw in unit_records:
                record = _normalized_metric_record(raw, kind)
                if record is None or (record["accn"], record["period"]) in found:
                    continue
                found.add((record["accn"], record["period"]))
                yield record


def _normalized_metric_record(raw: Any, kind: str) -> dict[str, Any] | None:
    if not isinstance(raw, Mapping) or not isinstance(raw.get("accn"), str) or not isinstance(raw.get("end"), str):
        return None
    if not isinstance(raw.get("val"), (int, float)) or isinstance(raw.get("val"), bool):
        return None
    form = raw.get("form")
    if not _is_supported_form(form) or not isinstance(raw.get("filed"), str):
        return None
    period = _period_from_fact(raw, kind)
    if period is None:
        return None
    return {"accn": raw["accn"], "form": form, "filed": raw["filed"], "period": period, "end": raw["end"], "val": raw["val"]}


def _is_supported_form(value: Any) -> bool:
    return isinstance(value, str) and value.split("/", 1)[0] in _FORM_TYPES


def _period_from_fact(raw: Mapping[str, Any], kind: str) -> str | None:
    if kind == "annual_instant":
        # A balance sheet date is the period, full stop. `fy` names the report it was
        # printed in, and a prior-year comparative column carries this year's -- reading it
        # would file last year's inventory under this year and erase a year of growth.
        end = raw.get("end")
        if not isinstance(end, str) or not end.endswith("-12-31"):
            return None
        return end[:4]
    frame = raw.get("frame")
    if isinstance(frame, str):
        matched = re.fullmatch(r"CY(\d{4})(?:Q([1-4]))?", frame)
        if matched:
            year, quarter = matched.groups()
            if kind == "annual" and quarter is None:
                return year
            if kind == "quarterly" and quarter is not None:
                return f"{year}-Q{quarter}"
    fiscal_year, fiscal_period = raw.get("fy"), raw.get("fp")
    if isinstance(fiscal_year, int) and isinstance(fiscal_period, str):
        if kind == "annual" and fiscal_period == "FY":
            return str(fiscal_year)
        if kind == "quarterly" and fiscal_period in {"Q1", "Q2", "Q3", "Q4"}:
            return f"{fiscal_year}-{fiscal_period}"
    return None
