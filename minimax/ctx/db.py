"""seekdb 访问层：建库建表 + 连接。

seekdb 兼容 MySQL 协议，这里直接用 pymysql。所有 SQL 都落在本文件，
方便在"技术使用记录"里逐条核对。
"""

from __future__ import annotations

import pymysql
from pymysql.cursors import DictCursor

from .config import DBConfig

SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS documents (
        id         BIGINT AUTO_INCREMENT PRIMARY KEY,
        doc_key    VARCHAR(191) NOT NULL,
        kind       VARCHAR(16)  NOT NULL,
        path       VARCHAR(512) NOT NULL,
        title      VARCHAR(255) NOT NULL,
        content    MEDIUMTEXT   NOT NULL,
        sha256     CHAR(64)     NOT NULL,
        meta       LONGTEXT     NULL,
        updated_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uk_doc_key (doc_key),
        KEY idx_kind (kind)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS spec_refs (
        id          BIGINT AUTO_INCREMENT PRIMARY KEY,
        spec_key    VARCHAR(191) NOT NULL,
        target_path VARCHAR(512) NOT NULL,
        relation    VARCHAR(32)  NOT NULL,
        UNIQUE KEY uk_ref (spec_key, target_path, relation)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS task_state (
        id         BIGINT AUTO_INCREMENT PRIMARY KEY,
        task_id    VARCHAR(64)  NOT NULL,
        stage      VARCHAR(64)  NOT NULL,
        payload    LONGTEXT     NOT NULL,
        updated_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uk_task (task_id)
    )
    """,
)


def connect(cfg: DBConfig | None = None, *, with_database: bool = True) -> pymysql.connections.Connection:
    cfg = cfg or DBConfig.from_env()
    return pymysql.connect(
        host=cfg.host,
        port=cfg.port,
        user=cfg.user,
        password=cfg.password,
        database=cfg.database if with_database else None,
        charset="utf8mb4",
        autocommit=True,
        cursorclass=DictCursor,
        connect_timeout=10,
    )


def ensure_schema(cfg: DBConfig | None = None) -> None:
    """创建数据库与表（幂等）。"""

    cfg = cfg or DBConfig.from_env()

    conn = connect(cfg, with_database=False)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{cfg.database}` "
                "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci"
            )
    finally:
        conn.close()

    conn = connect(cfg)
    try:
        with conn.cursor() as cur:
            for statement in SCHEMA_STATEMENTS:
                cur.execute(statement)
    finally:
        conn.close()
