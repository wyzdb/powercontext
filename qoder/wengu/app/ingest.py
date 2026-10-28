"""把 data/raw/ 的讲义灌进 seekdb。

流程：解析 front matter → 按 "##" 切节 → 向量化 → 写 doc_meta / chunks /
concept / chunk_concept。幂等：同 doc_id 先删后插，chunk_uid 用 sha1 保证可复现。

用法：
    python -m app.ingest            # 全量
    python -m app.ingest --dry-run  # 只统计，不写库
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import pymysql

try:
    from app.embed import embed_texts, to_sql_vector, fit_idf, PROVIDER, DIM
except ImportError:  # 直接跑脚本时
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.embed import embed_texts, to_sql_vector, fit_idf, PROVIDER, DIM

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
DOC_MD = ROOT / "docs" / "01-需求与方案.md"

# doc_id 前缀 → (topic, level, has_code)
DOC_META = {
    "architecture": ("architecture", "入门", 0),
    "performance": ("performance", "入门", 1),
    "mpi": ("mpi", "进阶", 1),
    "collectives": ("mpi", "进阶", 1),
    "openmp": ("openmp", "进阶", 1),
    "design": ("design", "进阶", 0),
}


def connect():
    return pymysql.connect(
        host=os.getenv("SEEKDB_HOST", "127.0.0.1"),
        port=int(os.getenv("SEEKDB_PORT", "2881")),
        user=os.getenv("SEEKDB_USER", "root"),
        password=os.getenv("SEEKDB_PASSWORD", ""),
        database=os.getenv("SEEKDB_DATABASE", "wengu"),
        autocommit=False, charset="utf8mb4",
    )


def parse_doc(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    meta = {}
    if m:
        for line in m.group(1).splitlines():
            if ": " in line:
                k, v = line.split(": ", 1)
                meta[k.strip()] = v.strip()
        text = text[m.end():]
    return meta, text


def split_sections(body: str) -> list[tuple[str, str]]:
    """按 "## " 切；第一个标题前的内容丢弃（那只是文件标题）。"""
    parts = re.split(r"^##\s+", body, flags=re.M)
    return [(p.split("\n", 1)[0].strip(), p.split("\n", 1)[1].strip())
            for p in parts[1:] if "\n" in p]


def load_concepts(doc_path: Path) -> list[dict]:
    """从 §4.8 的表格里把受控词表读出来，避免在代码里重复维护一份。"""
    if not doc_path.exists():
        return []
    text = doc_path.read_text(encoding="utf-8")
    m = re.search(r"### 4\.8.*?\n(.*?)(?=\n### 4\.9)", text, re.S)
    if not m:
        return []
    out = []
    for line in m.group(1).splitlines():
        if not line.startswith("| `"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 5:
            continue
        out.append({
            "concept_id": cells[0].strip("`"),
            "name": cells[1],
            "topic": cells[2],
            "span": cells[3],
            "count": cells[4].replace("*", ""),
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not RAW.exists():
        print(f"[错误] 找不到 {RAW}", file=sys.stderr)
        return 2

    files = sorted(RAW.glob("*.md"))
    print(f"语料 {len(files)} 篇，向量方案 = {PROVIDER}（{DIM} 维）")

    docs, all_chunks = [], []
    for path in files:
        meta, body = parse_doc(path)
        doc_id = meta.get("doc_id", path.stem)
        key = doc_id.split("-", 1)[-1] if "-" in doc_id else doc_id
        topic, level, has_code = DOC_META.get(key.split("-")[0], ("design", "入门", 0))
        sections = split_sections(body)
        for i, (heading, text) in enumerate(sections, 1):
            all_chunks.append({
                "doc_id": doc_id,
                "source_file": f"data/raw/{path.name}",
                "section_no": i,
                "heading": heading,
                "heading_path": f"《{meta.get('title', doc_id)}》>> {heading}",
                "content": text,
                "course": meta.get("course", "parallel-computing"),
                "doc_type": meta.get("doc_type", "讲义"),
                "language": meta.get("language", "zh"),
                "topic": topic, "level": level, "has_code": 1 if "```" in text else has_code,
            })
        docs.append({
            "doc_id": doc_id, "title": meta.get("title", doc_id),
            "source_file": f"data/raw/{path.name}",
            "course": meta.get("course", "parallel-computing"),
            "doc_type": meta.get("doc_type", "讲义"),
            "language": meta.get("language", "zh"),
            "char_len": len(body), "cjk_len": sum(1 for c in body if "\u4e00" <= c <= "\u9fff"),
            "section_count": len(sections), "chunk_count": len(sections),
            "content_sha": hashlib.sha1(body.encode()).hexdigest(),
            "src_mtime": datetime.fromtimestamp(path.stat().st_mtime),
        })
        print(f"  {path.name:24} {len(sections):2} 节  {len(body):5} 字")

    concepts = load_concepts(DOC_MD)
    print(f"概念词表 {len(concepts)} 条，切片 {len(all_chunks)} 块")

    if args.dry_run:
        return 0

    print("\n拟合 IDF...")
    fit_idf([c["content"] for c in all_chunks])
    print("向量化中...")
    vecs = embed_texts([c["content"] for c in all_chunks])
    print(f"  完成，首条维度 {len(vecs[0])}")

    conn = connect()
    cur = conn.cursor()
    try:
        for d in docs:
            cur.execute("DELETE cc FROM chunk_concept cc JOIN chunks c ON c.id=cc.chunk_id WHERE c.doc_id=%s", (d["doc_id"],))
            cur.execute("DELETE FROM chunks WHERE doc_id=%s", (d["doc_id"],))
            cur.execute("DELETE FROM doc_meta WHERE doc_id=%s", (d["doc_id"],))
            cur.execute(
                """INSERT INTO doc_meta (doc_id, title, source_file, course, doc_type, language,
                     char_len, cjk_len, section_count, chunk_count, src_mtime, content_sha,
                     ingest_status, last_indexed_at, created_at, updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'indexed',NOW(),NOW(),NOW())""",
                (d["doc_id"], d["title"], d["source_file"], d["course"], d["doc_type"],
                 d["language"], d["char_len"], d["cjk_len"], d["section_count"],
                 d["chunk_count"], d["src_mtime"], d["content_sha"]))

        for c, v in zip(all_chunks, vecs):
            uid = hashlib.sha1(
                f"{c['source_file']}|{c['section_no']}|1".encode()).hexdigest()
            cur.execute(
                """INSERT INTO chunks (chunk_uid, doc_id, source_file, section_no,
                     section_heading, heading_path, part_no, part_count, content, content_seg,
                     char_len, course, doc_type, language, topic, level, has_code,
                     review_status, emb, src_mtime, ingested_at)
                   VALUES (%s,%s,%s,%s,%s,%s,1,1,%s,%s,%s,%s,%s,%s,%s,%s,%s,'ok',%s,NOW(),NOW())""",
                (uid, c["doc_id"], c["source_file"], c["section_no"], c["heading"][:200],
                 c["heading_path"][:300], c["content"], c["content"], len(c["content"]),
                 c["course"], c["doc_type"], c["language"], c["topic"], c["level"],
                 c["has_code"], to_sql_vector(v)))

        for k in concepts:
            cur.execute(
                """INSERT INTO concept (concept_id, canonical_name, aliases, topic,
                     docs_span, doc_count, note)
                   VALUES (%s,%s,'',%s,%s,%s,'')
                   ON DUPLICATE KEY UPDATE canonical_name=VALUES(canonical_name),
                     docs_span=VALUES(docs_span), doc_count=VALUES(doc_count)""",
                (k["concept_id"], k["name"], k["topic"], k["span"],
                 int(k["count"]) if k["count"].isdigit() else 1))

        # 切片 ↔ 概念：标题里出现记 primary，正文出现记 mention
        cur.execute("SELECT id, section_heading, content FROM chunks")
        rows = cur.fetchall()
        cur.execute("SELECT concept_id, canonical_name FROM concept")
        cmap = cur.fetchall()
        linked = 0
        for chunk_id, heading, content in rows:
            for cid, cname in cmap:
                short = cname.split(" / ")[0].split("、")[0].strip()
                if len(short) < 2:
                    continue
                if short in (heading or ""):
                    role = "primary"
                elif short in (content or ""):
                    role = "mention"
                else:
                    continue
                cur.execute(
                    """INSERT IGNORE INTO chunk_concept (chunk_id, concept_id, role)
                       VALUES (%s,%s,%s)""", (chunk_id, cid, role))
                linked += 1
        conn.commit()
        print(f"  概念关联 {linked} 条")
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.execute("SELECT COUNT(*) FROM chunks")
        n = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM concept")
        m = cur.fetchone()[0]
        conn.close()

    print(f"\n入库完成：chunks={n}  concept={m}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
