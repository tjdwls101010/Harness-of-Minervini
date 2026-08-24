#!/usr/bin/env python3
"""Check that every registry quotation really appears in the chapter row it cites.

The registry's central promise is that no claim executes without the source text
behind it. ``doctrine.validate()`` can only see that a quotation is well formed --
that it names a corpus, a row, and enough characters to be a sentence. Whether those
characters are the source's own words is a different question, and this is what asks it.

The extraction the corpus came from breaks words across line ends ("sta tistics",
"cut ting") and interleaves running page headers. A quotation that repairs those is
closer to the book than the extraction is, so comparison ignores them. What it does
not ignore is splicing: text stitched from non-adjacent passages and presented as one
continuous quote reads as something the author said in one breath, and did not.

Run it from the repository root when the build-time corpus is present:

    scripts/.venv/bin/python scripts/verify_doctrine_quotations.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sqlite3
import sys
import unicodedata


ROOT = Path(__file__).resolve().parents[1]
CORPORA = {"Minervini": ROOT / ".tmp" / "Minervini.db", "TraderLion": ROOT / ".tmp" / "TraderLion.db"}
_SMART = {"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-", "…": "..."}
# Everything a page boundary drops into the middle of a sentence: the figure blocks,
# the running head, the chapter rule, and the bare folio. None of it is prose, and a
# quotation that reads across it is quoting the author, not stitching two passages.
_PAGE_FURNITURE = (
    re.compile(r"!\[[^\]]*\](?:\([^)]*\))?", re.S),
    re.compile(r"t\s*r\s*a\s*d\s*e\s*l\s*i\s*k\s*e\s*a\s*s\s*t\s*o\s*c\s*k\s*m\s*a\s*r\s*k\s*e\s*t\s*w\s*i\s*z\s*a\s*r\s*d"),
    re.compile(r"c\s*h\s*a\s*p\s*t\s*e\s*r\s*\d+[a-z ]{0,60}?\d{2,4}"),
    re.compile(r"\*\*\d{1,4}\*\*"),
)


def collapse(text: str, *, source: bool = False) -> str:
    """Reduce prose to comparable letters, absorbing the extraction's own line noise."""

    text = unicodedata.normalize("NFC", text)
    for smart, plain in _SMART.items():
        text = text.replace(smart, plain)
    text = text.lower()
    if source:
        for pattern in _PAGE_FURNITURE:
            text = pattern.sub(" ", text)
    # A separator inside a number carries no meaning and a decimal point carries all of
    # it, so the point survives as a word while the thousands comma does not. Without
    # this, "7.5 percent" and "75 percent" normalise to the same string and a tenfold
    # alteration of a quoted figure reads as the author's own number.
    text = re.sub(r"(?<=\d),(?=\d)", "", text)
    text = re.sub(r"(?<=\d)\.(?=\d)", " point ", text)
    # A dash between figures makes a range and a colon makes a ratio. Stripping either
    # turns "30-40 percent" into "3040 percent" and "2:1" into "21", so an altered
    # figure would read as the author's own.
    text = re.sub(r"(?<=\d)\s*[-]\s*(?=\d)", " to ", text)
    text = re.sub(r"(?<=\d)\s*:\s*(?=\d)", " ratio ", text)
    # An operator and a sign are the whole content of a filter line. Dropping them lets
    # "> 69" read as "< 69" and "-25.00%" as "25.00%", reversing what was cited.
    text = text.replace("<=", " lte ").replace(">=", " gte ").replace("≤", " lte ").replace("≥", " gte ")
    text = text.replace("<", " lt ").replace(">", " gt ")
    text = re.sub(r"-(?=\d)", " minus ", text)
    # Dropping the remaining spaces and punctuation is what makes a hyphenation break
    # ("sta tistics") compare equal to the word the author actually wrote.
    return re.sub(r"[^a-z0-9]", "", text)


def load_rows() -> dict[tuple[str, int], tuple[str, ...]]:
    """Two readings of each row: as extracted, and with page furniture removed.

    Both are needed and neither is sufficient. This corpus puts real tables into figure
    alt-text, so removing figure blocks would delete the Trend Template itself; leaving
    them in would break any quotation that reads across a page boundary.
    """

    rows: dict[tuple[str, int], tuple[str, ...]] = {}
    for corpus, path in CORPORA.items():
        if not path.exists():
            continue
        with sqlite3.connect(path) as connection:
            for row_id, content in connection.execute("select id, content from chapters"):
                rows[(corpus, row_id)] = (collapse(content), collapse(content, source=True))
    return rows


