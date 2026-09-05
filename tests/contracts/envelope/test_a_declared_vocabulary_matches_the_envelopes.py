"""A declaration nobody checks against the code is the drift it was written to stop.

The schema now refuses a `data` key nobody declared. That closes one direction and opens
another: a vocabulary is a second place the key list lives, and the failure mode of a second
place is that it stops agreeing with the first. Silently -- a declaration is prose to the
interpreter, and the envelope that no longer matches it is published anyway.

So the envelopes are read back against it. Every capability is run here, in both formats,
and validated against its own published schema. The `--format compact` half is not
redundant: the shared filter strips top-level keys by name -- `measurements` from a setup,
`quarterly` from a fundamentals reading -- so a key declared as core that compact removes
would make the harness's own compact output invalid against its own schema.

What this does not catch is a declared key no capability can emit, which leaves the schema
more permissive than it needs to be and refuses nothing real. The direction that costs
something is the other one, and it is the one measured here.
"""

from tests.harness import *


class EveryCapabilityDeclaresWhatItsDataHolds(unittest.TestCase):
    def test_no_capability_leaves_its_data_field_open(self) -> None:
        """An empty declaration bakes no constraint, so it is the old `data: {}` by another name."""

        undeclared = sorted(name for name, capability in CAPABILITIES.items() if not capability.data_keys)

        self.assertEqual(undeclared, [])

    def test_every_core_key_is_in_the_vocabulary_that_admits_it(self) -> None:
        for name, capability in CAPABILITIES.items():
            with self.subTest(capability=name):
                self.assertLessEqual(capability.data_core, capability.data_keys)

    def test_every_capability_is_asked_for_an_envelope_here(self) -> None:
        """A capability missing from the table is one this sweep silently never validates."""

        self.assertEqual(set(REQUESTS), set(CAPABILITIES))


class AnEnvelopeValidatesAgainstItsOwnPublishedSchema(unittest.TestCase):
    def envelopes(self) -> list[tuple[str, str, str, dict]]:
        produced: list[tuple[str, str, str, dict]] = []
        for label, build in (("withholding", withholding), ("measured", measured)):
            with tempfile.TemporaryDirectory() as temporary:
                ledger = pathlib.Path(temporary) / "ledger.sqlite3"
                runtime = build(ledger)
                for capability, request in REQUESTS.items():
                    # The export destination is a caller-selected path, so it lives with the ledger.
                    payload = execute(capability, {**request, **({"output": str(pathlib.Path(temporary) / "export.csv")} if capability == "watchlist.export" else {})}, runtime=runtime)
                    for mode in ("full", "compact"):
                        produced.append((capability, label, mode, format_payload(payload, mode)))
        for capability, label, request in EXTRA_CASES:
            payload = execute(capability, request, runtime={"filed": filed, "current": current, "listed": listed}.get(label, sealed)())
            for mode in ("full", "compact"):
                produced.append((capability, label, mode, format_payload(payload, mode)))
        return produced

    def test_every_envelope_this_harness_builds_satisfies_its_declaration(self) -> None:
        for capability, label, mode, payload in self.envelopes():
            with self.subTest(capability=capability, providers=label, format=mode):
                validator(capability).validate(payload)


if __name__ == "__main__":
    unittest.main()
