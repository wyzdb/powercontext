"""Build the specification / code / test index for a business project.

Everything here is deterministic and dependency-free: Markdown front matter,
``ast`` for Python symbols and tests, and a shared tokenizer for the inverted
index. Re-running the indexer on unchanged sources produces identical rows.
"""

from __future__ import annotations

import ast
from pathlib import Path

from sdd_context.models import CodeSymbol, IndexBundle, TermRow, TestItem
from sdd_context.spec_parser import SpecClause, SpecDocument, parse_spec_file
from sdd_context.tokenizer import tokenize

_ANNOTATION_PREFIXES = ("spec", "covers")


def module_name(path: Path, source_root: Path) -> str:
    relative = path.relative_to(source_root).with_suffix("")
    parts = list(relative.parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _signature(node: ast.AST) -> str:
    name = getattr(node, "name", "?")
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        arguments = ast.unparse(node.args)
        return f"{name}({arguments})"
    if isinstance(node, ast.ClassDef):
        bases = ", ".join(ast.unparse(base) for base in node.bases)
        return f"class {name}({bases})" if bases else f"class {name}"
    return name


def _collect_symbols(tree: ast.Module, module: str, path: str) -> list[CodeSymbol]:
    symbols: list[CodeSymbol] = []

    def add(node: ast.AST, kind: str, qualified: str) -> None:
        symbols.append(
            CodeSymbol(
                symbol_id=qualified,
                path=path,
                qualified_name=qualified,
                kind=kind,
                line_start=node.lineno,  # type: ignore[attr-defined]
                line_end=node.end_lineno,  # type: ignore[attr-defined]
                signature=_signature(node),
                doc=ast.get_docstring(node) or "",  # type: ignore[arg-type]
            )
        )

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            add(node, "function", f"{module}.{node.name}")
        elif isinstance(node, ast.ClassDef):
            add(node, "class", f"{module}.{node.name}")
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    add(child, "method", f"{module}.{node.name}.{child.name}")
    return symbols


def parse_source_file(path: Path, source_root: Path, relative_path: str) -> list[CodeSymbol]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return _collect_symbols(tree, module_name(path, source_root), relative_path)


def _annotations_above(lines: list[str], lineno: int) -> dict[str, tuple[str, ...]]:
    """Read ``# spec:`` / ``# covers:`` comments directly above a definition."""

    found: dict[str, list[str]] = {}
    index = lineno - 2  # zero-based index of the line before the definition
    lookback = 0
    while index >= 0 and lookback < 4:
        line = lines[index].strip()
        if line.startswith("#"):
            body = line.lstrip("#").strip()
            key, separator, value = body.partition(":")
            if separator and key.strip() in _ANNOTATION_PREFIXES:
                refs = [item.strip() for item in value.split(",") if item.strip()]
                found.setdefault(key.strip(), []).extend(refs)
            index -= 1
            lookback += 1
            continue
        if not line:
            index -= 1
            lookback += 1
            continue
        break
    return {key: tuple(dict.fromkeys(value)) for key, value in found.items()}


def parse_test_file(
    path: Path,
    relative_path: str,
    spec_status: dict[str, str],
    spec_verified_by: dict[str, str],
) -> list[TestItem]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    tree = ast.parse(text, filename=str(path))
    items: list[TestItem] = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test_"):
            continue
        annotations = _annotations_above(lines, node.lineno)
        spec_refs = annotations.get("spec", ())
        code_refs = annotations.get("covers", ())
        if not spec_refs:
            fallback = spec_verified_by.get(relative_path)
            if fallback:
                spec_refs = (fallback,)
        statuses = {spec_status.get(ref.split("/")[0], "active") for ref in spec_refs}
        kind = "target" if "proposed" in statuses else "regression"
        items.append(
            TestItem(
                test_id=f"{relative_path}::{node.name}",
                path=relative_path,
                name=node.name,
                kind=kind,
                spec_refs=tuple(spec_refs),
                code_refs=tuple(code_refs),
                line_start=node.lineno,
                line_end=node.end_lineno or node.lineno,
                doc=ast.get_docstring(node) or "",
            )
        )
    return items


def _terms_for(weighted_fields: list[tuple[str, int]], ref_kind: str, ref_id: str) -> list[TermRow]:
    best: dict[str, int] = {}
    for text, weight in weighted_fields:
        for term in tokenize(text):
            if best.get(term, 0) < weight:
                best[term] = weight
    return [
        TermRow(term=term, ref_kind=ref_kind, ref_id=ref_id, weight=weight)
        for term, weight in sorted(best.items())
    ]


def build_index(business_root: Path) -> IndexBundle:
    business_root = business_root.resolve()
    spec_dir = business_root / "specs"
    source_root = business_root / "src"
    test_dir = business_root / "tests"

    specs: list[SpecDocument] = []
    for path in sorted(spec_dir.glob("SPEC-*.md")):
        specs.append(parse_spec_file(path, business_root))

    clauses: list[SpecClause] = [clause for spec in specs for clause in spec.clauses]
    spec_status = {spec.spec_id: spec.status for spec in specs}
    spec_verified_by = {
        filename: spec.spec_id for spec in specs for filename in spec.verified_by
    }

    symbols: list[CodeSymbol] = []
    for path in sorted(source_root.rglob("*.py")):
        relative = path.relative_to(business_root).as_posix()
        symbols.extend(parse_source_file(path, source_root, relative))

    tests: list[TestItem] = []
    for path in sorted(test_dir.glob("test_*.py")):
        relative = path.relative_to(business_root).as_posix()
        tests.extend(parse_test_file(path, relative, spec_status, spec_verified_by))

    terms: list[TermRow] = []
    for clause in clauses:
        terms.extend(
            _terms_for(
                [
                    (clause.heading, 4),
                    (clause.body, 1),
                    (clause.spec_id, 3),
                    (clause.clause_id, 3),
                    (" ".join(clause.applies_to), 2),
                ],
                "spec",
                clause.clause_id,
            )
        )
    for symbol in symbols:
        terms.extend(
            _terms_for(
                [
                    (symbol.qualified_name, 3),
                    (symbol.signature, 2),
                    (symbol.doc, 1),
                    (symbol.path, 1),
                ],
                "code",
                symbol.symbol_id,
            )
        )
    for test in tests:
        terms.extend(
            _terms_for(
                [
                    (test.name, 3),
                    (test.doc, 2),
                    (" ".join(test.spec_refs), 2),
                    (" ".join(test.code_refs), 2),
                    (test.path, 1),
                ],
                "test",
                test.test_id,
            )
        )

    deduped: dict[tuple[str, str, str], TermRow] = {}
    for row in terms:
        key = (row.term, row.ref_kind, row.ref_id)
        if key not in deduped or deduped[key].weight < row.weight:
            deduped[key] = row

    return IndexBundle(
        specs=tuple(specs),
        clauses=tuple(clauses),
        symbols=tuple(symbols),
        tests=tuple(tests),
        terms=tuple(deduped[key] for key in sorted(deduped)),
    )
