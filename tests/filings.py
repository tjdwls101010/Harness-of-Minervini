"""Filed SEC document fixtures and normalized filing builders."""

from __future__ import annotations

import pandas as pd


CIK = "0000000042"
AS_OF = "2026-05-08"

_QUARTERS = [
    ("2024-Q1", "2024-01-01", "2024-03-31", 0.50, 100.0, 10.0, 100.0, "0000042-24-000001", "2024-04-25", "10-Q"),
    ("2024-Q2", "2024-04-01", "2024-06-30", 0.55, 110.0, 11.5, 100.0, "0000042-24-000002", "2024-07-25", "10-Q"),
    ("2024-Q3", "2024-07-01", "2024-09-30", 0.60, 120.0, 13.2, 100.0, "0000042-24-000003", "2024-10-25", "10-Q"),
    ("2024-Q4", "2024-10-01", "2024-12-31", 0.65, 130.0, 15.0, 100.0, "0000042-25-000001", "2025-02-20", "10-K"),
    ("2025-Q1", "2025-01-01", "2025-03-31", 0.70, 140.0, 17.0, 100.5, "0000042-25-000002", "2025-04-25", "10-Q"),
    ("2025-Q2", "2025-04-01", "2025-06-30", 0.82, 158.0, 20.5, 100.5, "0000042-25-000003", "2025-07-25", "10-Q"),
    ("2025-Q3", "2025-07-01", "2025-09-30", 0.98, 182.0, 25.5, 101.0, "0000042-25-000004", "2025-10-24", "10-Q"),
    ("2025-Q4", "2025-10-01", "2025-12-31", 1.20, 215.0, 32.5, 101.0, "0000042-26-000001", "2026-02-19", "10-K"),
]

_ANNUALS = [
    ("CY2023", "2023-01-01", "2023-12-31", 1.60, 380.0, "0000042-24-000004", "2024-02-21", "10-K"),
    ("CY2024", "2024-01-01", "2024-12-31", 2.30, 460.0, "0000042-25-000001", "2025-02-20", "10-K"),
    ("CY2025", "2025-01-01", "2025-12-31", 3.70, 695.0, "0000042-26-000001", "2026-02-19", "10-K"),
]


def _unit(rows: list[tuple], value_index: int, *, quarterly: bool) -> list[dict]:
    facts = []
    for row in rows:
        frame = row[0].replace("-", "") if quarterly else row[0]
        facts.append({
            "start": row[1],
            "end": row[2],
            "val": row[value_index],
            "accn": row[-3],
            "filed": row[-2],
            "form": row[-1],
            "fy": int(row[2][:4]),
            "fp": row[0].split("-")[-1] if quarterly else "FY",
            "frame": f"CY{frame}" if quarterly else frame,
        })
    return facts


def company_facts(**overrides) -> dict:
    facts = {
        "EarningsPerShareDiluted": ("USD/shares", _unit(_QUARTERS, 3, quarterly=True) + _unit(_ANNUALS, 3, quarterly=False)),
        "Revenues": ("USD", _unit(_QUARTERS, 4, quarterly=True) + _unit(_ANNUALS, 4, quarterly=False)),
        "NetIncomeLoss": ("USD", _unit(_QUARTERS, 5, quarterly=True)),
        "WeightedAverageNumberOfDilutedSharesOutstanding": ("shares", _unit(_QUARTERS, 6, quarterly=True)),
    }
    return {
        "cik": int(CIK),
        "entityName": "Test Corp",
        "facts": {"us-gaap": {concept: {"label": concept, "units": {unit: rows}} for concept, (unit, rows) in facts.items()}},
        **overrides,
    }


def submissions() -> dict:
    rows = {(row[-3], row[-2], row[-1], row[2]) for row in _QUARTERS} | {(row[-3], row[-2], row[-1], row[2]) for row in _ANNUALS}
    ordered = sorted(rows, key=lambda item: item[1])
    return {
        "cik": int(CIK),
        "filings": {
            "recent": {
                "accessionNumber": [row[0] for row in ordered],
                "filingDate": [row[1] for row in ordered],
                "reportDate": [row[3] for row in ordered],
                "form": [row[2] for row in ordered],
            }
        },
    }


def bars(start: str, end: str, close: float) -> pd.DataFrame:
    index = pd.bdate_range(start, end)
    return pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": [close + n * 0.01 for n in range(len(index))], "Volume": 1_000_000}, index=index)


def quarter(period: str, end: str, eps: float, **overrides) -> dict:
    return {"period": period, "end": end, "eps": eps, "revenue": 100.0, "net_income": overrides["net_income"] if "net_income" in overrides else eps * 10, "diluted_shares": 100.0, **overrides}


def annual(year: int, eps: float, **extra) -> dict:
    return {"period": str(year), "end": f"{year}-12-31", "eps": eps, "revenue": 400.0, "diluted_shares": 100.0, **extra}


def filing(form: str = "10-K", quarterly: list[dict] | None = None, years: list[dict] | None = None, *, filed_at: str = "2026-02-19", basis: str = "US-GAAP") -> dict:
    return {"filed_at": filed_at, "form": form, "accounting_basis": basis, "quarterly": quarterly or [], "annual": years or []}


def evidence(quarters: list[dict] | None = None, years: list[dict] | None = None, *, filed_at: str = "2026-02-19", form: str = "10-K", basis: str = "US-GAAP", filings: list[dict] | None = None) -> dict:
    return {"source": "sec_filed_facts", "filings": [{"filed_at": filed_at, "form": form, "accounting_basis": basis, "quarterly": quarters, "annual": years or []}] if filings is None else filings}
