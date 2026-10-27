"""Strict unified-diff parsing and application.

The patch is applied to the working tree, not through ``git apply``: the demo
project is not a git repository of its own, and a strict in-process applier
gives a clear failure when the model's context lines do not match the sources
it was given.
"""

from __future__ import annotations

import difflib
import hashlib
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

_HUNK_HEADER = re.compile(
    r"^@@ -(?P<old_start>\d+)(?:,(?P<old_len>\d+))? \+(?P<new_start>\d+)(?:,(?P<new_len>\d+))? @@"
)


class PatchError(RuntimeError):
    """Raised when a patch is malformed or does not match the working tree."""


@dataclass(frozen=True)
class Hunk:
    old_start: int
    old_len: int
    new_start: int
    new_len: int
    lines: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class FilePatch:
    path: str
    hunks: tuple[Hunk, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class FileChange:
    path: str
    added: int
    removed: int
    before_sha: str
    after_sha: str


def _strip_prefix(path: str) -> str:
    cleaned = path.strip().strip('"')
    for prefix in ("a/", "b/", "./"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :]
    return cleaned


def parse_patch(text: str) -> tuple[FilePatch, ...]:
    """Parse a unified diff into file patches and hunks."""

    lines = text.splitlines()
    patches: list[FilePatch] = []
    index = 0
    current_path: str | None = None
    current_hunks: list[Hunk] = []
    pending_old: str | None = None

    while index < len(lines):
        line = lines[index]
        if line.startswith("--- "):
            pending_old = _strip_prefix(line[4:])
            index += 1
            continue
        if line.startswith("+++ "):
            if current_path is not None:
                patches.append(FilePatch(current_path, tuple(current_hunks)))
            current_path = _strip_prefix(line[4:])
            current_hunks = []
            pending_old = None
            index += 1
            continue
        header = _HUNK_HEADER.match(line)
        if header:
            if current_path is None:
                raise PatchError("hunk appears before any '+++ ' file header")
            old_start = int(header.group("old_start"))
            old_len = int(header.group("old_len") or "1")
            new_start = int(header.group("new_start"))
            new_len = int(header.group("new_len") or "1")
            index += 1
            hunk_lines: list[tuple[str, str]] = []
            while index < len(lines) and not lines[index].startswith("@@ "):
                hunk_line = lines[index]
                if hunk_line.startswith("--- ") and hunk_lines:
                    break
                if not hunk_line:
                    # Some models drop the leading space on blank context lines.
                    hunk_lines.append((" ", ""))
                elif hunk_line[0] in " +-":
                    hunk_lines.append((hunk_line[0], hunk_line[1:]))
                elif hunk_line.startswith("\\"):
                    pass
                else:
                    raise PatchError(f"unexpected hunk line: {hunk_line!r}")
                index += 1
            current_hunks.append(Hunk(old_start, old_len, new_start, new_len, tuple(hunk_lines)))
            continue
        index += 1

    if pending_old is not None and current_path is None:
        raise PatchError("'--- ' header without a matching '+++ ' header")
    if current_path is not None:
        patches.append(FilePatch(current_path, tuple(current_hunks)))
    if not patches:
        raise PatchError("patch contains no file sections")
    return tuple(patches)


def _matches(original: str, expected: str) -> bool:
    return original.rstrip() == expected.rstrip()


def _hunk_matches(lines: list[str], hunk: Hunk, candidate: int) -> bool:
    """True when every context/removal line matches starting at ``candidate``."""

    position = candidate
    for tag, text in hunk.lines:
        if tag in (" ", "-"):
            if position >= len(lines) or not _matches(lines[position], text):
                return False
            position += 1
    return True


def _locate(lines: list[str], hunk: Hunk, expected: int, floor: int, window: int = 80) -> int | None:
    """Find the hunk position, tolerating line-number drift from the model.

    Models often miscount the line numbers in ``@@`` headers even when the
    context lines themselves are copied exactly. Prefer the declared position,
    then search outwards, which is what ``patch`` does with its fuzz factor.
    """

    if expected >= floor and _hunk_matches(lines, hunk, expected):
        return expected
    for offset in range(1, window + 1):
        for candidate in (expected - offset, expected + offset):
            if candidate < floor or candidate > len(lines):
                continue
            if _hunk_matches(lines, hunk, candidate):
                return candidate
    if floor <= len(lines) and _hunk_matches(lines, hunk, floor):
        return floor
    return None


def apply_patch(patch_text: str, root: Path, *, dry_run: bool = False) -> list[FileChange]:
    """Apply ``patch_text`` under ``root`` and return the touched files."""

    root = root.resolve()
    changes: list[FileChange] = []
    for file_patch in parse_patch(patch_text):
        relative = file_patch.path
        target = (root / relative).resolve()
        if root not in target.parents and target != root:
            raise PatchError(f"patch escapes the project root: {relative}")
        if not target.is_file():
            raise PatchError(f"patched file does not exist: {relative}")

        original_text = target.read_text(encoding="utf-8")
        original_lines = original_text.splitlines()
        before_sha = hashlib.sha256(original_text.encode("utf-8")).hexdigest()
        output: list[str] = []
        cursor = 0
        added = 0
        removed = 0

        for hunk in file_patch.hunks:
            start = hunk.old_start - 1 if hunk.old_start > 0 else 0
            if start < cursor:
                start = cursor
            position = _locate(original_lines, hunk, start, cursor)
            if position is None:
                raise PatchError(
                    f"{relative}: no matching context near line {hunk.old_start}"
                )
            output.extend(original_lines[cursor:position])
            cursor = position
            for tag, line in hunk.lines:
                if tag == " ":
                    if position >= len(original_lines) or not _matches(
                        original_lines[position], line
                    ):
                        raise PatchError(
                            f"{relative}: context mismatch at line {position + 1}"
                        )
                    output.append(original_lines[position])
                    position += 1
                elif tag == "-":
                    if position >= len(original_lines) or not _matches(
                        original_lines[position], line
                    ):
                        raise PatchError(
                            f"{relative}: removal mismatch at line {position + 1}"
                        )
                    position += 1
                    removed += 1
                elif tag == "+":
                    output.append(line)
                    added += 1
            cursor = position

        output.extend(original_lines[cursor:])
        new_text = "\n".join(output)
        if original_text.endswith("\n"):
            new_text += "\n"
        after_sha = hashlib.sha256(new_text.encode("utf-8")).hexdigest()
        if not dry_run:
            # Write LF explicitly so snapshot hashes match the bytes recorded
            # in the run log regardless of the host platform.
            target.write_text(new_text, encoding="utf-8", newline="\n")
        changes.append(
            FileChange(
                path=relative,
                added=added,
                removed=removed,
                before_sha=before_sha,
                after_sha=after_sha,
            )
        )
    return changes


def snapshot_sources(business_root: Path, destination: Path) -> list[Path]:
    """Copy ``src`` and ``tests`` trees into ``destination`` for review."""

    destination.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name in ("src", "tests", "specs"):
        source = business_root / name
        if not source.is_dir():
            continue
        for path in sorted(source.rglob("*")):
            if path.is_dir() or "__pycache__" in path.parts:
                continue
            relative = path.relative_to(business_root)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            written.append(relative)
    return written


def unified_diff(before_root: Path, after_root: Path, relative_paths: list[str]) -> str:
    """Render a review diff between two snapshot trees."""

    chunks: list[str] = []
    for relative in relative_paths:
        before = (before_root / relative).read_text(encoding="utf-8").splitlines(keepends=True)
        after = (after_root / relative).read_text(encoding="utf-8").splitlines(keepends=True)
        diff = difflib.unified_diff(
            before,
            after,
            fromfile=f"a/{relative}",
            tofile=f"b/{relative}",
            n=3,
        )
        chunks.extend(diff)
    return "".join(chunks)
