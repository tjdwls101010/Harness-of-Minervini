"""`consumers` is a promise about the interface, and nothing checked it against the interface.

`tests/260827/integration/test_doctrine_ids_follow_use.py` runs one direction: a capability
may cite only claims that registered it. Nothing ran the other way, so `ticker.setup` stood
in `consumers` on both base-count claims while the harness had no route to hand it a count --
no `base_count` field on the capability, no such flag on the CLI. A registry entry no
interface can honour reads to an auditor exactly like one that works.

What this proves is narrow, and the narrowness is the registry's rather than this test's.
`consumers` names which capability's analysis a claim is doctrine for, not which reducer
emits it: 65 of the 169 claims name a capability and appear in no module under
`scripts/minervini`, because a chart-assisted or qualitative claim is doctrine an analyst
reads off the envelope. So "registered but never cited" is the registry's ordinary state and
cannot be the check. What can be checked is the case where the claim is a measurement
compared against a standard and the measurement has to be handed in: a consumer that does
not declare the field can never receive it, whoever is doing the reading.

The vocabulary comes from the interface rather than from a list kept beside it. A
`required_input` that some capability declares as a field is one a caller supplies. Names no
capability declares -- `price_history`, `base_start_date`, `intraday_volume_so_far` -- are
read from a provider, derived from the bars, or simply not spelled the way any field is, and
this check says nothing about them either way.

Scoped to the kinds that measure. A `constitution` claim is cited as a restraint on what a
verdict may conclude, so `market.snapshot` naming the two practitioner claims about selling
on a stock's own stop is citing what it may *not* do -- its `required_inputs` describe the
decision being forbidden. A `tactic` claim's invalidation is disclosed by the capability
rather than supplied to it. Neither is a consumer that cannot reach its inputs.
"""

from __future__ import annotations

import collections
import json
import pathlib
import unittest

from scripts.minervini.capabilities import CAPABILITIES


from tests.paths import REGISTRY
# Kinds whose citation is a measurement compared against a standard. The other two -- a
# constitution's restraint and a tactic's disclosure -- name inputs the citer never receives.
MEASURED = {"interpretation", "default", "hard_gate", "exception"}


def claims() -> list[dict]:
    return json.loads(REGISTRY.read_text())["claims"]


def declared_fields() -> dict[str, set[str]]:
    fields: dict[str, set[str]] = collections.defaultdict(set)
    for capability_id, capability in CAPABILITIES.items():
        for name in capability.inputs or {}:
            fields[name].add(capability_id)
    return fields


class ARegisteredConsumerCanBeHandedWhatItCites(unittest.TestCase):
    def test_no_capability_is_registered_for_a_measurement_it_cannot_be_handed(self) -> None:
        fields = declared_fields()
        unreachable = set()
        for record in claims():
            if record["kind"] not in MEASURED:
                continue
            for consumer in record.get("consumers") or []:
                if consumer not in CAPABILITIES:
                    continue
                for required in record.get("required_inputs") or []:
                    if required in fields and consumer not in fields[required]:
                        unreachable.add((consumer, record["id"], required, tuple(sorted(fields[required]))))

        self.assertEqual(unreachable, set())

    def test_the_count_claims_name_only_the_capability_that_takes_a_count(self) -> None:
        """Decision 309 gave the count one home; the registry has to say the same thing."""

        registered = {record["id"]: record for record in claims()}
        for claim_id in ("basecount.role_and_disclaimer", "basecount.typical_top_after_3_to_5_bases"):
            with self.subTest(claim=claim_id):
                self.assertEqual(registered[claim_id]["consumers"], ["ticker.risk"])


if __name__ == "__main__":
    unittest.main()
