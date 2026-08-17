from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


LEDGER_ENV = "MINERVINI_LEDGER_PATH"
_DATABASE_VERSION = 2
_TABLE = "research_ledger"
_FIELDS = (
    "instrument_id",
    "symbol",
    "as_of",
    "output_hash",
    "verdict",
    "condition",
    "invalidation",
    "doctrine_ids",
    "evidence_quality",
    "note",
    "history",
)


def resolve_ledger_path(
    *, root: Path | None = None, environ: Mapping[str, str] | None = None
) -> Path:
    """Resolve, but do not create, the local research-ledger database path."""
    environment = os.environ if environ is None else environ
    configured = environment.get(LEDGER_ENV)
    if configured:
        return Path(configured)
    repository_root = root or Path(__file__).resolve().parents[2]
    return repository_root / ".state" / "research-ledger.sqlite3"


class Ledger:
    """Explicit-write local research ledger with a read-only public surface."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else resolve_ledger_path()

    def show(self) -> list[dict[str, Any]]:
        """Return the newest explicit snapshot for each recorded instrument."""
        if not self.path.exists():
            return []
        with self._read_connection() as connection:
            columns = self._columns(connection)
            if not columns:
                return []
            selectable = ", ".join(column for column in _FIELDS if column in columns)
            rows = connection.execute(
                f"""
                SELECT {selectable} FROM {_TABLE}
                WHERE rowid IN (
                    SELECT MAX(rowid) FROM {_TABLE} GROUP BY instrument_id
                )
                ORDER BY symbol, instrument_id
                """
            ).fetchall()
        return [self._decode(row, columns) for row in rows]

    def history(self, symbol: str) -> list[dict[str, Any]]:
        """Return recorded and annotation events for a symbol without writing the DB."""
        if not self.path.exists():
            return []
        with self._read_connection() as connection:
            columns = self._columns(connection)
            if not columns:
                return []
            if "history" not in columns:
                rows = connection.execute(
                    f"SELECT note FROM {_TABLE} WHERE symbol = ? ORDER BY rowid", (symbol,)
                ).fetchall()
                return [{"operation": "record", "note": row["note"]} for row in rows]
            rows = connection.execute(
                f"SELECT history FROM {_TABLE} WHERE symbol = ? ORDER BY rowid", (symbol,)
            ).fetchall()
        return [event for row in rows for event in self._decode_history(row["history"])]

    def record(
        self,
        *,
        instrument_id: str,
        symbol: str,
        as_of: str,
        output_hash: str,
        verdict: str,
        condition: str | None,
        invalidation: str | None,
        doctrine_ids: Sequence[str],
        evidence_quality: str | None,
        note: str | None,
    ) -> dict[str, Any]:
        """Create one auditable research snapshot; this is an explicit DB write."""
        normalized_doctrine_ids = self._doctrine_ids(doctrine_ids)
        history = [{"operation": "record", "note": note}]
        with self._write_connection() as connection:
            connection.execute(
                f"""
                INSERT INTO {_TABLE} ({", ".join(_FIELDS)})
                VALUES ({", ".join("?" for _ in _FIELDS)})
                """,
                (
                    instrument_id,
                    symbol,
                    as_of,
                    output_hash,
                    verdict,
                    condition,
                    invalidation,
                    json.dumps(normalized_doctrine_ids, ensure_ascii=False),
                    evidence_quality,
                    note,
                    json.dumps(history, ensure_ascii=False),
                ),
            )
        return {
            "instrument_id": instrument_id,
            "symbol": symbol,
            "as_of": as_of,
            "output_hash": output_hash,
            "verdict": verdict,
            "condition": condition,
            "invalidation": invalidation,
            "doctrine_ids": normalized_doctrine_ids,
            "evidence_quality": evidence_quality,
            "note": note,
            "history": history,
        }

    def annotate(self, symbol: str, note: str) -> dict[str, Any]:
        """Append a note to the newest snapshot for a symbol; this is an explicit DB write."""
        if not self.path.exists():
            raise KeyError(symbol)
        with self._write_connection() as connection:
            row = connection.execute(
                f"SELECT rowid, {', '.join(_FIELDS)} FROM {_TABLE} WHERE symbol = ? ORDER BY rowid DESC LIMIT 1",
                (symbol,),
            ).fetchone()
            if row is None:
                raise KeyError(symbol)
            current = self._decode(row, _FIELDS)
            combined_note = f"{current['note']}\n{note}" if current["note"] else note
            history = [*current["history"], {"operation": "annotate", "note": note}]
            connection.execute(
                f"UPDATE {_TABLE} SET note = ?, history = ? WHERE rowid = ?",
                (combined_note, json.dumps(history, ensure_ascii=False), row["rowid"]),
            )
        return {**current, "note": combined_note, "history": history}

    def export(self, destination: Path | str) -> dict[str, Any]:
        """Explicitly export current research snapshots as JSON."""
        output = Path(destination)
        records = self.show()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"path": str(output), "count": len(records)}

    def _read_connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        return connection

    def _write_connection(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        self._migrate(connection)
        return connection

    @staticmethod
    def _columns(connection: sqlite3.Connection) -> tuple[str, ...]:
        return tuple(row["name"] for row in connection.execute(f"PRAGMA table_info({_TABLE})"))

    @staticmethod
    def _decode_history(value: str | None) -> list[dict[str, Any]]:
        if not value:
            return []
        decoded = json.loads(value)
        if not isinstance(decoded, list) or not all(isinstance(event, dict) for event in decoded):
            raise ValueError("invalid ledger history")
        return decoded

    def _decode(self, row: sqlite3.Row, columns: Sequence[str]) -> dict[str, Any]:
        record = {field: row[field] if field in columns else None for field in _FIELDS}
        record["doctrine_ids"] = self._decode_doctrine_ids(record["doctrine_ids"])
        record["history"] = self._decode_history(record["history"]) if "history" in columns else [
            {"operation": "record", "note": record["note"]}
        ]
        return record

    @staticmethod
    def _doctrine_ids(doctrine_ids: Sequence[str]) -> list[str]:
        if isinstance(doctrine_ids, (str, bytes)) or not all(isinstance(item, str) for item in doctrine_ids):
            raise ValueError("doctrine_ids must be a sequence of strings")
        return list(doctrine_ids)

    @staticmethod
    def _decode_doctrine_ids(value: str) -> list[str]:
        decoded = json.loads(value)
        if not isinstance(decoded, list) or not all(isinstance(item, str) for item in decoded):
            raise ValueError("invalid ledger doctrine_ids")
        return decoded

    @staticmethod
    def _migrate(connection: sqlite3.Connection) -> None:
        columns = Ledger._columns(connection)
        if not columns:
            connection.execute(
                f"""
                CREATE TABLE {_TABLE} (
                    instrument_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    as_of TEXT NOT NULL,
                    output_hash TEXT NOT NULL,
                    verdict TEXT NOT NULL,
                    condition TEXT,
                    invalidation TEXT,
                    doctrine_ids TEXT NOT NULL,
                    evidence_quality TEXT,
                    note TEXT,
                    history TEXT NOT NULL,
                    PRIMARY KEY (instrument_id, as_of, output_hash)
                )
                """
            )
            connection.execute(f"PRAGMA user_version = {_DATABASE_VERSION}")
            return
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version < 1:
            version = 1
            connection.execute("PRAGMA user_version = 1")
        if version < 2:
            connection.execute(f"ALTER TABLE {_TABLE} ADD COLUMN history TEXT NOT NULL DEFAULT '[]'")
            rows = connection.execute(f"SELECT rowid, note FROM {_TABLE}").fetchall()
            for row in rows:
                connection.execute(
                    f"UPDATE {_TABLE} SET history = ? WHERE rowid = ?",
                    (json.dumps([{"operation": "record", "note": row["note"]}], ensure_ascii=False), row["rowid"]),
                )
            connection.execute("PRAGMA user_version = 2")
