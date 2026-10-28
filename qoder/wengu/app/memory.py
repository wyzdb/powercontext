"""PowerContext 客户端。每学习者一个 scope，记忆以结构化 JSON 存在 text 里。

真实 API（2026-10-28 实测）：
    建 scope  POST /v1/scopes              {title, summary, idempotency_key} -> scope_id
    写记忆    POST /v1/memory/remember     {scope_id, kind, text} -> records[0].artifact.artifact_id
    列记忆    POST /v1/memory/entries/list {scope_id} -> {entries:[...], next_cursor}

设计要点：
- scope 按 learner 惰性创建，用 idempotency_key 保证重复调用不产生多个 scope；
  创建结果缓存在 data/pc_scopes.json，避免每次请求都建。
- 服务端没有 update 语义，所以「count+1」用追加 + 读取时取最大值实现：
  同一 concept 的多条记录只认 count 最大的那条。
- artifact_id 保留下来，供 quiz_attempt.memory_ref 追溯。
"""

from __future__ import annotations

import json
import os
import pathlib
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "pc_scopes.json"
MARK = "[[wengu]]"
STATUS_ORDER = ["新学", "巩固", "掌握"]


class MemoryUnavailable(RuntimeError):
    pass


class MemoryAuth(RuntimeError):
    pass


def _base() -> str:
    try:
        from app.embed import load_env
        load_env()
    except Exception:
        pass
    return os.getenv("PC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def _post(path: str, payload: dict) -> dict:
    base = _base()
    url = base + path
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    token = os.getenv("PC_TOKEN", "")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        detail = e.read()[:160].decode("utf-8", "replace")
        if e.code in (401, 403):
            raise MemoryAuth("%s %s -> HTTP %d" % (base, path, e.code)) from e
        raise MemoryUnavailable("%s%s -> HTTP %d: %s" % (base, path, e.code, detail)) from e
    except json.JSONDecodeError as e:
        raise MemoryUnavailable("%s%s -> 响应不是合法 JSON" % (base, path)) from e
    except Exception as e:
        raise MemoryUnavailable("%s%s -> %s" % (base, path, e)) from e


def _load_cache() -> dict:
    if CACHE.exists():
        try:
            return json.loads(CACHE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def scope_for(learner: str) -> str:
    """每个 learner 一个 scope；首次调用时创建并缓存。"""
    override = os.getenv("PC_SCOPE_ID", "")
    if learner == "demo" and override:
        return override
    cache = _load_cache()
    if learner in cache:
        return cache[learner]
    data = _post("/v1/scopes", {
        "title": "wengu learner %s" % learner,
        "summary": "温故复习教练的学习者 scope，由 app 惰性创建",
        "idempotency_key": "wengu-scope-%s" % learner,
    })
    sid = data.get("scope_id") or data.get("id")
    if not sid:
        raise MemoryUnavailable("建 scope 没拿到 scope_id: %s" % json.dumps(data)[:120])
    cache[learner] = sid
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    return sid


def _encode(payload: dict) -> str:
    return MARK + json.dumps(payload, ensure_ascii=False)


def _decode(text: str) -> dict:
    if text.startswith(MARK):
        try:
            return json.loads(text[len(MARK):])
        except Exception:
            pass
    return {"raw": text}


def get_entries(learner: str = "demo") -> list[dict]:
    data = _post("/v1/memory/entries/list", {"scope_id": scope_for(learner)})
    out = []
    for e in data.get("entries", []):
        if e.get("state") not in (None, "active"):
            continue
        if e.get("merged_into_id"):
            continue
        payload = _decode(e.get("text", ""))
        payload["artifact_id"] = (e.get("artifact") or {}).get("artifact_id", "")
        payload["kind"] = e.get("kind", "")
        out.append(payload)
    return out


def remember(learner: str, kind: str, payload: dict) -> str:
    data = _post("/v1/memory/remember", {
        "scope_id": scope_for(learner), "kind": kind, "text": _encode(payload)})
    recs = data.get("records") or []
    if recs:
        return (recs[0].get("artifact") or {}).get("artifact_id", "")
    return ""


def _latest_by_concept(items: list[dict]) -> dict:
    """同一 concept 可能有多条历史记录，只认 count 最大（同 count 取最新）。"""
    best = {}
    for it in items:
        c = it.get("concept")
        if not c:
            continue
        cur = best.get(c)
        if cur is None or int(it.get("count", 1)) >= int(cur.get("count", 1)):
            best[c] = it
    return best


def get_profile(learner: str = "demo") -> dict:
    try:
        items = get_entries(learner)
    except (MemoryUnavailable, MemoryAuth) as e:
        return {"ok": False, "items": [], "note": str(e)}
    latest = _latest_by_concept(items)
    shaped = [{
        "concept": c,
        "count": int(v.get("count", 1)),
        "status": v.get("status", "新学"),
        "evidence": v.get("evidence", ""),
        "artifact_id": v.get("artifact_id", ""),
    } for c, v in latest.items()]
    shaped.sort(key=lambda x: -x["count"])
    unstructured = sum(1 for it in items if not it.get("concept"))
    note = ("另有 %d 条非结构化记忆未纳入统计" % unstructured) if unstructured else ""
    return {"ok": True, "items": shaped, "note": note}


def upsert_weakness(learner: str, concept: str, wrong_answer: str = "") -> dict:
    try:
        prev = _latest_by_concept(get_entries(learner)).get(concept)
        count = int(prev.get("count", 0)) + 1 if prev else 1
        aid = remember(learner, "weakness", {
            "concept": concept or "未分类", "count": count, "status": "新学",
            "evidence": wrong_answer[:300], "at": int(time.time())})
        return {"ok": True, "count": count, "artifact_id": aid, "note": ""}
    except (MemoryUnavailable, MemoryAuth) as e:
        return {"ok": False, "count": 0, "artifact_id": "", "note": str(e)}


def advance_progress(learner: str, concept: str) -> dict:
    try:
        prev = _latest_by_concept(get_entries(learner)).get(concept)
        streak = int(prev.get("streak", 0)) + 1 if prev else 1
        # docs §4.7.2：连对 1 次→巩固，累计 3 次→掌握，中间不跳档
        nxt = "掌握" if streak >= 3 else "巩固"
        aid = remember(learner, "progress", {
            "concept": concept or "未分类", "count": int(prev.get("count", 1)) if prev else 1,
            "streak": streak, "status": nxt, "evidence": "答对一次", "at": int(time.time())})
        return {"ok": True, "count": 0, "status": nxt, "artifact_id": aid, "note": ""}
    except (MemoryUnavailable, MemoryAuth) as e:
        return {"ok": False, "count": 0, "artifact_id": "", "note": str(e)}