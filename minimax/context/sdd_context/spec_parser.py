"""Parse specification documents into clause-level records.

A specification is a Markdown file with a small YAML front matter block and one
``## R<n>`` section per normative clause. Clause identity is stable:
``SPEC-ORD-004/R2`` names the second rule of SPEC-ORD-004, so context output and
test annotations cite the same identifier.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

_CLAUSE_HEADING = "## "


@dataclass(frozen=True)
class SpecDocument:
    spec_id: str
    title: str
    version: int
    status: str
    applies_to: tuple[str, ...]
    verified_by: tuple[str, ...]
    path: str
    clauses: tuple["SpecClause", ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SpecClause:
    clause_id: str
    spec_id: str
    spec_title: str
    version: int
    status: str
    ordinal: int
    heading: str
    body: str
    line_start: int
    line_end: int
    applies_to: tuple[str, ...]
    verified_by: tuple[str, ...]
    path: str = ""


def _parse_front_matter(lines: list[str]) -> tuple[dict[str, str], int]:
    if not lines or lines[0].strip() != "---":
        raise ValueError("specification must start with a '---' front matter block")
    values: dict[str, str] = {}
    for index in range(1, len(lines)):
        line = lines[index]
        if line.strip() == "---":
            return values, index + 1
        key, separator, raw = line.partition(":")
        if separator:
            values[key.strip()] = raw.strip()
    raise ValueError("front matter block is not closed with '---'")


def _parse_list(value: str) -> tuple[str, ...]:
    stripped = value.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        stripped = stripped[1:-1]
    return tuple(item.strip() for item in stripped.split(",") if item.strip())


def _split_clauses(lines: list[str], start: int) -> list[dict[str, object]]:
    """Group body lines into ``## R<n> heading`` sections with 1-based ranges."""

    clauses: list[dict[str, object]] = []
    current: dict[str, object] | None = None

    for index in range(start, len(lines)):
        line_number = index + 1
        line = lines[index]
        if line.startswith(_CLAUSE_HEADING):
            if current is not None:
                clauses.append(current)
                current = None
            heading = line[len(_CLAUSE_HEADING) :].strip()
            ordinal_text, _, title = heading.partition(" ")
            if not ordinal_text.startswith("R") or not ordinal_text[1:].isdigit():
                # A non-normative section (for example "## 版本历史") ends the
                # current clause and is not indexed.
                continue
            current = {
                "ordinal": int(ordinal_text[1:]),
                "heading": title.strip(),
                "body": [],
                "start": line_number,
                "last": line_number,
            }
            continue
        if current is None:
            continue
        body = current["body"]
        assert isinstance(body, list)
        body.append(line)
        if line.strip():
            current["last"] = line_number

    if current is not None:
        clauses.append(current)
    return clauses


def parse_spec_text(text: str, path: str = "<memory>") -> SpecDocument:
    lines = text.splitlines()
    front, body_start = _parse_front_matter(lines)

    spec_id = front.get("id", "").strip()
    if not spec_id:
        raise ValueError(f"{path}: front matter is missing 'id'")
    title = front.get("title", spec_id).strip()
    version = int(front.get("version", "1"))
    status = front.get("status", "active").strip()
    applies_to = _parse_list(front.get("applies_to", ""))
    verified_by = _parse_list(front.get("verified_by", ""))

    clauses = tuple(
        SpecClause(
            clause_id=f"{spec_id}/R{raw['ordinal']}",
            spec_id=spec_id,
            spec_title=title,
            version=version,
            status=status,
            ordinal=int(raw["ordinal"]),  # type: ignore[arg-type]
            heading=str(raw["heading"]),
            body="\n".join(str(line) for line in raw["body"]).strip(),  # type: ignore[union-attr]
            line_start=int(raw["start"]),  # type: ignore[arg-type]
            line_end=int(raw["last"]),  # type: ignore[arg-type]
            applies_to=applies_to,
            verified_by=verified_by,
            path=path,
        )
        for raw in _split_clauses(lines, body_start)
    )
    return SpecDocument(
        spec_id=spec_id,
        title=title,
        version=version,
        status=status,
        applies_to=applies_to,
        verified_by=verified_by,
        path=path,
        clauses=clauses,
    )


def parse_spec_file(path: Path, business_root: Path | None = None) -> SpecDocument:
    relative = (
        path.relative_to(business_root).as_posix() if business_root is not None else path.name
    )
    return parse_spec_text(path.read_text(encoding="utf-8"), path=relative)
