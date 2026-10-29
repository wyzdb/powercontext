"""按任务组装上下文：规格 → 引用 → 代码 / 测试。

选择策略（写进一页技术说明的核心）：
1. 用任务文本切词，对 seekdb 里的文档打分（标题权重 > 正文）；
2. 命中的最高分规格作为「主规格」，它的「适用模块 / 关联测试」通过
   spec_refs 关系展开成代码与测试——即使代码里没出现"标签"这类词也能定位；
3. 主规格的「上游规格」作为约束一起带上，其关联测试作为回归测试；
4. 输出每一项都带真实路径与行号，便于评审核对来源。
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Iterable

from . import importer
from .config import DBConfig, DEMO_DIR

CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{1,}")
STOPWORDS = {"the", "and", "for", "with", "add", "task", "tasks"}


def tokenize(text: str) -> list[str]:
    """英文按词、中文按二元组切，够用且不引第三方分词库。"""

    tokens: dict[str, None] = {}
    for word in WORD_RE.findall(text):
        lowered = word.lower()
        if lowered not in STOPWORDS:
            tokens[lowered] = None
    for run in CJK_RE.findall(text):
        if len(run) <= 2:
            tokens[run] = None
        for i in range(len(run) - 1):
            tokens[run[i : i + 2]] = None
    return list(tokens)


def _score(doc: dict, tokens: Iterable[str]) -> float:
    title = doc["title"].lower()
    content = doc["content"].lower()
    score = 0.0
    for token in tokens:
        score += 3 * title.count(token)
        score += min(content.count(token), 5)
    return score


def _excerpt(content: str, tokens: Iterable[str], width: int = 300) -> str:
    lowered = content.lower()
    positions = [lowered.find(t) for t in tokens]
    positions = [p for p in positions if p >= 0]
    start = max(0, (min(positions) if positions else 0) - 80)
    snippet = content[start : start + width]
    return snippet.strip().replace("\n", " ")


def _pick_symbols(doc: dict, tokens: Iterable[str]) -> list[dict]:
    """按「名字 + 文档字符串 + 源码片段」的相关度挑符号。"""

    symbols = doc["meta"].get("symbols", [])
    if not symbols:
        return []
    tokens = list(tokens)
    lines = doc["content"].splitlines()

    def source_of(symbol: dict) -> str:
        start = max(0, symbol["line"] - 1)
        end = min(len(lines), symbol.get("end_line") or symbol["line"])
        return "\n".join(lines[start:end])

    def relevance(symbol: dict) -> int:
        name = symbol["name"].lower()
        body = f'{symbol.get("doc", "")}\n{source_of(symbol)}'.lower()
        score = 0
        for token in tokens:
            if token in name:
                score += 3
            score += min(body.count(token), 3)
        return score

    ranked = sorted(symbols, key=relevance, reverse=True)
    best = [s for s in ranked if relevance(s) > 0]
    # 嵌套函数与它的外层函数会同时命中，只保留最相关的 3 个
    return best[:3] or ranked[:2]


def build_context(task: str, *, root=DEMO_DIR, state: dict | None = None, top_specs: int = 2) -> dict:
    docs = importer.load_documents()
    refs = importer.load_refs()
    by_path = {doc["path"]: doc for doc in docs}
    tokens = tokenize(task)

    scored = sorted(
        ((_score(doc, tokens), doc) for doc in docs),
        key=lambda pair: pair[0],
        reverse=True,
    )

    # 规格候选先由 seekdb 用 LIKE 预筛，再在应用层打分
    spec_candidates = importer.search_specs(tokens)
    if not spec_candidates:
        spec_candidates = [doc for doc in docs if doc["kind"] == "spec"]
    spec_scored = sorted(
        ((_score(doc, tokens), doc) for doc in spec_candidates),
        key=lambda pair: pair[0],
        reverse=True,
    )

    spec_hits = [(score, doc) for score, doc in spec_scored if score > 0]
    primary = spec_hits[0][1] if spec_hits else None
    constraints = [doc for _, doc in spec_hits[1 : 1 + top_specs] if primary and doc["doc_key"] != primary["doc_key"]]

    # 主规格声明的引用：模块 → 代码，关联测试 → 目标测试
    codes: list[dict] = []
    target_tests: list[dict] = []
    regression_tests: list[dict] = []

    if primary:
        for ref in refs:
            if ref["spec_key"] != primary["doc_key"]:
                continue
            doc = by_path.get(ref["target_path"])
            if doc is None:
                continue
            if ref["relation"] == "module":
                codes.append(doc)
            elif ref["relation"] == "test":
                target_tests.append(doc)
            elif ref["relation"] == "regression":
                regression_tests.append(doc)

    # 约束规格（上游）引用的测试，作为回归测试
    for constraint in constraints:
        for ref in refs:
            if ref["spec_key"] == constraint["doc_key"] and ref["relation"] == "test":
                doc = by_path.get(ref["target_path"])
                if doc is not None and doc not in target_tests:
                    regression_tests.append(doc)

    # 兜底：没有规格命中时，用打分最高的代码/测试
    if not codes:
        codes = [doc for score, doc in scored if doc["kind"] == "code" and score > 0][:2]
    if not target_tests:
        target_tests = [doc for score, doc in scored if doc["kind"] == "test" and score > 0][:1]

    # 同一测试可能被多个规格引用，按路径去重且 target 优先
    target_tests = list({doc["doc_key"]: doc for doc in target_tests}.values())
    regression_tests = [
        doc for doc in {doc["doc_key"]: doc for doc in regression_tests}.values()
        if doc["doc_key"] not in {d["doc_key"] for d in target_tests}
    ]

    def spec_entry(doc: dict, role: str) -> dict:
        return {
            "key": doc["doc_key"],
            "title": doc["title"],
            "path": doc["path"],
            "role": role,
            "score": _score(doc, tokens),
            "requirements": doc["meta"].get("requirements", []),
            "excerpt": _excerpt(doc["content"], tokens),
        }

    def code_entry(doc: dict) -> dict:
        symbols = _pick_symbols(doc, tokens)
        return {
            "path": doc["path"],
            "doc_key": doc["doc_key"],
            "sha256": doc["sha256"],
            "reason": f"被 {primary['doc_key']} 的「适用模块」引用" if primary else "与任务关键词匹配",
            "symbols": [
                {"name": s["name"], "line": s["line"], "end_line": s["end_line"], "doc": s.get("doc", "")}
                for s in symbols
            ],
        }

    def test_entry(doc: dict, role: str, reason: str) -> dict:
        return {
            "path": doc["path"],
            "doc_key": doc["doc_key"],
            "role": role,
            "reason": reason,
            "cases": doc["meta"].get("cases", []),
        }

    payload = {
        "task": task,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "database": {
            "dsn": _dsn(),
            "documents": len(docs),
            "spec_refs": len(refs),
            "spec_query": importer.last_query(),
        },
        "retrieval": {
            "tokens": tokens,
            "primary_spec": primary["doc_key"] if primary else None,
            "constraints": [doc["doc_key"] for doc in constraints],
        },
        "specs": ([spec_entry(primary, "primary")] if primary else [])
        + [spec_entry(doc, "constraint") for doc in constraints],
        "code": [code_entry(doc) for doc in codes],
        "tests": [
            test_entry(doc, "target", f"{primary['doc_key']} 的「关联测试」" if primary else "关键词命中")
            for doc in target_tests
        ]
        + [
            test_entry(doc, "regression", f"{doc['doc_key']} 由约束规格引用")
            for doc in regression_tests
            if doc not in target_tests
        ],
        "state": state or {"done": [], "todo": [], "verifications": []},
    }
    return payload


def _dsn() -> str:
    cfg = DBConfig.from_env()
    return f"seekdb://{cfg.host}:{cfg.port}/{cfg.database}"
