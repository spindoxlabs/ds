"""Collect, from the test sources, every declaration that a test covers a rule.

Five layers, four syntaxes, one meaning. A test says which rulebook rule it is
evidence for, and the marker lives **on the test** rather than in the rulebook
page — so it moves with a rename, disappears with a deletion, and appears the
moment a new test is written. That is the whole reason the status column can be
derived instead of asserted.

| Layer | Where | How a test declares it |
|---|---|---|
| unit, integration | `services/*/tests`, `libs/*/tests` | `@pytest.mark.rule("A-11")` |
| java | `services/edc-extensions/src/test` | `@Tag("rule:A-11")` |
| e2e | `libs/ds-e2e/src/ds_e2e/flows` | `rules = ("D-17", "CR-5")` on the flow class |
| ui | `services/portal/tests/ui` | `@rule:C-3` in the test title |

`@Tag` and Playwright's title tags are both **existing** mechanisms of their
runners rather than inventions of this tool: `gradle test --tests` and
`playwright test --grep` can already select on them, so the marker is useful to
a person independently of this report. The pytest marker is registered in each
unit's `pyproject.toml`.

Parsing is static. See the note in `pyproject.toml` for what that buys and what
it costs.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from .model import Evidence, Layer, Problem

_JAVA_TAG = re.compile(r'@Tag\(\s*"rule:([A-Z]{1,2}-\d+[a-z]?)"\s*\)')
_JAVA_METHOD = re.compile(r"^\s*(?:public|private|protected)?\s*\w[\w<>\[\],\s]*\s+(\w+)\s*\(")
_JAVA_CLASS = re.compile(r"^\s*(?:public\s+)?(?:final\s+|abstract\s+)?class\s+(\w+)")
_TS_TAG = re.compile(r"@rule:([A-Z]{1,2}-\d+[a-z]?)")
_TS_TEST = re.compile(r"""^\s*(?:test|it)(?:\.\w+)*\(\s*(['"`])(.+?)\1""")

#: Directories that are never test sources, and are expensive to walk.
_SKIP_DIRS = frozenset(
    {
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".git",
        "build",
        ".gradle",
        "dist",
        "site",
        "data",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
    }
)


def _walk(root: Path, suffixes: tuple[str, ...]) -> list[Path]:
    found: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in suffixes:
            continue
        if _SKIP_DIRS & set(path.parts):
            continue
        found.append(path)
    return sorted(found)


def _unit_of(path: Path, repo: Path) -> str:
    """`services/connector`, `libs/governance` — the unit a file belongs to."""
    parts = path.relative_to(repo).parts
    if len(parts) >= 2 and parts[0] in ("services", "libs"):
        return f"{parts[0]}/{parts[1]}"
    return parts[0] if parts else "?"


# --------------------------------------------------------------------------
# Python — pytest markers
# --------------------------------------------------------------------------


def _rule_ids_from_decorator(node: ast.expr) -> list[str]:
    """Extract ids from `@pytest.mark.rule("A-1", "A-2")` and `@mark.rule(...)`.

    Accepts both dotted spellings because both are idiomatic and a collector
    that only understood one would report a real test as missing — which is a
    false negative in a tool whose entire value is not producing false answers.
    """
    if not isinstance(node, ast.Call):
        return []
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr != "rule":
        return []
    owner = func.value
    if isinstance(owner, ast.Attribute):
        if owner.attr != "mark":
            return []
    elif isinstance(owner, ast.Name):
        if owner.id != "mark":
            return []
    else:
        return []
    ids: list[str] = []
    for argument in node.args:
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
            ids.append(argument.value)
    return ids


def _module_level_rules(tree: ast.Module) -> list[str]:
    """`pytestmark = pytest.mark.rule("X")` — a whole module as evidence."""
    ids: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if "pytestmark" not in names:
            continue
        values = node.value.elts if isinstance(node.value, ast.List | ast.Tuple) else [node.value]
        for value in values:
            ids.extend(_rule_ids_from_decorator(value))
    return ids


def collect_python(repo: Path, roots: list[Path]) -> tuple[list[Evidence], list[Problem]]:
    evidence: list[Evidence] = []
    problems: list[Problem] = []

    for root in roots:
        if not root.exists():
            continue
        for path in _walk(root, (".py",)):
            name = path.name
            if not (name.startswith("test_") or name.endswith("_test.py")):
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except SyntaxError as error:
                problems.append(
                    Problem(
                        kind="unparseable-test-source",
                        subject=str(path.relative_to(repo)),
                        detail=f"could not be parsed, so its markers are invisible: {error}",
                        where=str(path.relative_to(repo)),
                    )
                )
                continue

            relative = str(path.relative_to(repo))
            unit = _unit_of(path, repo)
            # `tests/integration/` is the repo's own convention for the layer
            # that needs real dependencies — see `docs/development/testing.md`.
            layer = Layer.INTEGRATION if "integration" in path.parts else Layer.UNIT
            module_rules = _module_level_rules(tree)

            for rule_id in module_rules:
                evidence.append(
                    Evidence(
                        rule_id=rule_id,
                        layer=layer,
                        unit=unit,
                        node=f"{relative}::<module>",
                        file=relative,
                        line=1,
                    )
                )

            for node, class_name in _iter_test_functions(tree):
                inherited: list[str] = []
                if class_name:
                    inherited = _class_rules(tree, class_name)
                own: list[str] = []
                for decorator in node.decorator_list:
                    own.extend(_rule_ids_from_decorator(decorator))
                qualified = f"{class_name}::{node.name}" if class_name else node.name
                for rule_id in dict.fromkeys(own + inherited):
                    evidence.append(
                        Evidence(
                            rule_id=rule_id,
                            layer=layer,
                            unit=unit,
                            node=f"{relative}::{qualified}",
                            file=relative,
                            line=node.lineno,
                        )
                    )

    return evidence, problems


def _iter_test_functions(
    tree: ast.Module,
) -> list[tuple[ast.FunctionDef | ast.AsyncFunctionDef, str | None]]:
    found: list[tuple[ast.FunctionDef | ast.AsyncFunctionDef, str | None]] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            if node.name.startswith("test"):
                found.append((node, None))
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            for child in node.body:
                if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                    if child.name.startswith("test"):
                        found.append((child, node.name))
    return found


def _class_rules(tree: ast.Module, class_name: str) -> list[str]:
    """Markers on a test class apply to every test in it."""
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            ids: list[str] = []
            for decorator in node.decorator_list:
                ids.extend(_rule_ids_from_decorator(decorator))
            return ids
    return []


# --------------------------------------------------------------------------
# Java — JUnit @Tag("rule:…")
# --------------------------------------------------------------------------


def collect_java(repo: Path, roots: list[Path]) -> list[Evidence]:
    """Associate each `@Tag("rule:…")` with the method or class it annotates.

    Line-oriented rather than a Java parse, because the annotation always sits
    immediately above its target in this codebase and a real parser would be a
    dependency out of proportion to 116 test methods. A tag whose next
    declaration is a class is class-level and covers every test in the file.
    """
    evidence: list[Evidence] = []

    for root in roots:
        if not root.exists():
            continue
        for path in _walk(root, (".java",)):
            if not path.name.endswith("Test.java"):
                continue
            relative = str(path.relative_to(repo))
            unit = _unit_of(path, repo)
            lines = path.read_text(encoding="utf-8").splitlines()
            class_name = path.stem

            pending: list[tuple[str, int]] = []
            for number, line in enumerate(lines, 1):
                tags = _JAVA_TAG.findall(line)
                if tags:
                    pending.extend((tag, number) for tag in tags)
                    continue
                if not pending:
                    continue
                if _JAVA_CLASS.match(line):
                    for rule_id, tag_line in pending:
                        evidence.append(
                            Evidence(
                                rule_id=rule_id,
                                layer=Layer.JAVA,
                                unit=unit,
                                node=f"{class_name}",
                                file=relative,
                                line=tag_line,
                            )
                        )
                    pending = []
                    continue
                method = _JAVA_METHOD.match(line)
                if method and not line.strip().startswith("@"):
                    for rule_id, tag_line in pending:
                        evidence.append(
                            Evidence(
                                rule_id=rule_id,
                                layer=Layer.JAVA,
                                unit=unit,
                                node=f"{class_name}#{method.group(1)}",
                                file=relative,
                                line=tag_line,
                            )
                        )
                    pending = []

    return evidence


# --------------------------------------------------------------------------
# ds-e2e — `rules` on the flow class
# --------------------------------------------------------------------------


def collect_flows(repo: Path, flows_dir: Path) -> tuple[list[Evidence], list[Problem]]:
    """Read the `rules` class attribute off each e2e flow.

    A flow is one named journey rather than a collection of assertions, so the
    declaration belongs on the class. `ds-e2e` names its flows by `name`, which
    is what `task e2e:all` prints — so that is what the report cites, and a
    reader can run exactly the flow the evidence names.

    **A file that will not parse is reported, not skipped.** An earlier version
    swallowed the `SyntaxError` and returned nothing for that file, which read
    as "this flow evidences no rule" — indistinguishable from a flow that
    genuinely declares none. It hid thirteen broken files behind a plausible
    zero, which is precisely the green-because-it-did-not-run failure this tool
    exists to surface, reproduced inside the tool itself.
    """
    evidence: list[Evidence] = []
    problems: list[Problem] = []
    if not flows_dir.exists():
        return evidence, problems

    for path in _walk(flows_dir, (".py",)):
        if path.name.startswith("__"):
            continue
        relative = str(path.relative_to(repo))
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as error:
            problems.append(
                Problem(
                    kind="unparseable-flow-source",
                    subject=relative,
                    detail=f"could not be parsed, so its declared rules are invisible: {error}",
                    where=relative,
                )
            )
            continue
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            rules = _string_sequence_attribute(node, "rules")
            if not rules:
                continue
            flow_name = _string_attribute(node, "name") or node.name
            for rule_id in rules:
                evidence.append(
                    Evidence(
                        rule_id=rule_id,
                        layer=Layer.E2E,
                        unit="libs/ds-e2e",
                        node=flow_name,
                        file=relative,
                        line=node.lineno,
                    )
                )
    return evidence, problems


def _string_sequence_attribute(node: ast.ClassDef, attribute: str) -> list[str]:
    for child in node.body:
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(child, ast.Assign):
            targets, value = list(child.targets), child.value
        elif isinstance(child, ast.AnnAssign) and child.value is not None:
            targets, value = [child.target], child.value
        if not any(isinstance(t, ast.Name) and t.id == attribute for t in targets):
            continue
        if isinstance(value, ast.Tuple | ast.List):
            return [
                element.value
                for element in value.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            ]
    return []


def _string_attribute(node: ast.ClassDef, attribute: str) -> str | None:
    for child in node.body:
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(child, ast.Assign):
            targets, value = list(child.targets), child.value
        elif isinstance(child, ast.AnnAssign) and child.value is not None:
            targets, value = [child.target], child.value
        if not any(isinstance(t, ast.Name) and t.id == attribute for t in targets):
            continue
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return value.value
    return None


# --------------------------------------------------------------------------
# Playwright — a tag in the test title
# --------------------------------------------------------------------------


def collect_ui(repo: Path, ui_dir: Path) -> list[Evidence]:
    evidence: list[Evidence] = []
    if not ui_dir.exists():
        return evidence

    for path in _walk(ui_dir, (".ts",)):
        relative = str(path.relative_to(repo))
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            matched = _TS_TEST.match(line)
            if not matched:
                continue
            title = matched.group(2)
            for rule_id in _TS_TAG.findall(title):
                evidence.append(
                    Evidence(
                        rule_id=rule_id,
                        layer=Layer.UI,
                        unit="services/portal",
                        node=title,
                        file=relative,
                        line=number,
                    )
                )
    return evidence


#: This tool's own suite. Its fixtures contain marker syntax as *test data* —
#: a collector that counted them would report evidence for rules nothing
#: covers, which is the exact failure mode it exists to prevent.
SELF = "libs/ds-conformance"


def collect_all(repo: Path) -> tuple[list[Evidence], list[Problem]]:
    """Every marker in the tree, deduplicated and stably ordered."""
    evidence, problems = collect_python(repo, [repo / "services", repo / "libs"])
    evidence += collect_java(repo, [repo / "services"])
    flow_evidence, flow_problems = collect_flows(
        repo, repo / "libs" / "ds-e2e" / "src" / "ds_e2e" / "flows"
    )
    evidence += flow_evidence
    problems += flow_problems
    evidence += collect_ui(repo, repo / "services" / "portal" / "tests" / "ui")

    evidence = [e for e in evidence if not e.file.startswith(SELF)]
    problems = [p for p in problems if not p.subject.startswith(SELF)]

    unique = {(e.rule_id, e.layer, e.node, e.file, e.line): e for e in evidence}
    ordered = sorted(unique.values(), key=lambda e: (e.rule_id, e.layer.value, e.file, e.line))
    return ordered, problems
