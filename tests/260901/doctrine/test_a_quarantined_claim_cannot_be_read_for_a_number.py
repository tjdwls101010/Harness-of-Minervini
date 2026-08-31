"""Quarantine has to refuse at the seam, the way out_of_scope already does.

`_readable` turned away a claim recorded out_of_scope (decision 12) and said nothing about
a quarantined one, so "a quarantined claim never executes" lived in one sentence of the
constitution and nowhere in the code. A sentence is the layer that fails quietly: a reducer
author reads the registry, finds a threshold, and reads it -- the registry never objects,
and the resulting verdict cites a claim this harness had already set aside.

Nothing is quarantined today, which is exactly when the guard is cheap to install and
impossible to notice missing. These tests quarantine live claims in a copied registry.
"""

from __future__ import annotations

import contextlib
import copy
import json
import pathlib
import unittest

from scripts.minervini import doctrine


REGISTRY = pathlib.Path(__file__).resolve().parents[3] / "doctrine" / "claims.json"

GATE = ("eligibility.standard_trend_template", "sma_200_rising_minimum_months")
BAND = ("eligibility.recent_ipo_primary_base", "three_to_five_week_base_depth_pct")
MARKER = ("eligibility.ipo_youthfulness_10yr_window", "typical_max_years_since_ipo")
PARAMETER = ("setup.swing_segmentation_convention", "retracement_range_multiple")


@contextlib.contextmanager
def quarantined(*claim_ids: str):
    """Set the named claims aside, as a reviewer would when a source stops supporting one."""

    edited = copy.deepcopy(json.loads(REGISTRY.read_text(encoding="utf-8")))
    for claim_id in claim_ids:
        record = next(item for item in edited["claims"] if item["id"] == claim_id)
        record["quarantine"] = {"is_quarantined": True, "reason": "set aside pending re-sourcing"}
        record["status"] = "quarantine"
    loader = doctrine._load_registry
    doctrine._load_registry = lambda: edited
    try:
        yield
    finally:
        doctrine._load_registry = loader


class NoNumberComesOutOfAQuarantinedClaim(unittest.TestCase):
    def test_a_raw_threshold_is_refused(self) -> None:
        with quarantined(GATE[0]):
            with self.assertRaises(ValueError) as raised:
                doctrine.threshold(*GATE)

        self.assertIn("quarantine", str(raised.exception).casefold())

    def test_every_evaluator_is_refused_the_same_way(self) -> None:
        with quarantined(GATE[0], BAND[0], MARKER[0]):
            for call in (
                lambda: doctrine.evaluate_gate(*GATE, 8.0),
                lambda: doctrine.evaluate_band(*BAND, 20.0),
                lambda: doctrine.evaluate_marker(*MARKER, 12.0),
            ):
                with self.assertRaises(ValueError):
                    call()

    def test_an_algorithm_parameter_is_refused_too(self) -> None:
        """A parameter chooses which measurement exists, so reading one is still executing."""

        with quarantined(PARAMETER[0]):
            with self.assertRaises(ValueError):
                doctrine.parameter(*PARAMETER)


class QuarantineWithdrawsTheNumbersAndNotTheRecord(unittest.TestCase):
    """It is audit material. A reader must still be able to see what was set aside and why."""

    def test_the_claim_is_still_retrievable_for_audit(self) -> None:
        with quarantined(GATE[0]):
            record = doctrine.get_claim(GATE[0])

        self.assertTrue(record["claim"]["quarantine"]["is_quarantined"])
        self.assertEqual(record["claim"]["quarantine"]["reason"], "set aside pending re-sourcing")

    def test_it_leaves_the_runtime_listing(self) -> None:
        with quarantined(GATE[0]):
            runtime = {record["claim"]["id"] for record in doctrine.list()}
            audited = {record["claim"]["id"] for record in doctrine.list(include_quarantined=True)}

        self.assertNotIn(GATE[0], runtime)
        self.assertIn(GATE[0], audited)


class TheRegistryRefusesToWireOneInTheFirstPlace(unittest.TestCase):
    """The seam is the last line. Validation is where the situation is refused outright.

    An out_of_scope record already has to declare `consumers: ["doctrine audit"]` (decision
    12), so a reviewer cannot leave one wired to a capability. Quarantine had no such rule,
    which meant a registry could set a claim aside and leave every consumer pointing at it
    -- valid, and refused only when some verdict reached for the number mid-run.
    """

    def test_a_quarantined_claim_that_still_names_a_runtime_consumer_is_invalid(self) -> None:
        edited = copy.deepcopy(json.loads(REGISTRY.read_text(encoding="utf-8")))
        record = next(item for item in edited["claims"] if item["id"] == GATE[0])
        record["quarantine"] = {"is_quarantined": True, "reason": "set aside pending re-sourcing"}
        record["status"] = "quarantine"

        result = doctrine.validate(edited)

        self.assertFalse(result["valid"])
        self.assertTrue(any("quarantine" in error and "consumer" in error for error in result["errors"]), result["errors"])

    def test_the_same_claim_set_aside_as_audit_material_validates(self) -> None:
        edited = copy.deepcopy(json.loads(REGISTRY.read_text(encoding="utf-8")))
        record = next(item for item in edited["claims"] if item["id"] == GATE[0])
        record["quarantine"] = {"is_quarantined": True, "reason": "set aside pending re-sourcing"}
        record["status"] = "quarantine"
        record["consumers"] = ["doctrine audit"]

        self.assertEqual([error for error in doctrine.validate(edited)["errors"] if "quarantine" in error], [])


class NoModuleReadsAThresholdAroundTheSeam(unittest.TestCase):
    """`_readable` only guards what goes through it, and one caller went around it.

    `threshold()` refuses a band on purpose, so that where a measurement sits travels with
    the number. Reading `get_claim(...)["claim"]["thresholds"][name]["range"]` is that rule's
    end-run, and it skips the out_of_scope and quarantine refusals with it.
    """

    def test_no_runtime_module_indexes_thresholds_or_parameters_directly(self) -> None:
        source = pathlib.Path(__file__).resolve().parents[3] / "scripts" / "minervini"
        offenders = [
            f"{path.relative_to(source.parent.parent)}:{number}"
            for path in sorted(source.rglob("*.py"))
            if path.name != "doctrine.py"
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
            if '["thresholds"]' in line or '["parameters"]' in line
        ]

        self.assertEqual(offenders, [])


class AnActiveClaimIsUntouched(unittest.TestCase):
    def test_the_same_seams_still_answer_for_a_claim_nobody_set_aside(self) -> None:
        with quarantined(BAND[0]):
            self.assertEqual(doctrine.threshold(*GATE), 1)
            self.assertEqual(doctrine.evaluate_marker(*MARKER, 12.0)["measured"], 12.0)


if __name__ == "__main__":
    unittest.main()
