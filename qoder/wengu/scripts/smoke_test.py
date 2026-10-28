#!/usr/bin/env python3
"""seekdb 连通性与 wengu 库结构自检。

只做三件事：连上 seekdb、确认 wengu 库在、确认 9 张业务表都在并打出行数。
连接参数一律来自 .env（同名环境变量优先），不硬编码。依赖只有 pymysql。
"""

import os
import sys

import pymysql

EXPECTED_TABLES = (
    "kb_meta",
    "doc_meta",
    "chunks",
    "concept",
    "chunk_concept",
    "concept_edge",
    "quiz_item",
    "qa_log",
    "quiz_attempt",
)

REQUIRED_KEYS = ("SEEKDB_HOST", "SEEKDB_PORT", "SEEKDB_USER")

ENV_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"
)


class ProbeError(Exception):
    """失败信息统一包成人话，由 main 打印并以退出码 1 结束。"""


def describe(params):
    return "host=%s port=%s user=%s password=%s" % (
        params["host"],
        params["port"],
        params["user"],
        "<set>" if params["password"] else "<empty>",
    )


def load_env_file(path):
    """极简 .env 解析：KEY=VALUE，# 开头为注释，剥掉值两侧的成对引号。"""
    if not os.path.isfile(path):
        raise ProbeError("未找到 .env: %s\n      先执行: cp .env.example .env 并按本机情况填写" % path)
    cfg = {}
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                raise ProbeError(".env 第 %d 行不是 KEY=VALUE 形式: %s" % (lineno, line))
            key, value = line.split("=", 1)
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            cfg[key.strip()] = value
    return cfg


def resolve_params():
    cfg = load_env_file(ENV_PATH)
    merged = {k: os.environ.get(k, v) for k, v in cfg.items()}
    missing = [k for k in REQUIRED_KEYS if not merged.get(k)]
    if missing:
        raise ProbeError(".env 缺少必填项: %s（文件: %s）" % (", ".join(missing), ENV_PATH))
    try:
        port = int(merged["SEEKDB_PORT"])
    except ValueError:
        raise ProbeError("SEEKDB_PORT 必须是整数，当前读到 %r" % merged["SEEKDB_PORT"])
    params = {
        "host": merged["SEEKDB_HOST"],
        "port": port,
        "user": merged["SEEKDB_USER"],
        "password": merged.get("SEEKDB_PASSWORD", ""),
    }
    database = merged.get("SEEKDB_DATABASE") or "wengu"
    return params, database


def connect(params):
    try:
        return pymysql.connect(
            host=params["host"],
            port=params["port"],
            user=params["user"],
            password=params["password"],
            connect_timeout=5,
            read_timeout=10,
            write_timeout=10,
            autocommit=True,
        )
    except pymysql.MySQLError as exc:
        raise ProbeError("连不上 seekdb: %s\n      实际参数: %s" % (exc, describe(params)))


def check_database(conn, params, database):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = %s",
            (database,),
        )
        if not cur.fetchone():
            raise ProbeError(
                "数据库不存在: %s\n      实际参数: %s" % (database, describe(params))
            )
    print("database: ok %s" % database)


def list_tables(conn, params, database):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT TABLE_NAME FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = %s ORDER BY TABLE_NAME",
            (database,),
        )
        return [row[0] for row in cur.fetchall()]


def row_count(conn, params, database, table):
    # 行数一律用 COUNT(*)：information_schema.TABLES.TABLE_ROWS 在 seekdb 上是估算值，
    # 实测 kb_meta 有 7 行时它报 0，拿它验收会假绿。
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM `%s`.`%s`" % (database, table)
            )
            return cur.fetchone()[0]
    except pymysql.MySQLError as exc:
        raise ProbeError("统计表 %s.%s 行数失败: %s" % (database, table, exc))


def check_tables(conn, params, database):
    actual = set(list_tables(conn, params, database))
    expected = set(EXPECTED_TABLES)

    missing = sorted(expected - actual)
    if missing:
        raise ProbeError(
            "缺表 %d 张: %s\n      实际参数: %s\n      库里现有的表: %s"
            % (len(missing), ", ".join(missing), describe(params), ", ".join(sorted(actual)) or "<无>")
        )

    for table in EXPECTED_TABLES:
        print("table: ok %-14s rows=%d" % (table, row_count(conn, params, database, table)))

    print("tables: ok %d/%d present" % (len(EXPECTED_TABLES), len(EXPECTED_TABLES)))

    extra = sorted(actual - expected)
    if extra:
        print("warn: 库里有 %d 张计划外的表: %s" % (len(extra), ", ".join(extra)))
        print("warn: 不影响本次验收，但请确认是否为调试遗留表，是的话手动 DROP")


def main():
    try:
        params, database = resolve_params()
    except ProbeError as exc:
        print("FAIL: %s" % exc)
        return 1

    conn = None
    try:
        conn = connect(params)
        with conn.cursor() as cur:
            cur.execute("SELECT VERSION()")
            version = cur.fetchone()[0]
        print("seekdb: ok %s" % describe(params))
        print("server: ok version=%s" % version)
        check_database(conn, params, database)
        check_tables(conn, params, database)
        return 0
    except ProbeError as exc:
        print("FAIL: %s" % exc)
        return 1
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    sys.exit(main())
