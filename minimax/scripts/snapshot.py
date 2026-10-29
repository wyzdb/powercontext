#!/usr/bin/env python
"""给样例工程做代码快照（改前 / 改后各一份），用于提交材料里的"修改前后代码快照"。

用法::

    python scripts/snapshot.py --label before
    python scripts/snapshot.py --label after
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "demo" / "taskboard"
OUT_ROOT = ROOT / "records" / "snapshots"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    args = parser.parse_args(argv)

    out = OUT_ROOT / args.label
    if out.exists():
        shutil.rmtree(out)

    files: list[dict] = []
    for path in sorted((DEMO / "taskboard").glob("*.py")):
        rel = path.relative_to(DEMO)
        target = out / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        files.append({"path": rel.as_posix(), "sha256": _sha256(path), "bytes": path.stat().st_size})

    manifest = {
        "label": args.label,
        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
        "root": "demo/taskboard",
        "files": files,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
