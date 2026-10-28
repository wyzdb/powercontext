#!/usr/bin/env python3
"""扫描 data/raw/，生成 manifest.json，并做一遍隐私自检。

用法：
    python scripts/build_manifest.py            # 生成清单 + 自检
    python scripts/build_manifest.py --check    # 只自检，不写文件

自检会拦下几类不该出现在公开语料里的东西：长数字串（学号/手机号）、
邮箱、以及「姓名：」「学号：」这类表单字段。
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

CHUNK_TARGET = 500

# 隐私自检规则：命中即视为失败
RISKY_PATTERNS: list[tuple[str, str]] = [
    (r"(?<!\d)\d{11,12}(?!\d)", "疑似学号/手机号"),
    (r"[\w.+-]+@[\w-]+\.[\w.]+", "疑似邮箱"),
    (r"(姓\s*名|学\s*号|指导教师|班\s*级)\s*[:：]", "表单身份字段"),
    (r"C:\\\\Users\\\\", "本机绝对路径"),
]

FRONT_RE = re.compile(r"^---\n(.*?)\n---\n", re.S)


def parse_front_matter(text: str) -> tuple[dict, str]:
    m = FRONT_RE.match(text)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        if ": " in line:
            k, v = line.split(": ", 1)
            meta[k.strip()] = v.strip()
    return meta, text[m.end():]


def scan_privacy(body: str) -> list[str]:
    hits = []
    for pattern, label in RISKY_PATTERNS:
        for m in re.finditer(pattern, body):
            hits.append(f"{label}: {m.group(0)[:40]}")
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只做自检，不写 manifest")
    args = ap.parse_args()

    project = Path(__file__).resolve().parents[1]
    raw = project / "data" / "raw"
    if not raw.exists():
        print(f"[错误] 找不到 {raw}", file=sys.stderr)
        return 2

    docs, problems = [], []
    for path in sorted(raw.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        meta, body = parse_front_matter(text)
        if not meta:
            problems.append(f"{path.name}: 缺少 front matter")
        sections = [ln for ln in body.splitlines() if ln.startswith("## ")]
        chars = len(body.strip())
        doc = {
            "doc_id": meta.get("doc_id", path.stem),
            "title": meta.get("title", path.stem),
            "doc_type": meta.get("doc_type", "讲义"),
            "course": meta.get("course", "parallel-computing"),
            "language": meta.get("language", "zh"),
            "file": f"data/raw/{path.name}",
            "chars": chars,
            "cjk": sum(1 for c in body if "\u4e00" <= c <= "\u9fff"),
            "sections": len(sections),
            "est_chunks": math.ceil(chars / CHUNK_TARGET),
        }
        docs.append(doc)
        problems.extend(f"{path.name}: {h}" for h in scan_privacy(body))
        print(f"[语料] {path.name:24} {chars:5} 字  {len(sections):2} 节  ~{doc['est_chunks']:2} 块")

    total_chars = sum(d["chars"] for d in docs)
    total_sections = sum(d["sections"] for d in docs)
    print(f"\n合计 {len(docs)} 篇 / {total_chars} 字 / {total_sections} 节 / "
          f"约 {sum(d['est_chunks'] for d in docs)} 块")

    if problems:
        print("\n[隐私自检未通过]", file=sys.stderr)
        for p in problems:
            print("  " + p, file=sys.stderr)
        return 1
    print("[隐私自检] 通过：无长数字串、无邮箱、无身份字段、无本机路径")

    if args.check:
        return 0

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "corpus": "sample-notes",
        "license": "CC-BY-4.0",
        "note": "本语料为项目原创编写的示例讲义，不含任何第三方材料与个人信息。",
        "total_chars": total_chars,
        "total_sections": total_sections,
        "docs": docs,
    }
    out = project / "data" / "manifest.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n已写出 {out.relative_to(project)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
