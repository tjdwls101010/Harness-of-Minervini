import json
import pathlib
import sqlite3
import tempfile
import unittest

from scripts.minervini.ledger import Ledger, resolve_ledger_path


class LedgerIntegrationTests(unittest.TestCase):
    def test_default_path_is_repo_local_state_and_environment_can_override_it(self) -> None:
        root = pathlib.Path("/repository")

        self.assertEqual(
            resolve_ledger_path(root=root, environ={}),
            root / ".state" / "research-ledger.sqlite3",
        )
        self.assertEqual(
            resolve_ledger_path(root=root, environ={"MINERVINI_LEDGER_PATH": "/tmp/ledger.sqlite3"}),
            pathlib.Path("/tmp/ledger.sqlite3"),
        )

    def test_show_and_history_do_not_create_a_missing_database(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = pathlib.Path(directory) / "state" / "research-ledger.sqlite3"
            ledger = Ledger(database)

            self.assertEqual(ledger.show(), [])
            self.assertEqual(ledger.history("AAPL"), [])
            self.assertFalse(database.exists())
            self.assertFalse(database.parent.exists())

    def test_record_and_annotate_preserve_auditable_research_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = pathlib.Path(directory) / "research-ledger.sqlite3"
            ledger = Ledger(database)

            recorded = ledger.record(
                instrument_id="us:0000320193",
                symbol="AAPL",
                as_of="2026-08-14",
                output_hash="abc123",
                verdict="WATCH",
                condition="Wait for a completed pivot breakout.",
                invalidation="Close below the 50-day SMA.",
                doctrine_ids=["funnel.confluence", "risk.hard_stop"],
                evidence_quality="complete",
                note="Initial review.",
            )
            annotated = ledger.annotate("AAPL", "Volume confirmation remains required.")

            self.assertTrue(database.exists())
            self.assertEqual(recorded["symbol"], "AAPL")
            self.assertEqual(recorded["doctrine_ids"], ["funnel.confluence", "risk.hard_stop"])
            self.assertEqual(annotated["note"], "Initial review.\nVolume confirmation remains required.")
            self.assertEqual(
                ledger.history("AAPL"),
                [
                    {"operation": "record", "note": "Initial review."},
                    {"operation": "annotate", "note": "Volume confirmation remains required."},
                ],
            )
            self.assertEqual(ledger.show(), [annotated])

    def test_export_writes_only_allowed_research_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            directory_path = pathlib.Path(directory)
            ledger = Ledger(directory_path / "research-ledger.sqlite3")
            ledger.record(
                instrument_id="us:0000320193",
                symbol="AAPL",
                as_of="2026-08-14",
                output_hash="abc123",
                verdict="WATCH",
                condition=None,
                invalidation=None,
                doctrine_ids=[],
                evidence_quality="partial",
                note=None,
            )
            destination = directory_path / "export.json"

            exported = ledger.export(destination)

            self.assertEqual(exported, {"path": str(destination), "count": 1})
            payload = json.loads(destination.read_text(encoding="utf-8"))
            self.assertEqual(payload[0]["instrument_id"], "us:0000320193")
            self.assertEqual(
                set(payload[0]),
                {
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
                },
            )

    def test_explicit_write_migrates_a_version_one_database_for_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = pathlib.Path(directory) / "research-ledger.sqlite3"
            connection = sqlite3.connect(database)
            connection.execute(
                """
                CREATE TABLE research_ledger (
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
                    PRIMARY KEY (instrument_id, as_of, output_hash)
                )
                """
            )
            connection.execute(
                """
                INSERT INTO research_ledger VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "us:0000320193",
                    "AAPL",
                    "2026-08-14",
                    "abc123",
                    "WATCH",
                    None,
                    None,
                    "[\"funnel.confluence\"]",
                    "complete",
                    "Legacy note.",
                ),
            )
            connection.execute("PRAGMA user_version = 1")
            connection.commit()
            connection.close()

            ledger = Ledger(database)
            self.assertEqual(ledger.history("AAPL"), [{"operation": "record", "note": "Legacy note."}])
            ledger.record(
                instrument_id="us:0000789019",
                symbol="MSFT",
                as_of="2026-08-14",
                output_hash="def456",
                verdict="WATCH",
                condition=None,
                invalidation=None,
                doctrine_ids=[],
                evidence_quality="complete",
                note=None,
            )
            history = ledger.history("AAPL")

            self.assertEqual(history, [{"operation": "record", "note": "Legacy note."}])
            with sqlite3.connect(database) as migrated:
                self.assertEqual(migrated.execute("PRAGMA user_version").fetchone()[0], 2)
                self.assertEqual(
                    [row[1] for row in migrated.execute("PRAGMA table_info(research_ledger)")],
                    [
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
                    ],
                )


if __name__ == "__main__":
    unittest.main()