def _reads_in_order(pieces: list[str], readings: tuple[str, ...]) -> bool:
    """Whether every piece appears in some one reading of the row, each after the last."""

    for body in readings:
        cursor = 0
        for piece in pieces:
            found = body.find(piece, cursor)
            if found < 0:
                break
            cursor = found + len(piece)
        else:
            return True
    return False


_MINIMUM_RUN = 24


def _uncovered(needle: str, readings: tuple[str, ...]) -> str | None:
    """The first stretch of the quotation that no reading accounts for.

    Checking sentence-sized pieces let a short one through: anything below the size
    floor was simply dropped, so a fabricated "Buy now." appended to a real passage was
    never looked at. Walking the whole string instead leaves nothing unexamined.
    """

    cursor = 0
    while cursor < len(needle):
        best = 0
        for body in readings:
            low, high = best, len(needle) - cursor
            while low < high:
                middle = (low + high + 1) // 2
                if needle[cursor : cursor + middle] in body:
                    low = middle
                else:
                    high = middle - 1
            best = max(best, low)
        if best < _MINIMUM_RUN:
            # A run this short is either the tail of a genuine assembly or an insertion.
            # Asking whether the whole remainder is somewhere in the row separates them,
            # instead of rejecting every assembly that ends in a short passage.
            remainder = needle[cursor:]
            if any(remainder in body for body in readings):
                return None
            return remainder[:_MINIMUM_RUN]
        cursor += best
    return None


def verify(registry: dict, rows: dict[tuple[str, int], tuple[str, ...]]) -> tuple[list[str], list[str], list[str]]:
    """Return undeclared defects, undeclared assemblies, and the declared departures."""

    defects: list[str] = []
    assembled: list[str] = []
    declarations: list[str] = []
    for record in registry["claims"]:
        for index, quotation in enumerate(record["provenance"].get("quotations", [])):
            label = f"{record['id']}[{index}]"
            key = (quotation["corpus"], quotation["row"])
            if key not in rows:
                defects.append(f"{label}: cites {key[0]} row {key[1]}, which does not exist")
                continue
            readings = rows[key]
            # An explicit ellipsis is the author of the quotation telling you they cut
            # something; each side of it still has to be the source's own words.
            pieces = [collapse(piece) for piece in quotation["text"].split("...") if collapse(piece)]
            if _reads_in_order(pieces, readings):
                continue
            needle = collapse(quotation["text"])
            elsewhere = [f"{name} row {row_id}" for (name, row_id), other in rows.items() if any(needle in reading for reading in other)]
            if elsewhere:
                defects.append(f"{label}: cites {key[0]} row {key[1]} but the text is in {', '.join(elsewhere)}")
                continue
            # A quotation may legitimately depart from the extraction: sentences joined
            # from a list, a passage read across a figure block, a word the extraction
            # broke and the transcriber repaired. A declaration explains why the pieces
            # are not adjacent. It never excuses a piece that is not in the source --
            # otherwise the field is a way to enter any sentence at all and have it
            # counted as verified.
            uncovered = _uncovered(needle, readings)
            declared = quotation.get("assembled_from")
            if uncovered is None:
                if declared:
                    declarations.append(f"{label}: {declared}")
                else:
                    assembled.append(f"{label}: every passage is genuine but they are not adjacent; needs assembled_from")
            elif declared:
                defects.append(f"{label}: declares '{declared}' but this is not in the source: {uncovered}")
            else:
                defects.append(f"{label}: departs from the extraction and does not say how; needs assembled_from")
    return defects, assembled, declarations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--registry", type=Path, default=ROOT / "doctrine" / "claims.json", help="registry to verify")
    arguments = parser.parse_args()

    rows = load_rows()
    if not rows:
        print("build-time corpus is absent; nothing to verify against", file=sys.stderr)
        return 0

    registry = json.loads(arguments.registry.read_text(encoding="utf-8"))
    total = sum(len(record["provenance"].get("quotations", [])) for record in registry["claims"])
    defects, assembled, declarations = verify(registry, rows)
    verified = total - len(defects) - len(assembled) - len(declarations)
    print(f"verified {verified} of {total} quotations across {len(registry['claims'])} claims")
    if declarations:
        print(f"\ndeclared departures from the extraction ({len(declarations)}) -- accepted because they say what they did:")
        for item in declarations:
            print(f"  {item}")
    if assembled:
        print(f"\nassembled from non-adjacent passages ({len(assembled)}) -- wording is the author's, adjacency is not:")
        for item in assembled:
            print(f"  {item}")
    if defects:
        print(f"\nnot source text ({len(defects)}):")
        for item in defects:
            print(f"  {item}")
    return 1 if defects or assembled else 0


if __name__ == "__main__":
    raise SystemExit(main())
