"""seekdb persistence for the SDD index, task records and query journal.

The store uses the MySQL wire protocol, so the same code runs against seekdb and
OceanBase MySQL mode. Every read that feeds task context is recorded in
``sdd_query_log`` and mirrored to ``records/seekdb/queries.jsonl`` so the
submitted record shows which database rows were actually used.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pymysql

from sdd_context.config import Settings
from sdd_context.models import IndexBundle, Match, TaskState

TABLES = (
    "sdd_specs",
    "sdd_spec_clauses",
    "sdd_code_symbols",
    "sdd_tests",
    "sdd_terms",
    "sdd_tasks",
    "sdd_task_events",
    "sdd_contexts",
    "sdd_config",
    "sdd_query_log",
)

DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS sdd_specs (
        spec_id VARCHAR(64) NOT NULL,
        title VARCHAR(255) NOT NULL,
        version INT NOT NULL,
        status VARCHAR(32) NOT NULL,
        path VARCHAR(255) NOT NULL,
        applies_to VARCHAR(2048) NOT NULL,
        verified_by VARCHAR(2048) NOT NULL,
        content_sha CHAR(64) NOT NULL,
        updated_at DATETIME NOT NULL,
        PRIMARY KEY (spec_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS sdd_spec_clauses (
        clause_id VARCHAR(96) NOT NULL,
        spec_id VARCHAR(64) NOT NULL,
        spec_title VARCHAR(255) NOT NULL,
        version INT NOT NULL,
        status VARCHAR(32) NOT NULL,
        ordinal INT NOT NULL,
        heading VARCHAR(255) NOT NULL,
        body TEXT NOT NULL,
        path VARCHAR(255) NOT NULL,
        line_start INT NOT NULL,
        line_end INT NOT NULL,
        applies_to VARCHAR(2048) NOT NULL,
        verified_by VARCHAR(2048) NOT NULL,
        PRIMARY KEY (clause_id),
        KEY idx_clause_spec (spec_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS sdd_code_symbols (
        symbol_id VARCHAR(200) NOT NULL,
        path VARCHAR(255) NOT NULL,
        qualified_name VARCHAR(200) NOT NULL,
        kind VARCHAR(16) NOT NULL,
        line_start INT NOT NULL,
        line_end INT NOT NULL,
        signature VARCHAR(1024) NOT NULL,
        doc TEXT NOT NULL,
        source_sha CHAR(64) NOT NULL,
        PRIMARY KEY (symbol_id),
        KEY idx_symbol_path (path)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS sdd_tests (
        test_id VARCHAR(320) NOT NULL,
        path VARCHAR(255) NOT NULL,
        name VARCHAR(255) NOT NULL,
        kind VARCHAR(16) NOT NULL,
        spec_refs VARCHAR(1024) NOT NULL,
        code_refs VARCHAR(1024) NOT NULL,
        doc TEXT NOT NULL,
        line_start INT NOT NULL,
        line_end INT NOT NULL,
        PRIMARY KEY (test_id),
        KEY idx_test_kind (kind)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS sdd_terms (
        term VARCHAR(64) NOT NULL,
        ref_kind VARCHAR(8) NOT NULL,
        ref_id VARCHAR(320) NOT NULL,
        weight INT NOT NULL,
        PRIMARY KEY (term, ref_kind, ref_id),
        KEY idx_term_lookup (term)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS sdd_tasks (
        task_id VARCHAR(64) NOT NULL,
        title VARCHAR(255) NOT NULL,
        task_text TEXT NOT NULL,
        status VARCHAR(32) NOT NULL,
        step VARCHAR(64) NOT NULL,
        context_id VARCHAR(64) NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        PRIMARY KEY (task_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS sdd_task_events (
        event_id BIGINT NOT NULL AUTO_INCREMENT,
        task_id VARCHAR(64) NOT NULL,
        phase VARCHAR(32) NOT NULL,
        status VARCHAR(32) NOT NULL,
        detail LONGTEXT NOT NULL,
        created_at DATETIME NOT NULL,
        PRIMARY KEY (event_id),
        KEY idx_event_task (task_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS sdd_contexts (
        context_id VARCHAR(64) NOT NULL,
        task_id VARCHAR(64) NOT NULL,
        payload LONGTEXT NOT NULL,
        created_at DATETIME NOT NULL,
        PRIMARY KEY (context_id),
        KEY idx_context_task (task_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS sdd_config (
        config_key VARCHAR(64) NOT NULL,
        config_value TEXT NOT NULL,
        PRIMARY KEY (config_key)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS sdd_query_log (
        query_id BIGINT NOT NULL AUTO_INCREMENT,
        task_id VARCHAR(64) NULL,
        purpose VARCHAR(64) NOT NULL,
        sql_sha CHAR(64) NOT NULL,
        sql_text TEXT NOT NULL,
        params_digest VARCHAR(128) NOT NULL,
        row_count INT NOT NULL,
        duration_ms INT NOT NULL,
        created_at DATETIME NOT NULL,
        PRIMARY KEY (query_id),
        KEY idx_query_task (task_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_id(prefix: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    digest = hashlib.sha1(f"{stamp}-{time.time_ns()}".encode()).hexdigest()[:6]
    return f"{prefix}-{stamp}-{digest}"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class SeekdbStore:
    """Thin, synchronous access layer over seekdb."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.last_query_stats: list[dict[str, Any]] = []

    # -- connection -----------------------------------------------------
    def _connect(self, database: str | None) -> pymysql.connections.Connection:
        import pymysql
        from pymysql.cursors import DictCursor

        return pymysql.connect(
            host=self.settings.db_host,
            port=self.settings.db_port,
            user=self.settings.db_user,
            password=self.settings.db_password,
            database=database,
            charset="utf8mb4",
            cursorclass=DictCursor,
            autocommit=False,
            connect_timeout=10,
        )

    def ensure_database(self) -> None:
        connection = self._connect(None)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"CREATE DATABASE IF NOT EXISTS `{self.settings.db_database}` "
                    "DEFAULT CHARACTER SET utf8mb4"
                )
            connection.commit()
        finally:
            connection.close()

    def ensure_schema(self) -> None:
        self.ensure_database()
        connection = self._connect(self.settings.db_database)
        try:
            with connection.cursor() as cursor:
                for statement in DDL:
                    cursor.execute(statement)
            connection.commit()
        finally:
            connection.close()

    def reset(self) -> None:
        self.ensure_database()
        connection = self._connect(self.settings.db_database)
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET FOREIGN_KEY_CHECKS=0")
                for table in TABLES:
                    cursor.execute(f"DROP TABLE IF EXISTS `{table}`")
            connection.commit()
        finally:
            connection.close()
        self.ensure_schema()

    # -- index ----------------------------------------------------------
    def replace_index(self, bundle: IndexBundle) -> dict[str, int]:
        connection = self._connect(self.settings.db_database)
        now = utc_now()
        try:
            with connection.cursor() as cursor:
                for table in (
                    "sdd_terms",
                    "sdd_tests",
                    "sdd_code_symbols",
                    "sdd_spec_clauses",
                    "sdd_specs",
                ):
                    cursor.execute(f"DELETE FROM `{table}`")

                for spec in bundle.specs:
                    body = "\n".join(
                        f"{clause.clause_id} {clause.heading}\n{clause.body}"
                        for clause in spec.clauses
                    )
                    cursor.execute(
                        "INSERT INTO sdd_specs (spec_id, title, version, status, path, "
                        "applies_to, verified_by, content_sha, updated_at) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        (
                            spec.spec_id,
                            spec.title,
                            spec.version,
                            spec.status,
                            spec.path,
                            ",".join(spec.applies_to),
                            ",".join(spec.verified_by),
                            _sha(body),
                            now,
                        ),
                    )

                for clause in bundle.clauses:
                    cursor.execute(
                        "INSERT INTO sdd_spec_clauses (clause_id, spec_id, spec_title, version, "
                        "status, ordinal, heading, body, path, line_start, line_end, applies_to, "
                        "verified_by) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        (
                            clause.clause_id,
                            clause.spec_id,
                            clause.spec_title,
                            clause.version,
                            clause.status,
                            clause.ordinal,
                            clause.heading[:255],
                            clause.body,
                            clause.path,
                            clause.line_start,
                            clause.line_end,
                            ",".join(clause.applies_to),
                            ",".join(clause.verified_by),
                        ),
                    )

                for symbol in bundle.symbols:
                    cursor.execute(
                        "INSERT INTO sdd_code_symbols (symbol_id, path, qualified_name, kind, "
                        "line_start, line_end, signature, doc, source_sha) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        (
                            symbol.symbol_id,
                            symbol.path,
                            symbol.qualified_name,
                            symbol.kind,
                            symbol.line_start,
                            symbol.line_end,
                            symbol.signature[:1024],
                            symbol.doc,
                            _sha(symbol.qualified_name + symbol.signature + symbol.doc),
                        ),
                    )

                for test in bundle.tests:
                    cursor.execute(
                        "INSERT INTO sdd_tests (test_id, path, name, kind, spec_refs, code_refs, "
                        "doc, line_start, line_end) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        (
                            test.test_id,
                            test.path,
                            test.name,
                            test.kind,
                            ",".join(test.spec_refs),
                            ",".join(test.code_refs),
                            test.doc,
                            test.line_start,
                            test.line_end,
                        ),
                    )

                cursor.executemany(
                    "INSERT INTO sdd_terms (term, ref_kind, ref_id, weight) VALUES (%s, %s, %s, %s)",
                    [(row.term, row.ref_kind, row.ref_id, row.weight) for row in bundle.terms],
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return bundle.stats()

    # -- selection ------------------------------------------------------
    def search_terms(self, terms: Sequence[str], limit: int = 40, task_id: str | None = None) -> list[Match]:
        if not terms:
            return []
        placeholders = ", ".join(["%s"] * len(terms))
        sql = (
            "SELECT ref_kind, ref_id, SUM(weight) AS score, COUNT(*) AS hits "
            "FROM sdd_terms WHERE term IN (" + placeholders + ") "
            "GROUP BY ref_kind, ref_id ORDER BY score DESC, hits DESC, ref_kind, ref_id LIMIT %s"
        )
        params = [*terms, limit]
        rows = self._read(sql, params, purpose="select.terms", task_id=task_id)
        return [
            Match(
                ref_kind=str(row["ref_kind"]),
                ref_id=str(row["ref_id"]),
                score=int(row["score"]),
                hits=int(row["hits"]),
            )
            for row in rows
        ]

    def load_clauses(self, clause_ids: Sequence[str], task_id: str | None = None) -> list[dict[str, Any]]:
        if not clause_ids:
            return []
        placeholders = ", ".join(["%s"] * len(clause_ids))
        sql = (
            "SELECT clause_id, spec_id, spec_title, version, status, ordinal, heading, body, "
            "line_start, line_end, applies_to, verified_by, path FROM sdd_spec_clauses "
            f"WHERE clause_id IN ({placeholders}) ORDER BY clause_id"
        )
        return self._read(sql, list(clause_ids), purpose="select.clauses", task_id=task_id)

    def load_symbols(self, symbol_ids: Sequence[str], task_id: str | None = None) -> list[dict[str, Any]]:
        if not symbol_ids:
            return []
        placeholders = ", ".join(["%s"] * len(symbol_ids))
        sql = (
            "SELECT symbol_id, path, qualified_name, kind, line_start, line_end, signature, doc "
            f"FROM sdd_code_symbols WHERE symbol_id IN ({placeholders}) ORDER BY symbol_id"
        )
        return self._read(sql, list(symbol_ids), purpose="select.symbols", task_id=task_id)

    def load_tests(self, test_ids: Sequence[str], task_id: str | None = None) -> list[dict[str, Any]]:
        if not test_ids:
            return []
        placeholders = ", ".join(["%s"] * len(test_ids))
        sql = (
            "SELECT test_id, path, name, kind, spec_refs, code_refs, doc, line_start, line_end "
            f"FROM sdd_tests WHERE test_id IN ({placeholders}) ORDER BY test_id"
        )
        return self._read(sql, list(test_ids), purpose="select.tests", task_id=task_id)

    def tests_for_specs(self, spec_ids: Sequence[str], task_id: str | None = None) -> list[dict[str, Any]]:
        if not spec_ids:
            return []
        like = [f"%{spec_id}%" for spec_id in spec_ids]
        clause = " OR ".join(["spec_refs LIKE %s"] * len(like))
        sql = (
            "SELECT test_id, path, name, kind, spec_refs, code_refs, doc, line_start, line_end "
            f"FROM sdd_tests WHERE {clause} ORDER BY kind, test_id"
        )
        return self._read(sql, like, purpose="select.tests_for_specs", task_id=task_id)

    def tests_for_symbols(self, symbol_ids: Sequence[str], task_id: str | None = None) -> list[dict[str, Any]]:
        if not symbol_ids:
            return []
        like = [f"%{symbol_id}%" for symbol_id in symbol_ids]
        clause = " OR ".join(["code_refs LIKE %s"] * len(like))
        sql = (
            "SELECT test_id, path, name, kind, spec_refs, code_refs, doc, line_start, line_end "
            f"FROM sdd_tests WHERE {clause} ORDER BY kind, test_id"
        )
        return self._read(sql, like, purpose="select.tests_for_symbols", task_id=task_id)

    # -- task records ---------------------------------------------------
    def upsert_task(self, state: TaskState, task_text: str) -> None:
        connection = self._connect(self.settings.db_database)
        now = utc_now()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO sdd_tasks (task_id, title, task_text, status, step, context_id, "
                    "created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON DUPLICATE KEY UPDATE title=VALUES(title), status=VALUES(status), "
                    "step=VALUES(step), context_id=VALUES(context_id), updated_at=VALUES(updated_at)",
                    (
                        state.task_id,
                        state.title[:255],
                        task_text,
                        state.status,
                        state.step,
                        state.context_id,
                        now,
                        now,
                    ),
                )
            connection.commit()
        finally:
            connection.close()

    def add_event(self, task_id: str, phase: str, status: str, detail: dict[str, Any]) -> None:
        connection = self._connect(self.settings.db_database)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO sdd_task_events (task_id, phase, status, detail, created_at) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (task_id, phase, status, json.dumps(detail, ensure_ascii=False), utc_now()),
                )
            connection.commit()
        finally:
            connection.close()

    def save_context(self, context_id: str, task_id: str, payload: dict[str, Any]) -> None:
        connection = self._connect(self.settings.db_database)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO sdd_contexts (context_id, task_id, payload, created_at) "
                    "VALUES (%s, %s, %s, %s) ON DUPLICATE KEY UPDATE payload=VALUES(payload)",
                    (context_id, task_id, json.dumps(payload, ensure_ascii=False), utc_now()),
                )
            connection.commit()
        finally:
            connection.close()

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        rows = self._read(
            "SELECT task_id, title, task_text, status, step, context_id, created_at, updated_at "
            "FROM sdd_tasks WHERE task_id = %s",
            [task_id],
            purpose="select.task",
            task_id=task_id,
        )
        return rows[0] if rows else None

    def list_tasks(self, limit: int = 20) -> list[dict[str, Any]]:
        return self._read(
            "SELECT task_id, title, status, step, context_id, updated_at FROM sdd_tasks "
            "ORDER BY updated_at DESC LIMIT %s",
            [limit],
            purpose="select.tasks",
        )

    def task_events(self, task_id: str) -> list[dict[str, Any]]:
        return self._read(
            "SELECT phase, status, detail, created_at FROM sdd_task_events "
            "WHERE task_id = %s ORDER BY event_id",
            [task_id],
            purpose="select.task_events",
            task_id=task_id,
        )

    def delete_task(self, task_id: str) -> dict[str, int]:
        """Remove one task, its events and its context snapshots."""

        deleted: dict[str, int] = {}
        connection = self._connect(self.settings.db_database)
        try:
            with connection.cursor() as cursor:
                for table in ("sdd_task_events", "sdd_contexts", "sdd_tasks"):
                    cursor.execute(f"DELETE FROM `{table}` WHERE task_id = %s", (task_id,))
                    deleted[table] = cursor.rowcount
            connection.commit()
        finally:
            connection.close()
        return deleted

    # -- config ---------------------------------------------------------
    def get_config(self, key: str) -> str | None:
        rows = self._read(
            "SELECT config_value FROM sdd_config WHERE config_key = %s",
            [key],
            purpose="select.config",
        )
        return str(rows[0]["config_value"]) if rows else None

    def set_config(self, key: str, value: str) -> None:
        connection = self._connect(self.settings.db_database)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO sdd_config (config_key, config_value) VALUES (%s, %s) "
                    "ON DUPLICATE KEY UPDATE config_value=VALUES(config_value)",
                    (key, value),
                )
            connection.commit()
        finally:
            connection.close()

    # -- internals ------------------------------------------------------
    def _read(
        self,
        sql: str,
        params: Iterable[Any],
        *,
        purpose: str,
        task_id: str | None = None,
    ) -> list[dict[str, Any]]:
        params = list(params)
        connection = self._connect(self.settings.db_database)
        started = time.perf_counter()
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                rows = list(cursor.fetchall())
        finally:
            connection.close()
        duration_ms = int((time.perf_counter() - started) * 1000)
        record = {
            "purpose": purpose,
            "sql_sha": _sha(sql),
            "sql": sql,
            "params": params,
            "row_count": len(rows),
            "duration_ms": duration_ms,
            "task_id": task_id,
            "at": datetime.now(timezone.utc).isoformat(),
        }
        self.last_query_stats.append(record)
        self._log_query(record)
        return rows

    def _log_query(self, record: dict[str, Any]) -> None:
        try:
            connection = self._connect(self.settings.db_database)
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO sdd_query_log (task_id, purpose, sql_sha, sql_text, "
                        "params_digest, row_count, duration_ms, created_at) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                        (
                            record["task_id"],
                            record["purpose"],
                            record["sql_sha"],
                            record["sql"],
                            _sha(json.dumps(record["params"], default=str))[:64],
                            record["row_count"],
                            record["duration_ms"],
                            utc_now(),
                        ),
                    )
                connection.commit()
            finally:
                connection.close()
        except Exception:
            # Query journaling must never break a read path.
            pass
        try:
            directory: Path = self.settings.records_dir / "seekdb"
            directory.mkdir(parents=True, exist_ok=True)
            with (directory / "queries.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            pass
