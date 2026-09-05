"""Every doctrine id the reducers cite must resolve to a registered claim.

`doctrine.has_claim`'s own words: "A citation nobody can look up is worse than no citation:
it reads as doctrine while leading a reader nowhere." Nothing enforced that. A capability can
name a `doctrine_id` the registry does not hold, and a reader following the citation finds
nothing -- during the Power Play work an unregistered claim was cited and not one of the
hundreds of runtime tests caught it, because no test exercised that envelope's citation list.

This walks the reducer source itself and resolves every statically-knowable claim-id citation
-- string literals and the module-level `_NAME = "claim.id"` constants they are usually written
as -- against the live registry. Citations built at runtime (`f"tactic.{tactic}"`) cannot be
resolved here and are left to the runtime tests that already exercise them; this test owns the
silent ones, the envelope lists and `evaluate_*` calls no scenario ever reads back.
"""

from __future__ import annotations

import ast
import importlib
import pathlib
import unittest

from scripts.minervini import doctrine


_MODULE_DIR = pathlib.Path(doctrine.__file__).parent

# The doctrine functions whose first positional argument is a claim id.
_CLAIM_FUNCS = {
    "has_claim",
    "get_claim",
    "required_inputs",
    "threshold",
    "parameter",
    "evaluate_gate",
    "evaluate_marker",
    "evaluate_band",
    "binds",
}


def _module_constants(tree: ast.Module) -> dict[str, str]:
    """Module-level `_NAME = "literal"` string assignments, the form a claim id is written in."""

    constants: dict[str, str] = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            constants[node.targets[0].id] = node.value.value
    return constants


def _is_doctrine_claim_call(func: ast.expr) -> bool:
    return (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id == "doctrine"
        and func.attr in _CLAIM_FUNCS
    )


def _cited_nodes(tree: ast.Module) -> list[ast.expr]:
    """Every AST node that sits where a claim id is expected.

    Three shapes carry one: the first argument of a `doctrine.<claim-fn>(...)` call, the value
    of a `doctrine_id` key or keyword, and each element of a `*doctrine_ids` list literal.
    """

    nodes: list[ast.expr] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if _is_doctrine_claim_call(node.func) and node.args:
                nodes.append(node.args[0])
            for keyword in node.keywords:
                if keyword.arg == "doctrine_id":
                    nodes.append(keyword.value)
                elif keyword.arg and keyword.arg.endswith("doctrine_ids") and isinstance(keyword.value, ast.List):
                    nodes.extend(keyword.value.elts)
        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                    continue
                if key.value == "doctrine_id":
                    nodes.append(value)
                elif key.value.endswith("doctrine_ids") and isinstance(value, ast.List):
                    nodes.extend(value.elts)
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.List):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.endswith("doctrine_ids"):
                    nodes.extend(node.value.elts)
    return nodes


def _resolve(node: ast.expr, constants: dict[str, str]) -> str | None:
    """The claim id this node names, or None when only runtime can know it."""

    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    return None


def _resolved_citations(source: str) -> list[str]:
    tree = ast.parse(source)
    constants = _module_constants(tree)
    resolved: list[str] = []
    for node in _cited_nodes(tree):
        claim_id = _resolve(node, constants)
        if claim_id is not None:
            resolved.append(claim_id)
    return resolved


class EveryCitedDoctrineIdResolves(unittest.TestCase):
    def test_no_reducer_cites_a_claim_the_registry_does_not_hold(self) -> None:
        dangling: list[str] = []
        total = 0
        for path in sorted(_MODULE_DIR.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            parts = path.relative_to(_MODULE_DIR).with_suffix("").parts
            if parts[-1] == "__init__":
                parts = parts[:-1]
            module = importlib.import_module(".".join(("scripts", "minervini", *parts)))
            # Imported string constants remain visible when a reducer moves into a package.
            constants = {name: value for name, value in vars(module).items() if isinstance(value, str)}
            for node in _cited_nodes(tree):
                claim_id = _resolve(node, constants)
                if claim_id is None:
                    continue
                total += 1
                if not doctrine.has_claim(claim_id):
                    dangling.append(f"{path.name}:{node.lineno} cites {claim_id!r}")

        self.assertEqual(dangling, [], f"citations resolve to no registered claim:\n" + "\n".join(dangling))
        # A walker that silently collects nothing would pass vacuously; there are ~191 direct
        # `doctrine.<fn>(...)` calls alone, so the real floor is far above this.
        self.assertGreaterEqual(total, 100, "the citation walker collected almost nothing -- it is broken, not clean")

    def test_the_walker_flags_a_dangling_citation_and_clears_a_real_one(self) -> None:
        """Positive control: the check is only worth trusting if it fails on a bad citation."""

        source = (
            '_GOOD = "market.correction_depth_healthy_leader"\n'
            '_BAD = "market.no_such_claim_exists"\n'
            'a = doctrine.evaluate_gate(_GOOD, "correction_failure_threshold", 1.0)\n'
            'b = {"doctrine_id": _BAD}\n'
        )
        resolved = _resolved_citations(source)

        self.assertIn("market.correction_depth_healthy_leader", resolved)
        self.assertIn("market.no_such_claim_exists", resolved)
        self.assertTrue(doctrine.has_claim("market.correction_depth_healthy_leader"))
        self.assertFalse(doctrine.has_claim("market.no_such_claim_exists"))


if __name__ == "__main__":
    unittest.main()
