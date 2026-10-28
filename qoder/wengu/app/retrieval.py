"""混合检索：一条 SQL 完成向量 + 全文 + 标量过滤，RRF 融合。

要点（都由实测确定，见 docs/01-需求与方案.md §4.10）：
- 全文用自然语言模式，**不能用 BOOLEAN MODE**，否则中文整串不切分、命中恒为 0
- 参数占位符用 %(name)s，pymysql 只认这个
- 标量过滤必须写进两个支路内部，否则 ANN 退化成全表扫描
- 融合阈值 0.0099（≈1/(60+ncand+1)），低于它判为未命中
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pymysql

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.embed import embed_texts, to_sql_vector  # noqa: E402

K = 60
NCAND = 40
FUSED_FLOOR = 0.0099
COVERAGE_FLOOR = 0.25
STOP_GRAMS = {"什么", "怎么", "为何", "哪些", "可以", "是否", "问题", "适合",
              "会让", "为什", "么会", "一个", "这个", "那个"}


def _grams(text: str) -> list[str]:
    cjk = [c for c in text if "\u4e00" <= c <= "\u9fff"]
    return ["".join(cjk[i:i + 2]) for i in range(len(cjk) - 1)]


def coverage(query: str, content: str) -> float:
    """查询的实义 bigram 有多少比例出现在这段正文里。

    向量支路永远会返回 ncand 条候选，所以「融合分」不能用来判断
    「资料里到底有没有」。覆盖率才可以：问一个语料里没有的话题时，
    查询的 bigram 基本不会出现在正文里。
    """
    grams = [g for g in _grams(query) if g not in STOP_GRAMS]
    if not grams:
        return 1.0
    return sum(1 for g in grams if g in content) / len(grams)

SQL = """
WITH vec AS (
  SELECT c.id, l2_distance(c.emb, %(qvec)s) AS dist
  FROM chunks c
  WHERE c.course = %(course)s
    AND c.review_status <> 'excluded'
    AND (%(topic)s IS NULL OR c.topic = %(topic)s)
    AND (%(level)s IS NULL OR c.level = %(level)s)
  ORDER BY dist APPROXIMATE LIMIT %(ncand)s
),
ft AS (
  SELECT c.id, MATCH(c.content) AGAINST(%(q)s) AS fts
  FROM chunks c
  WHERE MATCH(c.content) AGAINST(%(q)s)
    AND c.course = %(course)s
    AND c.review_status <> 'excluded'
    AND (%(topic)s IS NULL OR c.topic = %(topic)s)
    AND (%(level)s IS NULL OR c.level = %(level)s)
  ORDER BY fts DESC
  LIMIT %(ncand)s
),
vr AS (SELECT id, ROW_NUMBER() OVER (ORDER BY dist ASC)  AS rn FROM vec),
fr AS (SELECT id, ROW_NUMBER() OVER (ORDER BY fts DESC) AS rn FROM ft),
cand AS (SELECT id FROM vr UNION SELECT id FROM fr)
SELECT c.id, c.doc_id, c.heading_path, c.topic, c.content,
       vr.rn AS vrank, fr.rn AS frank,
       COALESCE(1.0/(%(k)s + vr.rn), 0) + COALESCE(1.0/(%(k)s + fr.rn), 0) AS fused
FROM cand
LEFT JOIN vr ON vr.id = cand.id
LEFT JOIN fr ON fr.id = cand.id
JOIN chunks c ON c.id = cand.id
ORDER BY fused DESC, c.id ASC
LIMIT %(k_limit)s
"""


def connect():
    return pymysql.connect(
        host=os.getenv("SEEKDB_HOST", "127.0.0.1"),
        port=int(os.getenv("SEEKDB_PORT", "2881")),
        user=os.getenv("SEEKDB_USER", "root"),
        password=os.getenv("SEEKDB_PASSWORD", ""),
        database=os.getenv("SEEKDB_DATABASE", "wengu"),
        charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor)


def search(query: str, k: int = 5, course: str = "parallel-computing",
           topic: str | None = None, level: str | None = None) -> dict:
    t0 = time.time()
    qvec = to_sql_vector(embed_texts([query])[0])
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(SQL, {
                "qvec": qvec, "q": query, "course": course, "topic": topic,
                "level": level, "ncand": NCAND, "k": K, "k_limit": k * 3})
            rows = cur.fetchall()
    finally:
        conn.close()

    latency = int((time.time() - t0) * 1000)
    if not rows or rows[0]["fused"] < FUSED_FLOOR:
        return {"hits": [], "degraded": "empty", "latency_ms": latency,
                "note": "低于融合阈值，判为未命中"}

    # 覆盖率只用于「有没有证据」的判定，不参与排序：
    # 它是字面指标，一旦拿去重排，会把语义向量好不容易排对的顺序再打乱。
    for r in rows:
        r["coverage"] = coverage(query, (r["heading_path"] or "") + " " + r["content"])
    rows = rows[:k]

    top_cov = rows[0]["coverage"]
    if top_cov < COVERAGE_FLOOR:
        return {"hits": [], "degraded": "no_evidence", "latency_ms": latency,
                "coverage": round(top_cov, 3),
                "note": "候选与问题的词面重合过低，判为资料中未提及"}
    return {"hits": rows, "degraded": "", "latency_ms": latency,
            "coverage": round(top_cov, 3)}


def main() -> int:
    queries = sys.argv[1:] or [
        "非阻塞通信会造成死锁吗",
        "伪共享为什么会让程序变慢",
        "Amdahl 定律的加速比上限",
        "量子退火适合什么问题",
    ]
    for q in queries:
        r = search(q, k=3)
        print(f"\n查询：{q}")
        print(f"  延迟 {r['latency_ms']}ms  降级={r['degraded'] or '无'}")
        if not r["hits"]:
            print("  → 资料中未提及")
            continue
        for i, h in enumerate(r["hits"], 1):
            v = f"{h['vrank']:>2}" if h["vrank"] else " -"
            f = f"{h['frank']:>2}" if h["frank"] else " -"
            print(f"  [{i}] fused={h['fused']:.4f} v={v} f={f}  {h['heading_path'][:52]}")
            print(f"      {h['content'][:60]}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
