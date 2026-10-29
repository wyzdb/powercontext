"""PowerContext 任务状态读写。

用途：把「任务做到哪一步、哪些验证已经跑过」存成 PowerContext 的 Memory，
换一个进程/重启 Server 之后还能读回来，接着用。

约定：
- 一个 Scope 对应一个工程（这里叫 ``mmx-sdd-taskboard``）；
- 一条 Memory 对应一个任务的状态，正文是 JSON，前缀 ``STATE <TASK_ID>``；
- Scope ID 缓存在 ``state/scope.json``，丢了也没关系——同样的 idempotency_key
  会让 Server 返回同一个 Scope。
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from powercontext.client import PowerContextClient
from powercontext.http import (
    CreateScopeRequest,
    RememberMemoryRequest,
    SearchMemoryRequest,
)

from .config import ROOT

SERVER_URL = os.getenv("POWERCONTEXT_SERVER_URL", "http://127.0.0.1:18080")
SCOPE_FILE = ROOT / "state" / "scope.json"
SCOPE_TITLE = "mmx-sdd-taskboard"
SCOPE_KEY = "mmx-sdd-taskboard-v1"
SCOPE_SUMMARY = "MiniMax 赛道：SDD 上下文管理样例工程"

STATE_PREFIX = "STATE "


def _load_scope_file() -> str | None:
    if not SCOPE_FILE.is_file():
        return None
    try:
        return json.loads(SCOPE_FILE.read_text(encoding="utf-8"))["scope_id"]
    except (KeyError, json.JSONDecodeError):
        return None


def _write_scope_file(scope_id: str) -> None:
    SCOPE_FILE.parent.mkdir(parents=True, exist_ok=True)
    SCOPE_FILE.write_text(
        json.dumps({"scope_id": scope_id, "title": SCOPE_TITLE, "server": SERVER_URL}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )


async def _ensure_scope(client: PowerContextClient) -> str:
    cached = _load_scope_file()
    if cached:
        return cached

    # 先找同名 Scope：换机器、丢缓存或重复初始化时都能复用，不会撞 409
    page = await client.list_scopes(limit=50)
    for item in getattr(page, "items", None) or []:
        if getattr(item, "title", "") == SCOPE_TITLE:
            _write_scope_file(item.scope_id)
            return item.scope_id

    scope = await client.create_scope(
        CreateScopeRequest(title=SCOPE_TITLE, summary=SCOPE_SUMMARY, idempotency_key=SCOPE_KEY)
    )
    _write_scope_file(scope.scope_id)
    return scope.scope_id


def _state_text(task_id: str, payload: dict[str, Any]) -> str:
    return f"{STATE_PREFIX}{task_id} {json.dumps(payload, ensure_ascii=False, sort_keys=True)}"


def _parse_state(text: str, task_id: str) -> dict[str, Any] | None:
    prefix = f"{STATE_PREFIX}{task_id} "
    if not text.startswith(prefix):
        return None
    try:
        return json.loads(text[len(prefix) :])
    except json.JSONDecodeError:
        return None


async def _find_state(client: PowerContextClient, scope_id: str, task_id: str):
    """找出该任务已有的状态 Memory（取 updated_at 最新的一条）。"""

    response = await client.search_memory(
        SearchMemoryRequest(scope_id=scope_id, query=f"{STATE_PREFIX}{task_id}", limit=20)
    )

    best = None
    for hit in getattr(response, "hits", None) or []:
        memory = getattr(hit, "memory", None)
        if memory is None:
            continue
        parsed = _parse_state(getattr(memory, "text", "") or "", task_id)
        if parsed is None:
            continue
        stamp = str(parsed.get("updated_at", ""))
        revision = getattr(getattr(memory, "artifact", None), "revision", 0) or 0
        key = (stamp, revision)
        if best is None or key >= best[0]:
            best = (key, memory)
    return best[1] if best else None


async def save_state(task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """写入任务状态。

    PowerContext 的 atomic-memory 每次 ``remember`` 会生成一个新 artifact；
    读回时按 ``updated_at`` 选最新一条，因此这里保持"追加"语义，
    历史 revision 都可追溯。
    """

    payload = {
        **payload,
        "task_id": task_id,
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    text = _state_text(task_id, payload)

    async with PowerContextClient(SERVER_URL) as client:
        scope_id = await _ensure_scope(client)
        response = await client.remember_memory(
            RememberMemoryRequest(scope_id=scope_id, kind="state", text=text, reason=f"{task_id} 阶段状态")
        )

    records = getattr(response, "records", None) or []
    artifact = records[0].artifact if records else None
    return {
        "scope_id": scope_id,
        "server": SERVER_URL,
        "mode": "append",
        "artifact": getattr(artifact, "artifact_id", None),
        "revision": getattr(artifact, "revision", None),
        "state": payload,
    }


async def load_state(task_id: str, limit: int = 20) -> dict[str, Any] | None:
    """按任务 ID 找回最近一次状态（按 updated_at 取最新）。"""

    async with PowerContextClient(SERVER_URL) as client:
        scope_id = await _ensure_scope(client)
        memory = await _find_state(client, scope_id, task_id)

    if memory is None:
        return None

    artifact = getattr(memory, "artifact", None)
    return {
        "scope_id": scope_id,
        "server": SERVER_URL,
        "artifact": getattr(artifact, "artifact_id", None),
        "revision": getattr(artifact, "revision", None),
        "state": _parse_state(memory.text, task_id),
    }


def save(task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return asyncio.run(save_state(task_id, payload))


def load(task_id: str) -> dict[str, Any] | None:
    return asyncio.run(load_state(task_id))
