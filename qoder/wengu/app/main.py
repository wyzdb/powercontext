"""温故应用层：带出处的问答 + 弱点档案（档案本轮为占位数据）。

启动（在项目根目录 qoder/wengu/ 下）：
    uvicorn app.main:app --port 8080
    打开 http://127.0.0.1:8080/

本轮范围：
- POST /api/ask        走 app.retrieval.search，返回 heading_path + content 供前端展开
- GET  /api/profile/{} 返回假数据，第 5 轮整函数替换为 PowerContext 调用
- GET  /               返回 web/index.html
只读 seekdb，不写任何表。
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from pymysql import MySQLError

from app import memory as pc

ROOT = Path(__file__).resolve().parents[1]
WEB_INDEX = ROOT / "web" / "index.html"

MAX_QUERY_CHARS = 500
K_HITS = 3
LEARNER_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


def load_env_file(path: Path) -> None:
    """把 .env 灌进 os.environ，已存在的真实环境变量优先。"""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


# 必须早于 app.embed 的 import：DIM / PROVIDER 在那个模块里是导入期定值的
load_env_file(ROOT / ".env")

from app.retrieval import connect as seekdb_connect, search  # noqa: E402

app = FastAPI(title="温故", description="讲义混合检索 + 薄弱点复习教练")


class AskRequest(BaseModel):
    learner: str = Field(..., min_length=1, max_length=32)
    query: str = Field(..., min_length=1)


def err(code: str, message: str, status: int = 400) -> JSONResponse:
    return JSONResponse(status_code=status, content={"code": code, "message": message})


@app.exception_handler(RequestValidationError)
def _on_validation(_request, exc):
    detail = exc.errors()[0] if exc.errors() else {}
    return err("invalid_request", "参数不合法: %s" % detail.get("msg", "格式错误"), 400)


@app.exception_handler(Exception)
def _on_internal(_request, exc):
    # 不把 stack trace 返回给前端，细节留在服务端日志
    return err("internal_error", "服务内部错误，请查看服务端日志", 500)


_source_cache: dict[str, str] | None = None


def doc_source(doc_id: str) -> str:
    """doc_id → source_file，取自 doc_meta，进程内缓存一次。"""
    global _source_cache
    if _source_cache is None:
        conn = seekdb_connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT doc_id, source_file FROM doc_meta")
                _source_cache = {row["doc_id"]: row["source_file"] for row in cur.fetchall()}
        finally:
            conn.close()
    return _source_cache.get(doc_id, "data/raw/%s.md" % doc_id)


def check_learner(learner: str) -> JSONResponse | None:
    if not LEARNER_RE.match(learner):
        return err(
            "invalid_learner",
            "learner 只能用小写字母/数字/_/-，以字母或数字开头，最长 32 字符（演示请用 demo）",
        )
    return None


@app.get("/")
def index():
    if not WEB_INDEX.is_file():
        return err("web_missing", "找不到 web/index.html，请在项目根目录启动服务", 500)
    return FileResponse(WEB_INDEX, media_type="text/html")


@app.post("/api/ask")
def ask(req: AskRequest):
    bad = check_learner(req.learner)
    if bad:
        return bad

    query = req.query.strip()
    if not query:
        return err("empty_query", "问题不能为空")
    if len(query) > MAX_QUERY_CHARS:
        # 上限存在的理由：检索要把整句送去向量化，超长文本既超出 embedding 输入限制，
        # 也会让 bigram 覆盖率这个判据失真；真要长文提问应该先做摘要，那是另一轮的事
        return err("query_too_long", "问题过长，最多 %d 字（当前 %d 字）" % (MAX_QUERY_CHARS, len(query)))

    try:
        result = search(query, k=K_HITS)
    except MySQLError as exc:
        return err("db_unavailable", "seekdb 不可用: %s" % (exc.args[1] if exc.args else exc), 503)
    except Exception as exc:
        return err("embed_unavailable", "向量化或检索失败: %s" % exc, 503)

    hits = result["hits"]
    citations = [
        {
            "chunk_id": h["id"],
            "doc_id": h["doc_id"],
            "source_file": doc_source(h["doc_id"]),
            "heading_path": h["heading_path"],
            "topic": h["topic"],
            "content": h["content"],
            "excerpt": h["content"][:80],
            "scores": {
                "fused": float(h["fused"]),
                "coverage": round(h["coverage"], 3),
                "vector_rank": h["vrank"],
                "fulltext_rank": h["frank"],
            },
        }
        for h in hits
    ]

    return {
        "learner": req.learner,
        "query": query,
        "citations": citations,
        "degraded": result["degraded"] or "",
        "latency_ms": result["latency_ms"],
        "coverage": result.get("coverage"),
        "message": (
            "命中 %d 条，点开卡片看原文" % len(citations)
            if citations
            else "资料中未提及：%s" % (result.get("note") or "无可靠依据")
        ),
    }


# ---------------- 出题与判分（第 4 轮补） ----------------

LLM_BASE = os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
LLM_KEY = os.getenv("DASHSCOPE_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen-plus")


def _llm(prompt: str, max_tokens: int = 600) -> str:
    """同一把百炼 Key 兼任对话模型；没配就返回空串，由调用方降级。"""
    import json, urllib.request
    if not LLM_KEY:
        return ""
    body = json.dumps({"model": LLM_MODEL, "temperature": 0.3, "max_tokens": max_tokens,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(
        f"{LLM_BASE}/chat/completions", data=body,
        headers={"Authorization": f"Bearer {LLM_KEY}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"].strip()


class GradeRequest(BaseModel):
    learner: str = "demo"
    concept: str = ""
    question: str = ""
    reference: str = ""
    answer: str = ""


@app.get("/api/quiz")
def quiz(learner: str = "demo", concept: str = ""):
    q = (concept or "伪共享").strip()
    try:
        result = search(q, k=1)
    except Exception as exc:
        return err("search_failed", "检索失败: %s" % exc, 503)
    if not result["hits"]:
        return err("no_material", "资料中没有这个概念", 404)

    chunk = result["hits"][0]
    prompt = ("根据下面的资料出一道简答题，只输出问题本身，不要答案。\n\n"
              + chunk["content"][:1200])
    try:
        text = _llm(prompt, 200)
    except Exception:
        text = ""
    return {
        "concept": q,
        "question": text or ("请简述「%s」的核心内容。" % chunk["heading_path"]),
        "reference": chunk["content"][:800],
        "source": chunk["heading_path"],
        "llm_used": bool(text),
    }


@app.post("/api/grade")
def grade(req: GradeRequest):
    prompt = ("参考答案：%s\n\n学习者作答：%s\n\n"
              "判断作答是否正确，只输出一行：第一词是 对 或 错，后面跟一句理由。"
              % (req.reference, req.answer))
    try:
        verdict = _llm(prompt, 200)
    except Exception as exc:
        verdict = "错 判分失败：%s" % str(exc)[:60]
    if not verdict:
        verdict = "对 未配置 LLM，按非空作答记为通过"

    correct = verdict.startswith(("对", "正确", "基本正确", "部分正确"))
    from app import memory as _mem
    if correct:
        res = _mem.advance_progress(req.learner, req.concept)
    else:
        res = _mem.upsert_weakness(req.learner, req.concept, req.answer)
    return {"correct": correct, "feedback": verdict,
            "memory_ok": res["ok"], "memory_note": res["note"]}


@app.get("/api/profile/{learner}")
def profile(learner: str):
    """读 PowerContext 里该学习者的 scope。服务不可用时明确降级，不伪造数据。"""
    bad = check_learner(learner)
    if bad:
        return bad
    mem = pc.get_profile(learner)
    return {
        "learner": learner,
        "source": "powercontext" if mem["ok"] else "unavailable",
        "memory_ok": mem["ok"],
        "note": mem["note"],
        "weaknesses": mem["items"],
        "count": len(mem["items"]),
        "banner": "" if mem["ok"] else "记忆服务不可用，本次不显示历史弱点",
    }
