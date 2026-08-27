"""A quarter's fact spans a quarter, and its period comes from its own dates.

NVDA's fiscal year closes in late January, and its filings show what that does here. Every
10-Q carries two duration facts for the same closing date -- the three months of the quarter
and the year-to-date run-up to it -- and the provider read both as quarterly, so a nine-month
cumulative figure was published as one quarter's earnings.

Then the period label. A fact with no `frame` fell back to `fy`/`fp`, which name the fiscal
year of the report the fact was printed in, not the year the fact belongs to. The same quarter
therefore arrived as `2026-Q2` from the report that first published it and as `2027-Q2` from
the following year's comparative column, so the two never met and no four consecutive quarters
existed to build a trailing year from.
"""

from __future__ import annotations

import unittest

from scripts.minervini.providers.sec import normalize_filed_facts


AS_OF = "2026-08-27"

# (start, end, val, frame) -- the shape SEC actually returns for a January-closing filer.
_FILINGS = [
    ("0001045810-25-000128", "10-Q", "2025-08-27", 2026, "Q2", [
        ("2025-01-27", "2025-07-27", 1.84, None),
        ("2025-04-28", "2025-07-27", 1.08, None),
    ]),
    ("0001045810-25-000200", "10-Q", "2025-11-19", 2026, "Q3", [
        ("2025-01-27", "2025-10-26", 3.14, None),
        ("2025-07-28", "2025-10-26", 1.30, "CY2025Q3"),
    ]),
    ("0001045810-26-000032", "10-K", "2026-02-25", 2026, "FY", [
        ("2025-01-27", "2026-01-25", 4.90, "CY2025"),
    ]),
    ("0001045810-26-000090", "10-Q", "2026-05-20", 2027, "Q1", [
        ("2026-01-26", "2026-04-26", 2.39, "CY2026Q1"),
    ]),
    ("0001045810-26-000140", "10-Q", "2026-08-26", 2027, "Q2", [
        ("2025-01-27", "2025-07-27", 1.84, None),
        ("2025-04-28", "2025-07-27", 1.08, "CY2025Q2"),
        ("2026-01-26", "2026-07-26", 4.85, None),
        ("2026-04-27", "2026-07-26", 2.46, "CY2026Q2"),
    ]),
]


def company_facts() -> dict:
    rows = []
    for accn, form, filed, fy, fp, facts in _FILINGS:
        for start, end, val, frame in facts:
            rows.append({"start": start, "end": end, "val": val, "accn": accn, "filed": filed, "form": form, "fy": fy, "fp": fp, **({"frame": frame} if frame else {})})
    return {
        "cik": 1045810,
        "entityName": "NVIDIA Corporation",
        "facts": {"us-gaap": {"EarningsPerShareDiluted": {"label": "EPS diluted", "units": {"USD/shares": rows}}}},
    }


def submissions() -> dict:
    return {
        "cik": 1045810,
        "filings": {"recent": {
            "accessionNumber": [row[0] for row in _FILINGS],
            "filingDate": [row[2] for row in _FILINGS],
            "reportDate": [row[5][-1][1] for row in _FILINGS],
            "form": [row[1] for row in _FILINGS],
        }},
    }


def quarters() -> dict[str, float]:
    evidence = normalize_filed_facts(company_facts(), submissions(), as_of=AS_OF)
    found = {}
    for filing in evidence["filings"]:
        for fact in filing["quarterly"]:
            found[fact["period"]] = fact.get("eps")
    return found


class AYearToDateFigureIsNotAQuarter(unittest.TestCase):
    def test_the_six_month_run_up_never_becomes_a_quarter(self) -> None:
        self.assertNotIn(1.84, quarters().values())

    def test_the_nine_month_run_up_never_becomes_a_quarter(self) -> None:
        self.assertNotIn(3.14, quarters().values())

    def test_the_three_month_figure_is_the_one_that_survives(self) -> None:
        self.assertEqual(quarters()["2026-Q2"], 2.46)


class ThePeriodComesFromTheFactNotFromTheReport(unittest.TestCase):
    def test_a_comparative_column_carries_the_year_it_measures(self) -> None:
        # The 2026-08-26 report prints the quarter ended 2025-07-27 with `fy=2027`. That is the
        # report's fiscal year. The quarter's own is the one the earlier report gave it.
        self.assertNotIn("2027-Q2", quarters())
        self.assertEqual(quarters()["2025-Q2"], 1.08)

    def test_the_quarters_run_consecutively(self) -> None:
        self.assertEqual(sorted(quarters()), ["2025-Q2", "2025-Q3", "2026-Q1", "2026-Q2"])

    def test_the_fiscal_year_closing_in_january_is_labelled_by_the_year_it_covers(self) -> None:
        evidence = normalize_filed_facts(company_facts(), submissions(), as_of=AS_OF)
        annual = {fact["period"]: fact.get("eps") for filing in evidence["filings"] for fact in filing["annual"]}

        self.assertEqual(annual, {"2025": 4.90})


if __name__ == "__main__":
    unittest.main()
