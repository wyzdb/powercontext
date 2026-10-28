#!/usr/bin/env python3
"""初始化 seekdb：建库、建表、灌入初始数据。

用法：
    python scripts/init_db.py              # 建库建表（幂等）
    python scripts/init_db.py --drop       # 删库重建（危险）

依赖：pymysql
参数：从 .env 读取 SEEKDB_HOST/PORT/USER/PASSWORD
"""

import argparse
import os
import sys
from pathlib import Path

import pymysql

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"


def load_env():
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        os.environ.setdefault(k, v)


DDL = """
CREATE DATABASE IF NOT EXISTS wengu
  DEFAULT CHARACTER SET utf8mb4 DEFAULT COLLATE utf8mb4_general_ci;

USE wengu;

CREATE TABLE IF NOT EXISTS kb_meta (
  k            VARCHAR(64)  NOT NULL,
  v            VARCHAR(255) NOT NULL,
  updated_at   DATETIME(0)  NOT NULL,
  PRIMARY KEY (k)
) ORGANIZATION=HEAP;

CREATE TABLE IF NOT EXISTS doc_meta (
  doc_id          VARCHAR(64)  NOT NULL,
  title           VARCHAR(200) NOT NULL,
  source_file     VARCHAR(255) NOT NULL,
  course          VARCHAR(64)  NOT NULL,
  doc_type        VARCHAR(32)  NOT NULL,
  language        VARCHAR(8)   NOT NULL DEFAULT 'zh',
  front_matter    JSON         NULL,
  char_len        INT UNSIGNED NOT NULL DEFAULT 0,
  cjk_len         INT UNSIGNED NOT NULL DEFAULT 0,
  section_count   SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  chunk_count     SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  src_mtime       DATETIME(0)  NOT NULL,
  content_sha     CHAR(40)     NOT NULL,
  ingest_status   ENUM('pending','indexed','failed','staged') NOT NULL DEFAULT 'pending',
  last_indexed_at DATETIME(0)  NULL,
  error_note      VARCHAR(500) NOT NULL DEFAULT '',
  created_at      DATETIME(0)  NOT NULL,
  updated_at      DATETIME(0)  NOT NULL,
  PRIMARY KEY (doc_id),
  UNIQUE KEY uk_doc_source (source_file),
  KEY idx_doc_status (ingest_status, course),
  KEY idx_doc_mtime  (src_mtime)
) ORGANIZATION=HEAP;

CREATE TABLE IF NOT EXISTS chunks (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  chunk_uid     CHAR(40)        NOT NULL,
  doc_id        VARCHAR(64)     NOT NULL,
  source_file   VARCHAR(255)    NOT NULL,
  section_no    SMALLINT UNSIGNED NOT NULL,
  section_heading VARCHAR(200)  NOT NULL,
  heading_path  VARCHAR(300)    NOT NULL,
  part_no       TINYINT UNSIGNED NOT NULL DEFAULT 1,
  part_count    TINYINT UNSIGNED NOT NULL DEFAULT 1,
  content       MEDIUMTEXT      NOT NULL,
  content_seg   MEDIUMTEXT      NOT NULL,
  char_len      INT UNSIGNED    NOT NULL,
  course        VARCHAR(64)     NOT NULL,
  doc_type      VARCHAR(32)     NOT NULL,
  language      VARCHAR(8)      NOT NULL DEFAULT 'zh',
  topic         ENUM('architecture','performance','mpi','openmp','design') NOT NULL,
  level         ENUM('入门','进阶') NOT NULL,
  has_code      TINYINT(1)      NOT NULL DEFAULT 0,
  formula_keys  VARCHAR(255)    NOT NULL DEFAULT '',
  review_status ENUM('ok','suspect','excluded') NOT NULL DEFAULT 'ok',
  review_note   VARCHAR(255)    NOT NULL DEFAULT '',
  emb           VECTOR(1024)    NOT NULL,
  src_mtime     DATETIME(0)     NOT NULL,
  ingested_at   DATETIME(0)     NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_chunk_uid (chunk_uid),
  KEY idx_topic_level_code (topic, level, has_code),
  KEY idx_course_doctype   (course, doc_type),
  KEY idx_doc_section      (doc_id, section_no, part_no),
  KEY idx_review           (review_status),
  KEY idx_src_file         (source_file, src_mtime),
  FULLTEXT INDEX idx_chunks_ft (content) WITH PARSER ngram,
  VECTOR INDEX idx_chunks_emb (emb)
      WITH (distance=l2, type=hnsw, lib=vsag, m=16, ef_construction=200, ef_search=64)
) ORGANIZATION=HEAP;

CREATE TABLE IF NOT EXISTS concept (
  concept_id     VARCHAR(48)  NOT NULL,
  canonical_name VARCHAR(96)  NOT NULL,
  aliases        VARCHAR(512) NOT NULL DEFAULT '',
  topic          ENUM('architecture','performance','mpi','openmp','design') NOT NULL,
  docs_span      VARCHAR(128) NOT NULL DEFAULT '',
  doc_count      TINYINT UNSIGNED NOT NULL DEFAULT 1,
  note           VARCHAR(255) NOT NULL DEFAULT '',
  PRIMARY KEY (concept_id),
  UNIQUE KEY uk_concept_name (canonical_name),
  KEY idx_concept_topic (topic, doc_count)
) ORGANIZATION=HEAP;

CREATE TABLE IF NOT EXISTS chunk_concept (
  chunk_id    BIGINT UNSIGNED NOT NULL,
  concept_id  VARCHAR(48)     NOT NULL,
  role        ENUM('primary','mention') NOT NULL DEFAULT 'mention',
  PRIMARY KEY (chunk_id, concept_id),
  KEY idx_cc_concept (concept_id, role, chunk_id),
  CONSTRAINT fk_cc_chunk   FOREIGN KEY (chunk_id)   REFERENCES chunks(id)   ON DELETE RESTRICT,
  CONSTRAINT fk_cc_concept FOREIGN KEY (concept_id) REFERENCES concept(concept_id) ON DELETE RESTRICT
) ORGANIZATION=HEAP;

CREATE TABLE IF NOT EXISTS concept_edge (
  from_id    VARCHAR(48)  NOT NULL,
  to_id      VARCHAR(48)  NOT NULL,
  edge_type  ENUM('requires','contrasts','part_of') NOT NULL,
  rationale  VARCHAR(255) NOT NULL DEFAULT '',
  PRIMARY KEY (from_id, to_id, edge_type),
  KEY idx_edge_to (to_id, edge_type),
  CONSTRAINT fk_edge_from FOREIGN KEY (from_id) REFERENCES concept(concept_id) ON DELETE RESTRICT,
  CONSTRAINT fk_edge_to   FOREIGN KEY (to_id)   REFERENCES concept(concept_id) ON DELETE RESTRICT
) ORGANIZATION=HEAP;

CREATE TABLE IF NOT EXISTS quiz_item (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  item_uid      CHAR(40)        NOT NULL,
  concept_id    VARCHAR(48)     NOT NULL,
  kind          ENUM('choice','calc','judge','short','code_review') NOT NULL,
  stem          TEXT            NOT NULL,
  options       JSON            NULL,
  answer_key    VARCHAR(500)    NOT NULL,
  rubric_points VARCHAR(1000)   NOT NULL DEFAULT '',
  grade_policy  ENUM('exact','option','set_match','llm') NOT NULL DEFAULT 'option',
  basis_chunk_ids VARCHAR(255)  NOT NULL,
  difficulty    ENUM('记忆','理解','应用','分析') NOT NULL DEFAULT '理解',
  answerable    TINYINT(1)      NOT NULL DEFAULT 1,
  review_note   VARCHAR(255)    NOT NULL DEFAULT '',
  created_at    DATETIME(0)     NOT NULL,
  updated_at    DATETIME(0)     NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_item_uid (item_uid),
  KEY idx_item_concept (concept_id, kind, answerable),
  CONSTRAINT fk_item_concept FOREIGN KEY (concept_id) REFERENCES concept(concept_id) ON DELETE RESTRICT
) ORGANIZATION=HEAP;

CREATE TABLE IF NOT EXISTS qa_log (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  learner_handle VARCHAR(32)    NOT NULL,
  query_kind    ENUM('ask','quiz_basis','today','other') NOT NULL DEFAULT 'ask',
  query_text    VARCHAR(500)    NOT NULL,
  query_sha     CHAR(40)        NOT NULL DEFAULT '',
  redacted      TINYINT(1)      NOT NULL DEFAULT 0,
  filter_course VARCHAR(64)     NULL,
  filter_topic  VARCHAR(32)     NULL,
  top_chunk_ids VARCHAR(255)    NOT NULL DEFAULT '',
  top_vrank     TINYINT UNSIGNED NULL,
  top_frank     TINYINT UNSIGNED NULL,
  fused_score   DECIMAL(9,6)    NOT NULL DEFAULT 0,
  degraded      ENUM('none','vector_only','empty','pc_unavailable') NOT NULL DEFAULT 'none',
  latency_ms    INT UNSIGNED    NOT NULL DEFAULT 0,
  answered      TINYINT(1)      NOT NULL DEFAULT 0,
  occurred_at   DATETIME(0)     NOT NULL,
  PRIMARY KEY (id),
  KEY idx_qa_learner_time (learner_handle, occurred_at),
  KEY idx_qa_degraded     (degraded, occurred_at)
) ORGANIZATION=HEAP;

CREATE TABLE IF NOT EXISTS quiz_attempt (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  learner_handle VARCHAR(32)    NOT NULL,
  item_id       BIGINT UNSIGNED NOT NULL,
  concept_id    VARCHAR(48)     NOT NULL,
  answer_text   MEDIUMTEXT      NOT NULL,
  outcome       ENUM('correct','partial','wrong','unparseable') NOT NULL,
  score         DECIMAL(4,3)    NOT NULL DEFAULT 0,
  grading_mode  ENUM('exact','option','set_match','llm') NOT NULL,
  memory_ref    CHAR(36)        NOT NULL DEFAULT '',
  memory_ok     TINYINT(1)      NOT NULL DEFAULT 1,
  latency_ms    INT UNSIGNED    NOT NULL DEFAULT 0,
  occurred_at   DATETIME(0)     NOT NULL,
  PRIMARY KEY (id),
  KEY idx_attempt_learner_time (learner_handle, occurred_at),
  KEY idx_attempt_concept      (concept_id, outcome, occurred_at),
  CONSTRAINT fk_attempt_item FOREIGN KEY (item_id) REFERENCES quiz_item(id) ON DELETE RESTRICT
) ORGANIZATION=HEAP;
"""

