"""PowerContext 客户端。

设计（见 docs/01-需求与方案.md §4.7.3）：
- 4 条路径集中在常量里。端点不确定的风险被限制在 4 行内。
- 服务不可用时抛 MemoryUnavailable，由上层降级成「本次未记入档案」，
  **绝不**把记忆兜底写进 seekdb——宁可丢一次记忆，也不能让状态分裂到两个系统。
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass


def _env() -> tuple[str, str]:
    try:
        from app.embed import load_env  # 复用它已经读过的 .env
        load_env()
    except Exception:
        pass
    return (os.getenv("PC_BASE_URL", "").rstrip("/"),
            os.getenv("PC_TOKEN", ""))


BASE, TOKEN = _env()
PATH_PROFILE = "/scopes/{scope}/memories"
PATH_UPSERT = "/memories"
PATH_UPDATE = "/memories/{mid}"


class MemoryUnavailable(RuntimeError):
    pass


class MemoryAuth(RuntimeError):
    pass


@dataclass
class MemoryResult:
    ok: bool
    items: list[dict]
    note: str = ""


def _call(method: str, path: str, payload: dict | None = None) -> dict:
    base, token = _env()
    if not base:
        raise MemoryUnavailable("PC_BASE_URL 未配置")
    url = base + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")

    last = None
    for attempt, delay in enumerate((0, 0.5, 1.0, 2.0)):
        if delay:
            time.sleep(delay)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                body = r.read().decode("utf-8", "replace")
                return json.loads(body) if body.strip() else {}
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise MemoryAuth(f"HTTP {e.code}") from e
            last = e
        except Exception as e:  # 连接失败、超时
            last = e
    raise MemoryUnavailable(str(last))


def get_profile(learner: str) -> MemoryResult:
    """读 scope 内全部弱点与进度；服务不在就返回降级结果，不抛给前端。"""
    try:
        data = _call("GET", PATH_PROFILE.format(scope=f"learner:{learner}"))
        items = data.get("memories") or data.get("items") or []
        return MemoryResult(True, items)
    except (MemoryUnavailable, MemoryAuth) as e:
        return MemoryResult(False, [], str(e))


def upsert_weakness(learner: str, concept: str, wrong_answer: str = "") -> MemoryResult:
    """错一次就记一次；已存在则 count+1，不新增条目。"""
    scope = f"learner:{learner}"
    try:
        existing = _call("GET", PATH_PROFILE.format(scope=scope) + f"?key=weakness:{concept}")
        items = existing.get("memories") or []
        if items:
            item = items[0]
            payload = {**item, "count": int(item.get("count", 1)) + 1,
                       "status": "新学", "last_seen": int(time.time())}
            _call("PUT", PATH_UPDATE.format(mid=item["id"]), payload)
        else:
            _call("POST", PATH_UPSERT, {
                "scope": scope, "key": f"weakness:{concept}", "type": "weakness",
                "concept": concept, "count": 1, "status": "新学",
                "evidence": wrong_answer[:500], "last_seen": int(time.time())})
        return MemoryResult(True, [])
    except (MemoryUnavailable, MemoryAuth) as e:
        return MemoryResult(False, [], str(e))


def advance_progress(learner: str, concept: str) -> MemoryResult:
    scope = f"learner:{learner}"
    order = ["新学", "巩固", "掌握"]
    try:
        existing = _call("GET", PATH_PROFILE.format(scope=scope) + f"?key=weakness:{concept}")
        items = existing.get("memories") or []
        if not items:
            return MemoryResult(True, [])
        item = items[0]
        cur = item.get("status", "新学")
        nxt = order[min(order.index(cur) + 1, len(order) - 1)] if cur in order else "新学"
        payload = {**item, "status": nxt,
                   "streak_correct": int(item.get("streak_correct", 0)) + 1,
                   "last_seen": int(time.time())}
        _call("PUT", PATH_UPDATE.format(mid=item["id"]), payload)
        return MemoryResult(True, [])
    except (MemoryUnavailable, MemoryAuth) as e:
        return MemoryResult(False, [], str(e))
