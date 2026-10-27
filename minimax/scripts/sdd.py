"""Launcher for environments where PYTHONPATH is ignored (embedded Python).

Usage: ``python scripts/sdd.py <subcommand> ...``
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "context"))

from sdd_context.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