INIT_DATA = """
INSERT INTO kb_meta (k, v, updated_at) VALUES
  ('schema_version', '1', NOW()),
  ('embed_model', 'text-embedding-v3', NOW()),
  ('embed_dim', '1024', NOW()),
  ('chunker_version', 'h2-v1', NOW()),
  ('fulltext_parser', 'ngram', NOW()),
  ('corpus_root', 'data/raw', NOW()),
  ('corpus_manifest_sha', '', NOW())
ON DUPLICATE KEY UPDATE v=VALUES(v), updated_at=NOW();
"""


def main():
    load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--drop", action="store_true", help="删库重建（危险）")
    args = ap.parse_args()

    params = {
        "host": os.getenv("SEEKDB_HOST", "127.0.0.1"),
        "port": int(os.getenv("SEEKDB_PORT", "2881")),
        "user": os.getenv("SEEKDB_USER", "root"),
        "password": os.getenv("SEEKDB_PASSWORD", ""),
    }

    print("连接 seekdb: %s:%s" % (params["host"], params["port"]))
    conn = pymysql.connect(**params, autocommit=True, charset="utf8mb4")

    try:
        with conn.cursor() as cur:
            if args.drop:
                print("删除旧库...")
                cur.execute("DROP DATABASE IF EXISTS wengu")

            print("执行 DDL...")
            for stmt in DDL.split(";"):
                stmt = stmt.strip()
                if stmt:
                    cur.execute(stmt)

            print("写入初始数据...")
            for stmt in INIT_DATA.split(";"):
                stmt = stmt.strip()
                if stmt:
                    cur.execute(stmt)

        print("[OK] 数据库初始化完成")
        print("  库名: wengu")
        print("  表数: 9")
        print("  初始数据: kb_meta 7 行")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
