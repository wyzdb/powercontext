"""Unified-diff application, including model line-number drift."""

from __future__ import annotations

from pathlib import Path

import pytest

from sdd_context.patcher import PatchError, apply_patch


def _project(base: Path, text: str) -> Path:
    source = base / "src"
    source.mkdir(parents=True, exist_ok=True)
    (source / "mod.py").write_text(text, encoding="utf-8")
    return base


def test_exact_patch_is_applied(project_dir: Path) -> None:
    root = _project(project_dir, "alpha\nbeta\ngamma\n")
    patch = (
        "--- a/src/mod.py\n"
        "+++ b/src/mod.py\n"
        "@@ -1,3 +1,3 @@\n"
        " alpha\n"
        "-beta\n"
        "+BETA\n"
        " gamma\n"
    )
    changes = apply_patch(patch, root)
    assert (root / "src" / "mod.py").read_text(encoding="utf-8") == "alpha\nBETA\ngamma\n"
    assert changes[0].added == 1
    assert changes[0].removed == 1


def test_hunk_line_drift_is_tolerated(project_dir: Path) -> None:
    root = _project(project_dir, "alpha\nbeta\ngamma\ndelta\n")
    # The header claims line 9 although the context actually starts at line 2.
    patch = (
        "--- a/src/mod.py\n"
        "+++ b/src/mod.py\n"
        "@@ -9,3 +9,4 @@\n"
        " beta\n"
        " gamma\n"
        "+inserted\n"
        " delta\n"
    )
    apply_patch(patch, root)
    assert (root / "src" / "mod.py").read_text(encoding="utf-8") == (
        "alpha\nbeta\ngamma\ninserted\ndelta\n"
    )


def test_mismatched_context_is_rejected(project_dir: Path) -> None:
    root = _project(project_dir, "alpha\nbeta\ngamma\n")
    patch = (
        "--- a/src/mod.py\n"
        "+++ b/src/mod.py\n"
        "@@ -1,2 +1,2 @@\n"
        " alpha\n"
        "-omega\n"
        "+OMEGA\n"
    )
    with pytest.raises(PatchError):
        apply_patch(patch, root)
    assert "beta" in (root / "src" / "mod.py").read_text(encoding="utf-8")


def test_dry_run_does_not_write(project_dir: Path) -> None:
    root = _project(project_dir, "alpha\n")
    patch = "--- a/src/mod.py\n+++ b/src/mod.py\n@@ -1 +1,2 @@\n alpha\n+beta\n"
    apply_patch(patch, root, dry_run=True)
    assert (root / "src" / "mod.py").read_text(encoding="utf-8") == "alpha\n"


def test_escape_from_project_root_is_rejected(project_dir: Path) -> None:
    root = _project(project_dir, "x\n")
    (project_dir / "outside.py").write_text("x\n", encoding="utf-8")
    patch = "--- a/../outside.py\n+++ b/../outside.py\n@@ -1 +1,2 @@\n x\n+y\n"
    with pytest.raises(PatchError):
        apply_patch(patch, root)
