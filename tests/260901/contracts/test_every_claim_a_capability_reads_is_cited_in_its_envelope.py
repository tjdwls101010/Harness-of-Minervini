"""A claim a reducer read and the envelope never named is doctrine applied off the record.

Decision 301 checks the citations resolve; the reverse -- a claim read at runtime that no
envelope mentions -- had nothing checking it, and decisions 313 and 317 each caught one
instance by hand. A reader following the citation list is told which sentences governed the
answer, so a threshold that moved the verdict and is absent from that list is a standard the
reader cannot audit and cannot argue with.

Recorded at runtime rather than walked statically, because an envelope's citations are not a
literal in the source: `_named_doctrine_ids` harvests `*doctrine_ids` keys out of the data the
reducers built, so what a capability cites is only knowable once it has run.

Only a call that returned is a read. `setup._owning_claim` finds the claim owning a condition
by trying successively shorter prefixes of its name and catching the failures, so counting the
attempts would report the composite `market.correction_depth_healthy_leader.correction_failure_threshold`
as a claim this harness reads, and no registry holds it.
"""

from __future__ import annotations

import contextlib
import functools
import importlib
import pathlib
import tempfile
import unittest

from scripts.minervini import doctrine
from scripts.minervini.operations import execute


# The whole-capability driver already exists, with the request table and the two provider
# runtimes. Imported by name because a test package under a date-named directory has no
# dotted path an `import` statement can spell.
_VOCABULARY = importlib.import_module("tests.260828.contracts.test_a_declared_vocabulary_matches_the_envelopes")

# Every accessor that hands back what a claim says. `has_claim` is absent on purpose: asking
# whether the registry holds an id is a membership test, not a reading of doctrine.
_READS = (
    "claim",
    "required_inputs",
    "threshold",
    "parameter",
    "evaluate_gate",
    "evaluate_marker",
    "evaluate_band",
    "binds",
    "quotation",
)


@contextlib.contextmanager
def recording() -> "list[str]":
    """Record the claim id of every doctrine read that returned, for the duration of the block."""

    read: list[str] = []
    originals = {name: getattr(doctrine, name) for name in _READS}

    def wrap(function):
        @functools.wraps(function)
        def recorder(claim_id, *args, **kwargs):
            answer = function(claim_id, *args, **kwargs)
            read.append(claim_id)
            return answer

        return recorder

    for name, function in originals.items():
        setattr(doctrine, name, wrap(function))
    try:
        yield read
    finally:
        for name, function in originals.items():
            setattr(doctrine, name, function)


def _envelopes():
    """Every capability, under both the withholding and the measured providers."""

    for label, build in (("withholding", _VOCABULARY.withholding), ("measured", _VOCABULARY.measured)):
        with tempfile.TemporaryDirectory() as temporary:
            runtime = build(pathlib.Path(temporary) / "ledger.sqlite3")
            for capability, request in _VOCABULARY.REQUESTS.items():
                # The export destination is a caller-selected path, so it lives with the ledger.
                extra = {"output": str(pathlib.Path(temporary) / "export.csv")} if capability == "watchlist.export" else {}
                with recording() as read:
                    payload = execute(capability, {**request, **extra}, runtime=runtime)
                yield label, capability, read, payload


# A read whose reading reaches no reader, declared one at a time with the reason, the way the
# quotation verifier declares its departures. The rule stays "read it, cite it"; what an entry
# here says is that this particular reading was built and then withheld whole, so citing it
# would tell a reader a standard governed an answer it had no part in.
_WITHHELD = {
    (
        "ticker.risk",
        "management.market_defense_tightens_stops",
    ): "an INCOMPLETE verdict publishes no management readings at all -- `management_evidence` "
    "is emptied wholesale, which tests/260827/integration/test_windows_and_citations.py pins "
    "as 'nothing was established, so nothing is measured about it' -- so the block this band "
    "was evaluated for reaches nobody",
}


class EveryClaimReadIsCited(unittest.TestCase):
    def test_no_capability_reads_a_claim_its_envelope_does_not_name(self) -> None:
        uncited: list[str] = []
        for label, capability, read, payload in _envelopes():
            cited = set(payload.get("doctrine_ids") or [])
            for claim_id in sorted(set(read) - cited):
                if (capability, claim_id) in _WITHHELD:
                    continue
                uncited.append(f"{capability} ({label}, status={payload.get('status')}) read {claim_id}")
        self.assertEqual(uncited, [], "claims read and never cited:\n" + "\n".join(uncited))

    def test_every_declared_departure_is_still_one(self) -> None:
        """A departure nobody takes any more is a sentence that reads as permission and grants
        none, and the next reader takes it for a rule. Each entry has to still be reachable."""

        taken = {
            (capability, claim_id)
            for _, capability, read, payload in _envelopes()
            for claim_id in set(read) - set(payload.get("doctrine_ids") or [])
        }
        self.assertEqual(sorted(set(_WITHHELD) - taken), [], "declared departures nothing exercises any more")

    def test_the_recorder_is_recording(self) -> None:
        """A recorder that intercepted nothing would report a clean sweep over every capability.

        `ticker.setup` is the densest reader in the harness; if this floor is not met the
        wrapper is no longer in the path the reducers call through, and the check above is
        passing vacuously rather than passing.
        """

        counts = {capability: len(set(read)) for _, capability, read, _ in _envelopes()}
        self.assertGreaterEqual(counts.get("ticker.setup", 0), 10)
        self.assertGreaterEqual(sum(counts.values()), 30)

    def test_a_read_that_raised_is_not_counted_as_one(self) -> None:
        """The positive control for the probe/read distinction the module docstring names."""

        with recording() as read:
            doctrine.claim("convention.trading_week")
            with self.assertRaises(KeyError):
                doctrine.claim("market.correction_depth_healthy_leader.correction_failure_threshold")
        self.assertEqual(read, ["convention.trading_week"])

    def test_the_recorder_puts_the_registry_back(self) -> None:
        before = {name: getattr(doctrine, name) for name in _READS}
        with recording():
            self.assertIsNot(doctrine.claim, before["claim"])
        self.assertEqual({name: getattr(doctrine, name) for name in _READS}, before)


if __name__ == "__main__":
    unittest.main()
