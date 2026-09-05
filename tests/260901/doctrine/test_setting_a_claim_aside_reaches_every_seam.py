"""Refusing the numbers was not enough, and the numbers were not the only way in.

An adversarial round against the first cut of this guard found seven ways a set-aside claim
still executed. None of them read a threshold: a claim's binding authority, its required
inputs, its kind and its stated rule all reach a reducer whole, and a numberless observation
is published as somebody's binding standard on the strength of `binds()` alone.

So the boundary is not "no numbers" but "two accessors": `get_claim` answers for anything the
registry holds, because `doctrine.show` exists to show what was set aside; `claim` answers only
for records this harness may act on, and everything a verdict passes through asks that one.
"""

from __future__ import annotations

from tests.paths import REGISTRY, ROOT

import contextlib
import copy
import json
import unittest

from scripts.minervini import doctrine
from scripts.minervini.setup_evidence import _observation


RUNTIME = ROOT / "scripts" / "minervini"

GATE = "eligibility.standard_trend_template"
OBSERVED = "setup.demand_supply_volume_asymmetry"


@contextlib.contextmanager
def quarantined(*claim_ids: str, audit_only: bool = True):
    edited = copy.deepcopy(json.loads(REGISTRY.read_text(encoding="utf-8")))
    for claim_id in claim_ids:
        record = next(item for item in edited["claims"] if item["id"] == claim_id)
        record["quarantine"] = {"is_quarantined": True, "reason": "set aside pending re-sourcing"}
        record["status"] = "quarantine"
        if audit_only:
            record["consumers"] = ["doctrine audit"]
    loader = doctrine._load_registry
    doctrine._load_registry = lambda: edited
    try:
        yield edited
    finally:
        doctrine._load_registry = loader


class TheSeamsThatCarryNoNumberAreRefusedToo(unittest.TestCase):
    def test_binding_authority_is_refused(self) -> None:
        with quarantined(OBSERVED):
            with self.assertRaises(ValueError):
                doctrine.binds(OBSERVED)

    def test_the_inputs_a_claim_asks_for_are_refused(self) -> None:
        with quarantined(OBSERVED):
            with self.assertRaises(ValueError):
                doctrine.required_inputs(OBSERVED)

    def test_a_numberless_observation_cannot_be_published_as_a_standard(self) -> None:
        """It reads binding authority and the rule prose, and never touches a threshold."""

        with quarantined(OBSERVED):
            with self.assertRaises(ValueError):
                _observation(OBSERVED, "pass", 1.4)

    def test_the_audit_accessor_still_answers_because_showing_it_is_the_point(self) -> None:
        with quarantined(OBSERVED):
            record = doctrine.get_claim(OBSERVED)

        self.assertTrue(record["claim"]["quarantine"]["is_quarantined"])


class TheRegistryRefusesTheContradictionsOutright(unittest.TestCase):
    def test_a_claim_a_reducer_must_read_cannot_be_set_aside(self) -> None:
        """Wired to no consumer and still named in the reducers' own threshold manifest."""

        with quarantined(GATE) as edited:
            result = doctrine.validate(edited)

        self.assertFalse(result["valid"])
        self.assertTrue(any(GATE in error and "reducer reads" in error for error in result["errors"]), result["errors"])

    def test_a_quarantine_status_without_the_flag_is_refused(self) -> None:
        edited = copy.deepcopy(json.loads(REGISTRY.read_text(encoding="utf-8")))
        next(item for item in edited["claims"] if item["id"] == GATE)["status"] = "quarantine"

        result = doctrine.validate(edited)

        self.assertFalse(result["valid"])
        self.assertTrue(any("quarantine" in error for error in result["errors"]), result["errors"])

    def test_a_record_set_aside_without_saying_why_is_refused(self) -> None:
        """`doctrine show` is the only place the withdrawal is explained; an empty reason explains nothing."""

        edited = copy.deepcopy(json.loads(REGISTRY.read_text(encoding="utf-8")))
        record = next(item for item in edited["claims"] if item["id"] == OBSERVED)
        record["quarantine"] = {"is_quarantined": True, "reason": None}
        record["status"] = "quarantine"
        record["consumers"] = ["doctrine audit"]

        result = doctrine.validate(edited)

        self.assertFalse(result["valid"])
        self.assertTrue(any("reason" in error for error in result["errors"]), result["errors"])


class OnlyTheAuditSurfaceUsesTheAuditAccessor(unittest.TestCase):
    """The guard is an accessor boundary, so what has to hold is who calls which one.

    A string search over source lines is a weak instrument for "does this read a number",
    which is what the first cut checked -- it missed a whole-claim serialization already in
    the tree and would have rejected an unrelated payload key. Naming one function is what
    makes the search sound: `get_claim` is one identifier, and its permitted callers are a
    list short enough to read.
    """

    PERMITTED = {"doctrine.py", "operations/discovery.py"}

    def test_no_reducer_reaches_past_the_guarded_accessor(self) -> None:
        offenders = [
            f"{path.relative_to(RUNTIME)}:{number}"
            for path in sorted(RUNTIME.rglob("*.py"))
            if path.relative_to(RUNTIME).as_posix() not in self.PERMITTED
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
            if "get_claim(" in line
        ]

        self.assertEqual(offenders, [])

    def test_the_whole_claim_digest_asks_the_guarded_accessor(self) -> None:
        """It serializes claims entire, thresholds included, into a key a reading depends on."""

        from scripts.minervini import power_play_evidence

        with quarantined(next(iter(power_play_evidence.ASKED_UNDER))):
            with self.assertRaises(ValueError):
                power_play_evidence._registry_digest()


if __name__ == "__main__":
    unittest.main()
