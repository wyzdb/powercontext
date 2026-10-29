"""把规格、代码、测试导入 seekdb。

导入是幂等的：``doc_key`` 唯一，重复导入会覆盖内容与元数据；
规格里声明的「适用模块 / 关联测试 / 上游规格」会被解析成 spec_refs 关系。
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path

from . import db
from .config import DEMO_DIR

SPEC_KEY_RE = re.compile(r"^(SPEC-\d+)", re.IGNORECASE)
BACKTICK_RE = re.compile(r"`([^`]+)`")
REQUIREMENT_RE = re.compile(r"^###\s+(REQ-[A-Z]+-\d+)\s*(.*)$", re.MULTILINE)

RELATION_BY_LABEL = (
    ("适用模块", "module"),
    ("回归测试", "regression"),
    ("关联测试", "test"),
    ("上游规格", "spec"),
    ("约束规格", "spec"),
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _first_heading(text: str, fallback: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def _module_title(tree: ast.Module, fallback: str) -> str:
    doc = ast.get_docstring(tree) or ""
    first = doc.strip().splitlines()[0].strip() if doc.strip() else ""
    return first or fallback


def _symbols(tree: ast.Module) -> list[dict]:
    """收集函数/类符号，包含嵌套函数（名字带限定前缀）。"""

    symbols: list[dict] = []

    def visit(node: ast.AST, prefix: str = "") -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = f"{prefix}{child.name}"
                doc = (ast.get_docstring(child) or "").strip()
                symbols.append(
                    {
                        "name": name,
                        "kind": "class" if isinstance(child, ast.ClassDef) else "function",
                        "line": child.lineno,
                        "end_line": getattr(child, "end_lineno", child.lineno),
                        "doc": doc.splitlines()[0] if doc else "",
                    }
                )
                visit(child, prefix=f"{name}.")
                continue
            visit(child, prefix=prefix)

    visit(tree)
    return symbols


def _spec_refs(text: str) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    for line in text.splitlines():
        relation = next((rel for label, rel in RELATION_BY_LABEL if label in line), None)
        if relation is None:
            continue
        for target in BACKTICK_RE.findall(line):
            refs.append((target.strip(), relation))
    return refs


def collect(root: Path = DEMO_DIR) -> list[dict]:
    """扫描样例工程，返回待入库的文档列表。"""

    docs: list[dict] = []

    for path in sorted((root / "specs").glob("*.md")):
        text = _read(path)
        match = SPEC_KEY_RE.match(path.name)
        key = match.group(1).upper() if match else path.stem.upper()
        refs = _spec_refs(text)
        requirements = [
            {"id": match.group(1), "title": match.group(2).strip()}
            for match in REQUIREMENT_RE.finditer(text)
        ]
        docs.append(
            {
                "doc_key": key,
                "kind": "spec",
                "path": path.relative_to(root).as_posix(),
                "title": _first_heading(text, key),
                "content": text,
                "sha256": _sha256(text),
                "meta": {
                    "refs": [{"path": p, "relation": r} for p, r in refs],
                    "requirements": requirements,
                },
            }
        )

    for path in sorted((root / "taskboard").glob("*.py")):
        text = _read(path)
        tree = ast.parse(text)
        rel = path.relative_to(root).as_posix()
        docs.append(
            {
                "doc_key": f"CODE:{rel}",
                "kind": "code",
                "path": rel,
                "title": _module_title(tree, path.stem),
                "content": text,
                "sha256": _sha256(text),
                "meta": {"symbols": _symbols(tree)},
            }
        )

    for path in sorted((root / "tests").glob("*.py")):
        text = _read(path)
        tree = ast.parse(text)
        rel = path.relative_to(root).as_posix()
        symbols = _symbols(tree)
        docs.append(
            {
                "doc_key": f"TEST:{rel}",
                "kind": "test",
                "path": rel,
                "title": _module_title(tree, path.stem),
                "content": text,
                "sha256": _sha256(text),
                "meta": {"cases": [s["name"] for s in symbols if s["name"].startswith("test_")]},
            }
        )

    return docs


def import_all(root: Path = DEMO_DIR) -> dict:
    """全量导入（幂等），并清理已不存在的文档。"""

    db.ensure_schema()
    docs = collect(root)

    conn = db.connect()
    try:
        with conn.cursor() as cur:
            for doc in docs:
                cur.execute(
                    """
                    INSERT INTO documents (doc_key, kind, path, title, content, sha256, meta)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        kind = VALUES(kind),
                        path = VALUES(path),
                        title = VALUES(title),
                        content = VALUES(content),
                        sha256 = VALUES(sha256),
                        meta = VALUES(meta)
                    """,
                    (
                        doc["doc_key"],
                        doc["kind"],
                        doc["path"],
                        doc["title"],
                        doc["content"],
                        doc["sha256"],
                        json.dumps(doc["meta"], ensure_ascii=False),
                    ),
                )

            keys = [doc["doc_key"] for doc in docs]
            placeholders = ", ".join(["%s"] * len(keys))
            cur.execute(f"DELETE FROM documents WHERE doc_key NOT IN ({placeholders})", keys)

            cur.execute("DELETE FROM spec_refs")
            for doc in docs:
                if doc["kind"] != "spec":
                    continue
                for ref in doc["meta"].get("refs", []):
                    cur.execute(
                        """
                        INSERT IGNORE INTO spec_refs (spec_key, target_path, relation)
                        VALUES (%s, %s, %s)
                        """,
                        (doc["doc_key"], ref["path"], ref["relation"]),
                    )

            cur.execute("SELECT kind, COUNT(*) AS n FROM documents GROUP BY kind")
            by_kind = {row["kind"]: row["n"] for row in cur.fetchall()}
    finally:
        conn.close()

    return {"total": len(docs), "by_kind": by_kind, "root": str(root)}


def load_documents() -> list[dict]:
    """读出全部文档（含解析后的 meta）。"""

    conn = db.connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT doc_key, kind, path, title, content, sha256, meta FROM documents ORDER BY kind, path"
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    for row in rows:
        row["meta"] = json.loads(row["meta"]) if row.get("meta") else {}
    return rows


def load_refs() -> list[dict]:
    conn = db.connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT spec_key, target_path, relation FROM spec_refs ORDER BY spec_key, relation")
            return list(cur.fetchall())
    finally:
        conn.close()


def search_specs(tokens: list[str], limit: int = 20) -> list[dict]:
    """在 seekdb 里做规格的候选召回（LIKE 预筛，打分在应用层）。

    返回列与 :func:`load_documents` 对齐，便于上层统一处理。
    """

    if not tokens:
        return []

    where = " OR ".join(["title LIKE %s OR content LIKE %s"] * len(tokens))
    params: list[str] = []
    for token in tokens:
        like = f"%{token}%"
        params.extend([like, like])

    sql = (
        "SELECT doc_key, kind, path, title, content, sha256, meta "
        f"FROM documents WHERE kind = 'spec' AND ({where}) LIMIT {int(limit)}"
    )

    conn = db.connect()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    finally:
        conn.close()

    _LAST_QUERY.update({"sql": sql, "params": params, "rows": len(rows)})

    for row in rows:
        row["meta"] = json.loads(row["meta"]) if row.get("meta") else {}
    return rows


def last_query() -> dict:
    """返回最近一次检索用的 SQL 与参数，供证据日志使用。"""

    return dict(_LAST_QUERY)


_LAST_QUERY: dict = {}
