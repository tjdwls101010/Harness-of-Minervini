from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
import math
from typing import Any, Callable, Iterable, Mapping

from . import ProviderSnapshot, ProviderUnavailable, RequestThrottle, SnapshotMeta, fetch_with_one_retry


SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_PROVIDER = "sec"
MIN_REQUEST_INTERVAL_SECONDS = 0.15
_THROTTLE = RequestThrottle(MIN_REQUEST_INTERVAL_SECONDS)
# 40-F is the Canadian MJDS annual report, and this harness covers ADRs. Dropping the form
# turned every such issuer into a company that had filed nothing. 6-K stays out: it furnishes
# whatever the issuer chose to send, so its form name says nothing about what is inside it.
_FORM_TYPES = {"10-Q", "10-K", "20-F", "40-F"}
# What a duration fact has to span to be one. Thirteen weeks is 91 days and a fourteen-week
# quarter is 98; a 52/53-week year is 364 or 371 and a calendar one 365 or 366. These are
# shapes of the document, not doctrine -- nothing here is a threshold a source stated.
_QUARTER_LENGTH_DAYS = (80, 100)
_FISCAL_YEAR_LENGTH_DAYS = (340, 380)
# How far back from a close the middle of the period it closes sits. Read from the close alone
# rather than from the span, because the close is the half of a duration fact an amendment
# never moves: a 10-K/A correcting 52 weeks to 53 pushed a span midpoint back across New Year
# and the corrected year arrived as the year before the one it was correcting.
_HALF_QUARTER_DAYS = 45
_HALF_YEAR_DAYS = 182
_QUARTERLY_METRICS = {
    "eps": ("EarningsPerShareDiluted", "DilutedEarningsLossPerShare", "BasicAndDilutedEarningsLossPerShare"),
    "revenue": ("RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet", "Revenues", "Revenue"),
    "net_income": ("NetIncomeLoss", "ProfitLoss"),
    "diluted_shares": ("WeightedAverageNumberOfDilutedSharesOutstanding",),
}
_ANNUAL_METRICS = {"eps": _QUARTERLY_METRICS["eps"], "revenue": _QUARTERLY_METRICS["revenue"], "net_income": _QUARTERLY_METRICS["net_income"], "diluted_shares": _QUARTERLY_METRICS["diluted_shares"]}
# Balances rather than flows. Inventory and receivables are reported as of a date, so a
# filing carries no `start` for them and the period they belong to is the one whose books
# close on that date -- never the fiscal year of the report, which for a comparative column
# is this year while the balance is last year's.
# Both taxonomies, because the provider accepts both. Looking for US-GAAP names only meant a
# 20-F filer's balance sheet was dropped before per-field provenance could see it, and the
# readings built on it reported evidence the company had in fact filed as evidence it lacked.
_ANNUAL_INSTANT_METRICS = {
    "inventory": ("InventoryNet", "InventoryFinishedGoodsNetOfReserves", "InventoryGross", "Inventories"),
    "accounts_receivable": ("AccountsReceivableNetCurrent", "ReceivablesNetCurrent", "AccountsReceivableNet", "TradeAndOtherCurrentReceivables", "CurrentTradeReceivables"),
    "stockholders_equity": ("StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "Equity", "EquityAttributableToOwnersOfParent"),
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
    taxonomies = _accounting_taxonomies(company_facts)
    filings: dict[str, dict[str, Any]] = {}
    annual_ends = _annual_period_by_end(taxonomies, submission_rows, boundary)
    for kind, metrics in (("quarterly", _QUARTERLY_METRICS), ("annual", _ANNUAL_METRICS), ("annual_instant", _ANNUAL_INSTANT_METRICS)):
        for metric, concepts in metrics.items():
            for record in _metric_records(taxonomies, concepts, kind, annual_ends):
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
                # Keyed by the regime as well as the accession, because a filing can carry
                # both and the basis is what stamps every field's provenance. One entry per
                # regime keeps each number under the regime that measured it.
                filing = filings.setdefault(
                    (accession, record["accounting_basis"]),
                    {
                        "filed_at": submission["filed_at"],
                        # The form as filed, amendment suffix and all. Support is decided on
                        # the half before the slash, because an amendment carries facts, but
                        # publishing only that half loses the one thing that tells a reader
                        # these numbers replaced numbers already published.
                        "form": submission["form"],
                        "accounting_basis": record["accounting_basis"],
                        "quarterly": {},
                        "annual": {},
                    },
                )
                bucket = "annual" if kind == "annual_instant" else kind
                # Keyed by the closing date too. The period name is a projection and two closes
                # can reach one; merging them here kept a single figure and left the evaluator
                # nothing to notice, where its own rule is to withhold the whole period.
                fact = filing[bucket].setdefault(
                    (record["period"], record["end"]),
                    # The span travels with the period. Two annual periods that overlap are
                    # not a year and the year before it, and without the start nothing
                    # downstream can tell that they do.
                    {"period": record["period"], "end": record["end"], **({"start": record["start"]} if record.get("start") else {}), "_units": {}},
                )
                fact[metric] = record["val"]
                fact["_units"][metric] = record["unit"]

    normalized_filings = []
    for filing in sorted(filings.values(), key=lambda item: (item["filed_at"], item["accounting_basis"])):
        normalized_filings.append(
            {
                "filed_at": filing["filed_at"],
                "form": filing["form"],
                "accounting_basis": filing["accounting_basis"],
                # Ordered by the closing date, so that a period two closes reached arrives the
                # same way whichever order the provider sent the two facts in.
                "quarterly": [fact for _, fact in sorted(filing["quarterly"].items())],
                "annual": [fact for _, fact in sorted(filing["annual"].items())],
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


def _accounting_taxonomies(company_facts: Mapping[str, Any]) -> list[tuple[Mapping[str, Any], str]]:
    """Every taxonomy the company filed under, because a registrant can change one.

    Choosing one for the whole company read whichever was present first, so the day a 10-K
    appeared every IFRS year the filer had ever published stopped existing -- including for an
    `as_of` before that 10-K was filed, which is a future document deciding a past answer.
    Provenance is already per field, so both regimes can travel together from here.
    """

    facts = company_facts["facts"]
    found = [(facts[name], basis) for name, basis in (("us-gaap", "US-GAAP"), ("ifrs-full", "IFRS")) if isinstance(facts.get(name), Mapping)]
    if not found:
        raise ValueError("SEC companyfacts must contain US-GAAP or IFRS facts.")
    return found


def _annual_period_by_end(taxonomies: list[tuple[Mapping[str, Any], str]], submission_rows: Mapping[str, Any], boundary: date) -> dict[str, str]:
    """Each fiscal year's closing date, mapped to the year it closes, as of the request's boundary.

    A balance is dated, not spanned, so nothing in the fact itself says which fiscal year it
    closes. The income statement for that year does: it ends on the same date. Requiring 31
    December instead dropped every balance a September or January filer ever filed, silently,
    because a dropped fact and a fact the company never filed look identical downstream.

    The map is built from the same filings the request can see. Reading the whole taxonomy let a
    filing three weeks past `as_of` decide which fiscal year an earlier balance belonged to,
    which is a future document reaching into a point-in-time answer. And a closing date two
    filings disagree about is left out rather than resolved by input order: the balance is then
    a balance nobody can place, which is what it is.
    """

    ends: dict[str, str] = {}
    conflicts: set[str] = set()
    for concepts in _ANNUAL_METRICS.values():
        for record in _metric_records(taxonomies, concepts, "annual", {}):
            submission = submission_rows.get(record["accn"])
            if submission is None or not _is_supported_form(submission["form"]) or record.get("form") != submission["form"]:
                continue
            if _filed_date(submission["filed_at"]) > boundary:
                continue
            end = record.get("end")
            if not isinstance(end, str):
                continue
            if ends.setdefault(end, record["period"]) != record["period"]:
                conflicts.add(end)
    return {end: period for end, period in ends.items() if end not in conflicts}


def _metric_records(taxonomies: list[tuple[Mapping[str, Any], str]], concepts: tuple[str, ...], kind: str, annual_ends: Mapping[str, str]) -> Iterable[dict[str, Any]]:
    """Every fact of this metric, once per closing date rather than once per period name.

    The name is a projection and two closes can reach one, which is precisely the collision the
    evaluator withholds. Deduplicating on the name alone kept whichever fact the provider
    happened to send first, so that decision never saw the second close and the answer depended
    on input order. The unit travels too: SEC files a concept once per unit, and a hundred US
    dollars beside a hundred and thirty Canadian ones is not thirty percent of growth.
    """

    found: set[tuple[str, str, str]] = set()
    for taxonomy, accounting_basis in taxonomies:
        for concept_name in concepts:
            concept = taxonomy.get(concept_name)
            if not isinstance(concept, Mapping) or not isinstance(concept.get("units"), Mapping):
                continue
            for unit, unit_records in concept["units"].items():
                if not isinstance(unit_records, list):
                    continue
                for raw in unit_records:
                    record = _normalized_metric_record(raw, kind, annual_ends)
                    if record is None or (record["accn"], record["period"], record["end"]) in found:
                        continue
                    found.add((record["accn"], record["period"], record["end"]))
                    yield {**record, "accounting_basis": accounting_basis, "unit": unit if isinstance(unit, str) else None}


def _normalized_metric_record(raw: Any, kind: str, annual_ends: Mapping[str, str]) -> dict[str, Any] | None:
    if not isinstance(raw, Mapping) or not isinstance(raw.get("accn"), str) or not isinstance(raw.get("end"), str):
        return None
    value = raw.get("val")
    # A boundary that admits a value the arithmetic cannot use is not a boundary. `nan` reached
    # a published return-on-equity and then broke strict JSON encoding at the envelope.
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        return None
    form = raw.get("form")
    if not _is_supported_form(form) or not isinstance(raw.get("filed"), str):
        return None
    period = _period_from_fact(raw, kind, annual_ends)
    if period is None:
        return None
    return {"accn": raw["accn"], "form": form, "filed": raw["filed"], "period": period, "start": raw.get("start"), "end": raw["end"], "val": raw["val"]}


def _is_supported_form(value: Any) -> bool:
    return isinstance(value, str) and value.split("/", 1)[0] in _FORM_TYPES


def _period_from_fact(raw: Mapping[str, Any], kind: str, annual_ends: Mapping[str, str]) -> str | None:
    if kind == "annual_instant":
        # A balance sheet date is the period, and the fiscal year it belongs to is the one whose
        # income statement closes on that same date. `fy` names the report it was printed in, and
        # a prior-year comparative column carries this year's -- reading it would file last
        # year's inventory under this year and erase a year of growth. A date matching no fiscal
        # year end is a quarter's balance and is not this bucket's fact.
        end = raw.get("end")
        return annual_ends.get(end) if isinstance(end, str) else None
    span = _duration(raw)
    if span is None:
        return None
    start, end = span
    days = (end - start).days
    lower, upper = _QUARTER_LENGTH_DAYS if kind == "quarterly" else _FISCAL_YEAR_LENGTH_DAYS
    # A quarter's fact spans a quarter. Every 10-Q also carries the year-to-date run-up to the
    # same closing date, and reading that as one quarter published a nine-month cumulative
    # figure as three months of earnings -- above every growth band it was then measured
    # against. Length is what tells the two apart; nothing else in the fact does.
    if not lower <= days <= upper:
        return None
    if kind == "annual":
        return str((end - timedelta(days=_HALF_YEAR_DAYS)).year)
    middle = end - timedelta(days=_HALF_QUARTER_DAYS)
    return f"{middle.year}-Q{(middle.month - 1) // 3 + 1}"


def _duration(raw: Mapping[str, Any]) -> tuple[date, date] | None:
    try:
        return date.fromisoformat(str(raw["start"])), date.fromisoformat(str(raw["end"]))
    except (KeyError, TypeError, ValueError):
        return None
