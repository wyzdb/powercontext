"""Index records shared by the store, the selection logic and the CLI."""

from __future__ import annotations

from dataclasses import dataclass, field

from sdd_context.spec_parser import SpecClause, SpecDocument


@dataclass(frozen=True)
class CodeSymbol:
    symbol_id: str
    path: str
    qualified_name: str
    kind: str
    line_start: int
    line_end: int
    signature: str
    doc: str


@dataclass(frozen=True)
class TestItem:
    test_id: str
    path: str
    name: str
    kind: str  # "target" or "regression"
    spec_refs: tuple[str, ...]
    code_refs: tuple[str, ...]
    line_start: int
    line_end: int
    doc: str


@dataclass(frozen=True)
class TermRow:
    term: str
    ref_kind: str  # "spec" | "code" | "test"
    ref_id: str
    weight: int


@dataclass(frozen=True)
class IndexBundle:
    specs: tuple[SpecDocument, ...] = field(default_factory=tuple)
    clauses: tuple[SpecClause, ...] = field(default_factory=tuple)
    symbols: tuple[CodeSymbol, ...] = field(default_factory=tuple)
    tests: tuple[TestItem, ...] = field(default_factory=tuple)
    terms: tuple[TermRow, ...] = field(default_factory=tuple)

    def stats(self) -> dict[str, int]:
        return {
            "specs": len(self.specs),
            "clauses": len(self.clauses),
            "symbols": len(self.symbols),
            "tests": len(self.tests),
            "terms": len(self.terms),
        }


@dataclass(frozen=True)
class Match:
    ref_kind: str
    ref_id: str
    score: int
    hits: int


@dataclass
class TaskState:
    """Task progress persisted through PowerContext."""

    task_id: str
    title: str
    status: str
    step: str
    done: list[str] = field(default_factory=list)
    todo: list[str] = field(default_factory=list)
    verifications: list[dict[str, object]] = field(default_factory=list)
    context_id: str | None = None
    updated_at: str = ""
    revision: int = 0

    def to_mapping(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "status": self.status,
            "step": self.step,
            "done": list(self.done),
            "todo": list(self.todo),
            "verifications": list(self.verifications),
            "context_id": self.context_id,
            "updated_at": self.updated_at,
            "revision": self.revision,
        }

    @classmethod
    def from_mapping(cls, raw: dict[str, object]) -> "TaskState":
        return cls(
            task_id=str(raw["task_id"]),
            title=str(raw.get("title", "")),
            status=str(raw.get("status", "unknown")),
            step=str(raw.get("step", "")),
            done=[str(item) for item in raw.get("done", [])],  # type: ignore[union-attr]
            todo=[str(item) for item in raw.get("todo", [])],  # type: ignore[union-attr]
            verifications=list(raw.get("verifications", [])),  # type: ignore[arg-type]
            context_id=(str(raw["context_id"]) if raw.get("context_id") else None),
            updated_at=str(raw.get("updated_at", "")),
            revision=int(raw.get("revision", 0)),  # type: ignore[arg-type]
        )
