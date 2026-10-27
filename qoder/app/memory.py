"""Researcher profile memory backed by PowerContext."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from powercontext.builtin.artifacts.memory import MemoryEntryInput
from powercontext.builtin.persistence.sqlite import SQLiteConfig
from powercontext.builtin.runtime import BuiltinConfig, RememberMemoryRequest, open_builtin_runtime
from powercontext.builtin.scope import ScopeDraft

PREFIX = "RESEARCHFLOW_PROFILE:"


class ProfileMemory:
    def __init__(self, database_path: Path) -> None:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self.database_path = database_path
        self.config = BuiltinConfig(database=SQLiteConfig(url=f"sqlite+aiosqlite:///{database_path.as_posix()}"))

    async def _scope(self, runtime: Any) -> str:
        scope = await runtime.scopes.create(
            ScopeDraft(title="ResearchFlow profile", summary="Researcher interests", idempotency_key="researchflow-profile")
        )
        return scope.scope_id

    async def _save(self, user_id: str, profile: dict[str, Any]) -> None:
        async with open_builtin_runtime(self.config) as runtime:
            scope_id = await self._scope(runtime)
            memory = runtime.memory.for_scope(scope_id)
            await memory.remember(
                RememberMemoryRequest(
                    entries=(
                        MemoryEntryInput(
                            kind="profile",
                            text=PREFIX + json.dumps({"user_id": user_id, **profile}, ensure_ascii=False, sort_keys=True),
                        ),
                    )
                )
            )

    async def _load(self, user_id: str) -> dict[str, Any] | None:
        async with open_builtin_runtime(self.config) as runtime:
            scope_id = await self._scope(runtime)
            page = await runtime.memory.for_scope(scope_id).list()
            found = []
            for record in page.entries:
                text = record.entry.text
                if text.startswith(PREFIX):
                    try:
                        profile = json.loads(text[len(PREFIX) :])
                    except json.JSONDecodeError:
                        continue
                    if profile.get("user_id") == user_id:
                        found.append(profile)
            return found[-1] if found else None

    def save(self, user_id: str, profile: dict[str, Any]) -> None:
        asyncio.run(self._save(user_id, profile))

    def load(self, user_id: str) -> dict[str, Any] | None:
        return asyncio.run(self._load(user_id))

    @property
    def source(self) -> str:
        return f"powercontext://sqlite/{self.database_path}"
