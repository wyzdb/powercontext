#!/usr/bin/env python
"""把 seekdb 的实际查询与结果落盘，作为「数据库实际参与」的证据。

用法::

    python scripts/dump_sql_evidence.py

输出：``records/seekdb-queries.log``
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ctx import db, importer  # noqa: E402
from ctx.retrieve import tokenize  # noqa: E402

OUT = ROOT / "records" / "seekdb-queries.log"


def connect():
    return db.connect()


def main() -> int:
    task = "为任务列表增加按标签筛选"
    tokens = tokenize(task)
    importer.search_specs(tokens)  # 触发一次真实检索，记下 SQL

    lines: list[str] = [
        f"# seekdb 查询记录",
        f"# 时间: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"# 目标: {db.DBConfig.from_env().host}:{db.DBConfig.from_env().port}/{db.DBConfig.from_env().database}",
        "",
    ]

    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT VERSION() AS v")
            lines.append(f"-- SELECT VERSION()\n{cur.fetchone()['v']}\n")

            cur.execute("SHOW TABLES")
            tables = [list(row.values())[0] for row in cur.fetchall()]
            lines.append(f"-- SHOW TABLES\n{tables}\n")

            cur.execute("SELECT kind, COUNT(*) AS n FROM documents GROUP BY kind ORDER BY kind")
            lines.append(f"-- SELECT kind, COUNT(*) ... GROUP BY kind\n{cur.fetchall()}\n")

            cur.execute("SELECT doc_key, path, title, sha256 FROM documents ORDER BY kind, path")
            for row in cur.fetchall():
                lines.append(f"   {row['doc_key']:<28} {row['path']:<34} {row['sha256'][:12]}")
            lines.append("")

            cur.execute(
                "SELECT spec_key, target_path, relation FROM spec_refs WHERE spec_key = %s ORDER BY relation, target_path",
                ("SPEC-002",),
            )
            lines.append("-- SELECT ... FROM spec_refs WHERE spec_key='SPEC-002'")
            for row in cur.fetchall():
                lines.append(f"   {row['spec_key']:<10} {row['relation']:<10} {row['target_path']}")
            lines.append("")
    finally:
        conn.close()

    query = importer.last_query()
    lines.append("-- 检索规格时实际执行的 SQL")
    lines.append(query.get("sql", ""))
    lines.append(f"-- 参数: {json.dumps(query.get('params', []), ensure_ascii=False)}")
    lines.append(f"-- 命中行数: {query.get('rows')}")
    lines.append("-- 命中规格: " + ", ".join(doc["doc_key"] for doc in importer.search_specs(tokens)))

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"written: {OUT}")
    print("\n".join(lines[:12]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
