"""Task-state persistence through the PowerContext runtime."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from powercontext.builtin.artifacts.memory import MemoryEntryInput
from powercontext.builtin.persistence.sqlite import SQLiteConfig
from powercontext.builtin.runtime import BuiltinConfig, RememberMemoryRequest, open_builtin_runtime
from powercontext.builtin.scope import ScopeDraft

STATE_PREFIX = "SDD_TASK_STATE:"


class PowerContextState:
    """Store and reload task progress as PowerContext Memory entries."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.config = BuiltinConfig(
            database=SQLiteConfig(url=f"sqlite+aiosqlite:///{self.database_path.as_posix()}")
        )

    def _run(self, operation: Any) -> Any:
        return asyncio.run(operation())

    async def _scope(self, runtime: Any) -> str:
        scope = await runtime.scopes.create(
            ScopeDraft(
                title="SDD task state",
                summary="Progress and validation records",
                idempotency_key="sdd-task-state",
            )
        )
        return scope.scope_id

    async def _save(self, state: dict[str, Any]) -> None:
        async with open_builtin_runtime(self.config) as runtime:
            scope_id = await self._scope(runtime)
            memory = runtime.memory.for_scope(scope_id)
            await memory.remember(
                RememberMemoryRequest(
                    entries=(
                        MemoryEntryInput(
                            kind="task_state",
                            text=STATE_PREFIX + json.dumps(state, ensure_ascii=False, sort_keys=True),
                        ),
                    )
                )
            )

    async def _load(self, task_id: str) -> dict[str, Any] | None:
        async with open_builtin_runtime(self.config) as runtime:
            scope_id = await self._scope(runtime)
            memory = runtime.memory.for_scope(scope_id)
            page = await memory.list()
            found: list[dict[str, Any]] = []
            for record in page.entries:
                text = record.entry.text
                if not text.startswith(STATE_PREFIX):
                    continue
                try:
                    state = json.loads(text[len(STATE_PREFIX) :])
                except json.JSONDecodeError:
                    continue
                if state.get("task_id") == task_id:
                    found.append(state)
            if not found:
                return None
            return sorted(found, key=lambda item: item.get("updated_at", ""))[-1]

    def save(self, state: dict[str, Any]) -> None:
        self._run(lambda: self._save(state))

    def load(self, task_id: str) -> dict[str, Any] | None:
        return self._run(lambda: self._load(task_id))

    @property
    def source(self) -> str:
        return f"powercontext://sqlite/{self.database_path}"
