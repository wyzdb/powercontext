"""Sample maintenance: restore the business tree and clear task records."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sdd_context.config import Settings
from sdd_context.models import TaskState
from sdd_context.patcher import snapshot_sources
from sdd_context.powercontext_state import PowerContextState
from sdd_context.store import SeekdbStore


def reset_sample(
    settings: Settings,
    store: SeekdbStore,
    *,
    task_id: str | None = None,
    clear_state: bool = False,
    restore_code: bool = True,
) -> dict[str, Any]:
    """Restore the pristine sources and remove records for ``task_id``."""

    before = settings.artifacts_dir / "before"
    restored: list[str] = []
    if restore_code:
        if not before.is_dir():
            raise SystemExit(
                f"missing baseline snapshot: {before}; run the sample once before resetting"
            )
        for name in ("src", "tests", "specs"):
            source = before / name
            if not source.is_dir():
                continue
            for path in sorted(source.rglob("*")):
                if path.is_dir():
                    continue
                relative = path.relative_to(before)
                target = settings.business_root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(path.read_bytes())
                restored.append(relative.as_posix())

    deleted: dict[str, int] = {}
    if task_id:
        deleted = store.delete_task(task_id)

    state_record: dict[str, Any] | None = None
    if clear_state and task_id:
        empty = TaskState(
            task_id=task_id,
            title="reset",
            status="empty",
            step="reset",
            done=[],
            todo=[],
            verifications=[],
        )
        state_record = PowerContextState(settings).save(store, empty)

    return {
        "restored_files": len(restored),
        "restored": restored[:20],
        "deleted": deleted,
        "task_id": task_id,
        "state": state_record,
    }


def capture_baseline(settings: Settings) -> dict[str, Any]:
    """Snapshot the pristine sources under ``artifacts/before``."""

    destination = settings.artifacts_dir / "before"
    written = snapshot_sources(settings.business_root, destination)
    return {"destination": str(destination.relative_to(settings.root)), "files": len(written)}
