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

import builtins
import contextlib
import functools
import pathlib
import sys
import tempfile
import types
import unittest
from collections.abc import Mapping
from datetime import datetime, timezone

from scripts.minervini import doctrine
from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot, SnapshotMeta

from tests.series import power_play_series


# The whole-capability driver already exists, with the request table and the two provider
# runtimes. Imported by name because a test package under a date-named directory has no
# dotted path an `import` statement can spell.
from tests import harness as _VOCABULARY

# Every accessor that hands back what a claim says, and takes the claim as its first argument.
# `has_claim` is absent on purpose: asking whether the registry holds an id is a membership
# test, not a reading of doctrine, and `validate` checks the registry's own structure rather
# than answering about one claim. `doctrine.list` returns claim contents but is addressed by
# filter rather than by id, so there is nothing to record a citation against; it has no runtime
# caller today, and one appearing is a reason to give this guard a way to see it.
_READS = (
    "claim",
    "get_claim",
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

    wrapped = {name: wrap(function) for name, function in originals.items()}

    # Rebound on every module attribute that holds one of these functions, not only on
    # `doctrine`. A module that wrote `from .doctrine import get_claim` holds the original
    # directly and would keep calling it -- `operations` does exactly that, so patching the
    # module alone left `doctrine.show` reading a claim invisibly, and deleting its citation
    # would have passed this guard. Matched by identity rather than by name, so an import
    # bound under an alias is caught too.
    #
    # What this does not reach: a reference captured in a closure, held in a default argument
    # or stored in a container, and a module imported for the first time inside the block. None
    # of those is how this harness calls doctrine today, and each would make a read invisible
    # here -- so the claim is "every module-level binding that exists when recording starts",
    # not "everywhere the function is reachable".
    by_identity = {id(function): name for name, function in originals.items()}
    bindings = [
        (module, attribute, by_identity[id(value)])
        for module in [value for key, value in sys.modules.items() if key.startswith("scripts.minervini") and value]
        for attribute, value in builtins.list(vars(module).items())
        if id(value) in by_identity
    ]
    for module, attribute, name in bindings:
        setattr(module, attribute, wrapped[name])
    try:
        yield read
    finally:
        for module, attribute, name in bindings:
            setattr(module, attribute, originals[name])


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
    # The branches the table's two runtimes cannot reach, which that module maintains for the
    # same reason this one needs them: the prospective half of a reducer that has two, and
    # readings that come from another fixture session. A read hiding in a status the sweep
    # never produces is a read this guard would certify.
    for capability, label, request in _VOCABULARY.EXTRA_CASES:
        runtime = {"filed": _VOCABULARY.filed, "current": _VOCABULARY.current, "listed": _VOCABULARY.listed}.get(label, _VOCABULARY.sealed)()
        with recording() as read:
            payload = execute(capability, request, runtime=runtime)
        yield label, capability, read, payload

    # And a chart that found a span to shade. The table's bars are a straight line, so they
    # produce no power-play span and therefore no chart questions -- and the claim the question
    # keys are hashed under is read only when there is a question to key. A chart drawn over a
    # real advance is the ordinary case, not an edge one, and it was the case nothing ran.
    frame = power_play_series()
    snapshot = ProviderSnapshot(
        frame,
        SnapshotMeta(
            provider="fixture-prices",
            retrieved_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            as_of=frame.index[-1].date(),
            coverage={"completed_only": True},
        ),
    )
    with tempfile.TemporaryDirectory() as temporary:
        with recording() as read:
            payload = execute(
                "ticker.chart",
                {
                    "ticker": _VOCABULARY.TICKER,
                    "as_of": frame.index[-1].date().isoformat(),
                    "output_dir": temporary,
                    "no_cache": True,
                },
                runtime=Runtime(price_history=lambda ticker, requested: snapshot),
            )
        yield "power_play", "ticker.chart", read, payload


def _market_defense_withheld(payload: Mapping[str, object]) -> bool:
    """The absence itself, not the verdict that produces it today.

    Written as `verdict == "INCOMPLETE"` the predicate described the branch rather than the
    reason, so a payload that published `management_evidence.market_defense` under an
    INCOMPLETE verdict would have been forgiven -- and forgiven by the liveness check too,
    which would count the departure as taken. What justifies the departure is that the reading
    reaches nobody, so that is what is asked.
    """

    evidence = ((payload.get("data") or {}).get("management_evidence")) or {}
    return "market_defense" not in evidence


# A read whose reading reaches no reader, declared one at a time with the reason, the way the
# quotation verifier declares its departures. The rule stays "read it, cite it"; what an entry
# here says is that this particular reading was built and then withheld whole, so citing it
# would tell a reader a standard governed an answer it had no part in.
#
# Each entry carries the condition under which that is true, not just the pair. Keyed by
# capability and claim alone, the departure declared below for an INCOMPLETE risk verdict also
# forgave the HOLD envelope, which publishes `management_evidence.market_defense` and does put
# that band in front of a reader -- so dropping its citation there would have been permanently
# excused by an exemption written for a different branch.
_WITHHELD = {
    ("ticker.risk", "management.market_defense_tightens_stops"): (
        _market_defense_withheld,
        "an INCOMPLETE verdict publishes no management readings at all -- `management_evidence` "
        "is emptied wholesale, which tests/260827/integration/test_windows_and_citations.py pins "
        "as 'nothing was established, so nothing is measured about it' -- so the block this band "
        "was evaluated for reaches nobody",
    ),
}


class EveryClaimReadIsCited(unittest.TestCase):
    def test_no_capability_reads_a_claim_its_envelope_does_not_name(self) -> None:
        uncited: list[str] = []
        for label, capability, read, payload in _envelopes():
            cited = set(payload.get("doctrine_ids") or [])
            for claim_id in sorted(set(read) - cited):
                declared = _WITHHELD.get((capability, claim_id))
                if declared is not None and declared[0](payload):
                    continue
                uncited.append(f"{capability} ({label}, status={payload.get('status')}) read {claim_id}")
        self.assertEqual(uncited, [], "claims read and never cited:\n" + "\n".join(uncited))

    def test_a_departure_does_not_reach_the_branch_that_publishes_the_reading(self) -> None:
        """The same capability, the same claim, the other verdict.

        `ticker.risk` under HOLD publishes `management_evidence.market_defense`, so the band is
        in front of a reader and its claim has to be cited. This is the case an exemption keyed
        by capability and claim alone would have forgiven for good.
        """

        holds = [
            payload
            for _, capability, _, payload in _envelopes()
            if capability == "ticker.risk" and (payload.get("data") or {}).get("verdict") == "HOLD"
        ]
        self.assertTrue(holds, "the sweep produced no HOLD risk envelope, so this proves nothing")
        for payload in holds:
            self.assertFalse(_market_defense_withheld(payload))
            self.assertIn("market_defense", payload["data"]["management_evidence"])
            self.assertIn("management.market_defense_tightens_stops", payload["doctrine_ids"])

    def test_every_declared_departure_is_still_one(self) -> None:
        """A departure nobody takes any more is a sentence that reads as permission and grants
        none, and the next reader takes it for a rule. Each entry has to still be reachable."""

        taken = {
            (capability, claim_id)
            for _, capability, read, payload in _envelopes()
            for claim_id in set(read) - set(payload.get("doctrine_ids") or [])
            if (declared := _WITHHELD.get((capability, claim_id))) is not None and declared[0](payload)
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
        # Deduped, not counted: `claim` is `get_claim` plus the execution refusal, and both are
        # wrapped, so one reading of one claim arrives twice. What the comparison uses is the
        # set, and what this control is about is which ids are in it.
        self.assertEqual(set(read), {"convention.trading_week"})

    def test_an_import_bound_under_another_name_is_still_recorded(self) -> None:
        """Matching by name would miss `from .doctrine import claim as read_the_claim`, and the
        binding that motivated this was itself a direct import -- the next one need not keep
        the accessor's name for the recorder to have to see it."""

        module = types.ModuleType("scripts.minervini._alias_probe")
        module.read_the_claim = doctrine.claim
        sys.modules[module.__name__] = module
        try:
            with recording() as read:
                module.read_the_claim("convention.trading_week")
            self.assertEqual(set(read), {"convention.trading_week"})
            self.assertIs(module.read_the_claim, doctrine.claim)
        finally:
            del sys.modules[module.__name__]

    def test_the_recorder_puts_the_registry_back(self) -> None:
        before = {name: getattr(doctrine, name) for name in _READS}
        with recording():
            self.assertIsNot(doctrine.claim, before["claim"])
        self.assertEqual({name: getattr(doctrine, name) for name in _READS}, before)


if __name__ == "__main__":
    unittest.main()
