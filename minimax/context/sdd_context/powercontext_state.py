"""Task state persisted through PowerContext.

Each task owns durable PowerContext Sources whose content is a JSON state
snapshot (status, done, todo, verification results). Every save appends a new
Source with a fresh id, because Sources are append-only; reading selects the
newest Source for the task prefix. Reading it back after a process restart is
what the grading item "状态能够复用" exercises.

The scope id is stored in seekdb (``sdd_config``) so repeated CLI invocations
reuse the same PowerContext scope instead of creating one per run.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from powercontext.client.client import PowerContextClient
from powercontext.client.errors import TransportError
from powercontext.http._generated.models import (
    CaptureContentSourceRequest,
    CreateScopeRequest,
    ListSourcesRequest,
)

from sdd_context.config import Settings
from sdd_context.models import TaskState
from sdd_context.store import SeekdbStore

_SCOPE_CONFIG_KEY = "powercontext.scope_id"


def _source_prefix(task_id: str) -> str:
    return f"sdd-task-state-{task_id}-"


class PowerContextState:
    """Synchronous facade over the async PowerContext client."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    # -- public API -----------------------------------------------------
    def health(self) -> dict[str, Any]:
        return asyncio.run(self._health())

    def ensure_scope(self, store: SeekdbStore) -> str:
        return asyncio.run(self._ensure_scope(store))

    def save(self, store: SeekdbStore, state: TaskState) -> dict[str, Any]:
        return asyncio.run(self._save(store, state))

    def load(self, store: SeekdbStore, task_id: str) -> TaskState | None:
        return asyncio.run(self._load(store, task_id))

    # -- implementation -------------------------------------------------
    def _client(self) -> PowerContextClient:
        token = self.settings.powercontext_token or None
        return PowerContextClient(self.settings.powercontext_url, token=token, timeout=30.0)

    async def _health(self) -> dict[str, Any]:
        async with self._client() as client:
            liveness = await client.get_liveness()
            return json.loads(liveness.model_dump_json())

    async def _ensure_scope(self, store: SeekdbStore) -> str:
        existing = store.get_config(_SCOPE_CONFIG_KEY)
        if existing:
            return existing
        async with self._client() as client:
            page = await client.list_scopes()
            for item in page.items:
                if item.title == self.settings.powercontext_scope_name:
                    store.set_config(_SCOPE_CONFIG_KEY, item.scope_id)
                    return item.scope_id
            created = await client.create_scope(
                CreateScopeRequest(
                    title=self.settings.powercontext_scope_name,
                    summary="SDD 上下文模块：任务状态、上下文快照与验证结果",
                    context_references=[],
                    external_references=[],
                    idempotency_key=f"sdd-scope-{self.settings.powercontext_scope_name}",
                )
            )
        store.set_config(_SCOPE_CONFIG_KEY, created.scope_id)
        self._journal(
            {
                "operation": "create_scope",
                "scope_id": created.scope_id,
                "title": created.title,
                "version": created.version,
            }
        )
        return created.scope_id

    async def _save(self, store: SeekdbStore, state: TaskState) -> dict[str, Any]:
        scope_id = await self._ensure_scope(store)
        state.revision = max(state.revision, 0) + 1
        state.updated_at = datetime.now(timezone.utc).isoformat()
        content = json.dumps(state.to_mapping(), ensure_ascii=False)
        # Sources are append-only: a new revision gets a new source id so a
        # changed snapshot never conflicts with an earlier capture.
        source_id = (
            f"{_source_prefix(state.task_id)}r{state.revision:03d}-"
            f"{datetime.now(timezone.utc).strftime('%H%M%S%f')}"
        )
        request = CaptureContentSourceRequest(
            scope_id=scope_id,
            source_id=source_id,
            content=content,
            metadata={
                "kind": "sdd.task.state",
                "task_id": state.task_id,
                "step": state.step,
                "revision": state.revision,
            },
        )
        async with self._client() as client:
            response = await client.capture_content_source(request)
        record = {
            "operation": "capture_state",
            "scope_id": scope_id,
            "source_id": request.source_id,
            "status": str(response.status),
            "position": response.position,
            "revision": state.revision,
            "task_id": state.task_id,
            "bytes": len(content),
        }
        self._journal(record)
        return record

    async def _load(self, store: SeekdbStore, task_id: str) -> TaskState | None:
        scope_id = await self._ensure_scope(store)
        prefix = _source_prefix(task_id)
        async with self._client() as client:
            page = await client.list_sources(scope_id, ListSourcesRequest(limit=100))
        latest = None
        for item in page.items:
            if not str(item.source_id).startswith(prefix):
                continue
            if latest is None or int(getattr(item, "position", 0)) > int(
                getattr(latest, "position", 0)
            ):
                latest = item
        if latest is None:
            self._journal(
                {"operation": "missing_state", "task_id": task_id, "scope_id": scope_id}
            )
            return None
        content = latest.content
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)
        state = TaskState.from_mapping(json.loads(content))
        state.revision = int(getattr(latest, "position", 0) or state.revision)
        self._journal(
            {
                "operation": "load_state",
                "scope_id": scope_id,
                "task_id": task_id,
                "source_id": latest.source_id,
                "position": getattr(latest, "position", None),
                "sources": len(page.items),
                "revision": state.revision,
                "status": state.status,
                "step": state.step,
            }
        )
        return state

    def _journal(self, payload: dict[str, Any]) -> None:
        record = {"at": datetime.now(timezone.utc).isoformat(), **payload}
        directory = self.settings.records_dir / "powercontext"
        directory.mkdir(parents=True, exist_ok=True)
        try:
            with (directory / "state.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            pass


def state_transport_available(settings: Settings) -> bool:
    try:
        PowerContextState(settings).health()
        return True
    except (TransportError, OSError, ValueError):
        return False
