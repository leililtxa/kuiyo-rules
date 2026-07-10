from __future__ import annotations

import ast
from pathlib import Path

import kuiyo_rules


FORBIDDEN_IMPORTS = {
    "kuiyo_data_access",
    "kuiyo_jobs",
    "kuiyo_market_research",
    "psycopg",
}


def test_package_imports_from_public_root() -> None:
    assert kuiyo_rules.__doc__ == "Pure rule contracts and deterministic evaluators for Kuiyo."


def test_source_does_not_import_forbidden_projects_or_database_driver() -> None:
    source_root = Path(__file__).parents[1] / "src" / "kuiyo_rules"
    violations: list[str] = []

    for path in sorted(source_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            for imported in imported_modules(node):
                if imported.split(".", 1)[0] in FORBIDDEN_IMPORTS:
                    violations.append(f"{path.relative_to(source_root)}: {imported}")

    assert violations == []


def imported_modules(node: ast.AST) -> tuple[str, ...]:
    if isinstance(node, ast.Import):
        return tuple(alias.name for alias in node.names)
    if isinstance(node, ast.ImportFrom):
        return () if node.module is None else (node.module,)
    return ()
