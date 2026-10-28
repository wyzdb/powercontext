"""PowerContext 本地 mock 服务。

实现温故需要的 3 个端点：
- POST /v1/scopes              创建/返回 scope
- POST /v1/memory/remember     写入记忆
- POST /v1/memory/entries/list 列出记忆

数据存在内存里，进程退出即失。仅用于演示。
"""

import json
import time
import uuid
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="PowerContext Mock")

# 内存存储
_scopes: dict[str, dict] = {}  # scope_id -> {title, summary, idempotency_key}
_memories: dict[str, list[dict]] = {}  # scope_id -> [entries]


@app.post("/v1/scopes")
async def create_scope(req: Request):
    body = await req.json()
    key = body.get("idempotency_key", "")
    # 幂等：同 key 返回已有 scope
    for sid, s in _scopes.items():
        if s.get("idempotency_key") == key:
            return {"scope_id": sid, "title": s["title"]}
    sid = "scp_" + uuid.uuid4().hex[:16]
    _scopes[sid] = {
        "title": body.get("title", ""),
        "summary": body.get("summary", ""),
        "idempotency_key": key,
    }
    _memories.setdefault(sid, [])
    return {"scope_id": sid, "title": body.get("title", "")}


@app.post("/v1/memory/remember")
async def remember(req: Request):
    body = await req.json()
    sid = body.get("scope_id", "")
    if sid not in _memories:
        _memories[sid] = []
    entry = {
        "artifact_id": "art_" + uuid.uuid4().hex[:12],
        "kind": body.get("kind", ""),
        "text": body.get("text", ""),
        "state": "active",
        "created_at": int(time.time()),
    }
    _memories[sid].append(entry)
    return {"records": [{"artifact": {"artifact_id": entry["artifact_id"]}}]}


@app.post("/v1/memory/entries/list")
async def list_entries(req: Request):
    body = await req.json()
    sid = body.get("scope_id", "")
    entries = _memories.get(sid, [])
    return {"entries": entries, "next_cursor": None}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
