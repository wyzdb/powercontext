"""Shared paths and sandbox-friendly temporary projects for the module tests."""

from __future__ import annotations

import shutil
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "context"))


@pytest.fixture
def project_dir() -> Path:
    """A writable scratch directory created without a private DACL.

    ``tmp_path`` uses ``mkdtemp`` semantics (mode 0700), which some Windows
    sandboxes deny to the confined process. ``os.makedirs`` inherits the
    workspace permissions and stays writable.
    """

    base = ROOT / "tests" / ".tmp" / uuid.uuid4().hex
    base.mkdir(parents=True)
    try:
        yield base
    finally:
        shutil.rmtree(base, ignore_errors=True)
