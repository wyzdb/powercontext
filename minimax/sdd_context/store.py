"""Document store for SDD engineering material.

The preferred backend is embedded seekdb.  A SQLite backend is kept for unit
tests and for environments where the Linux-only seekdb binding is unavailable;
the selected backend is recorded in every context response.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

STOPWORDS = frozenset(
    "a an and are as at be by for from has have in is it its of on or that the their this to was were what when where which who with".split()
)


@dataclass(frozen=True)
class Document:
    doc_id: str
    version: int
    kind: str
    path: str
    symbol: str | None
    text: str

    def as_context(self) -> dict[str, Any]:
        return {
            "id": self.doc_id,
            "kind": self.kind,
            "path": self.path,
            "symbol": self.symbol,
            "version": self.version,
            "source": f"seekdb://sdd_documents/{self.doc_id}/v{self.version}"
            if self.kind != "spec"
            else f"seekdb://sdd_documents/{self.doc_id}/v{self.version}",
            "text": self.text,
        }


def terms(text: str) -> list[str]:
    return [word for word in re.findall(r"[a-z0-9]+", text.casefold()) if len(word) > 2 and word not in STOPWORDS]


class DocumentStore:
    """Versioned document table backed by seekdb or SQLite."""

    def __init__(self, root: Path, *, backend: str | None = None, db_path: Path | None = None) -> None:
        self.root = root
        self.backend = (backend or os.environ.get("SDD_STORE_BACKEND") or "seekdb").lower()
        self.db_path = db_path or root / ".sdd" / "store"
        self._instance: Any = None
        self._connection: Any = None
        if self.backend == "seekdb":
            try:
                self._open_seekdb()
            except Exception as error:  # pragma: no cover - exercised on non-seekdb hosts
                self.backend = "sqlite"
                self.fallback_reason = f"{type(error).__name__}: {error}"
        if self.backend == "sqlite":
            self.sqlite_path = root / ".sdd" / "sdd.sqlite3"
            self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(self.sqlite_path)
        self._create_schema()

    # -- connections -------------------------------------------------
    def _open_seekdb(self) -> None:
        import pylibseekdb  # type: ignore[import-not-found]

        self.db_path.mkdir(parents=True, exist_ok=True)
        self._instance = asyncio.run(pylibseekdb.aopen(str(self.db_path)))
        options = dict(self._instance.connection_options())
        import pymysql  # type: ignore[import-not-found]

        self._connection = pymysql.connect(
            host=options.get("host", "127.0.0.1"),
            port=int(options.get("port", 2881)),
            user=options.get("user", "root"),
            password=options.get("password") or "",
            database=options.get("database", "test"),
            autocommit=True,
            charset="utf8mb4",
        )

    def _placeholder(self) -> str:
        return "%s" if self.backend == "seekdb" else "?"

    def _create_schema(self) -> None:
        statement = """
        CREATE TABLE IF NOT EXISTS sdd_documents (
            doc_id VARCHAR(128) NOT NULL,
            version INT NOT NULL,
            kind VARCHAR(32) NOT NULL,
            path VARCHAR(512) NOT NULL,
            symbol VARCHAR(256) NULL,
            text LONGTEXT NOT NULL,
            PRIMARY KEY (doc_id, version)
        )
        """
        cursor = self._connection.cursor()
        cursor.execute(statement)
        self._connection.commit()

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
        if self._instance is not None:
            self._instance.close()

    # -- import -------------------------------------------------------
    def import_documents(self, documents: Iterable[Document]) -> int:
        placeholder = self._placeholder()
        sql = (
            f"INSERT INTO sdd_documents (doc_id, version, kind, path, symbol, text) "
            f"VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}) "
            f"ON DUPLICATE KEY UPDATE kind=VALUES(kind), path=VALUES(path), symbol=VALUES(symbol), text=VALUES(text)"
            if self.backend == "seekdb"
            else f"INSERT OR REPLACE INTO sdd_documents (doc_id, version, kind, path, symbol, text) "
            f"VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})"
        )
        cursor = self._connection.cursor()
        count = 0
        for document in documents:
            cursor.execute(
                sql,
                (
                    document.doc_id,
                    document.version,
                    document.kind,
                    document.path,
                    document.symbol,
                    document.text,
                ),
            )
            count += 1
        self._connection.commit()
        return count

    def import_tree(self) -> int:
        """Import specs, code and tests from the documented data directories."""

        documents: list[Document] = []
        for path in sorted((self.root / "data" / "specs").glob("*.md")):
            text = path.read_text(encoding="utf-8")
            version = _version_from_spec(text)
            documents.append(Document(path.stem, version, "spec", str(path.relative_to(self.root)), None, text))
        for path in sorted((self.root / "data" / "code").glob("*.py")):
            text = path.read_text(encoding="utf-8")
            documents.append(Document(f"code:{path.stem}", 1, "code", str(path.relative_to(self.root)), "approve", text))
        for path in sorted((self.root / "data" / "tests").glob("*.py")):
            text = path.read_text(encoding="utf-8")
            documents.append(Document(f"test:{path.stem}", 1, "test", str(path.relative_to(self.root)), "test_", text))
        return self.import_documents(documents)

    def latest(self) -> list[Document]:
        sql = """
        SELECT d.doc_id, d.version, d.kind, d.path, d.symbol, d.text
        FROM sdd_documents d
        JOIN (SELECT doc_id, MAX(version) AS version FROM sdd_documents GROUP BY doc_id) latest
          ON latest.doc_id = d.doc_id AND latest.version = d.version
        ORDER BY d.kind, d.doc_id
        """
        cursor = self._connection.cursor()
        cursor.execute(sql)
        return [Document(*row) for row in cursor.fetchall()]

    def search(self, query: str, *, per_kind: int = 3) -> dict[str, list[Document]]:
        query_terms = terms(query)
        if self.backend == "seekdb":
            # The database performs the candidate filter; ranking stays deterministic in the module.
            cursor = self._connection.cursor()
            cursor.execute(
                "SELECT doc_id, version, kind, path, symbol, text FROM sdd_documents "
                "WHERE text LIKE %s OR path LIKE %s LIMIT 500",
                (f"%{query_terms[0] if query_terms else query}%", f"%{query_terms[0] if query_terms else query}%"),
            )
            candidates = [Document(*row) for row in cursor.fetchall()]
        else:
            candidates = self.latest()

        latest: dict[str, Document] = {}
        for document in candidates:
            current = latest.get(document.doc_id)
            if current is None or document.version > current.version:
                latest[document.doc_id] = document
        selected: dict[str, list[Document]] = {"spec": [], "code": [], "test": []}
        for document in sorted(latest.values(), key=lambda item: item.doc_id):
            text_terms = set(terms(document.text))
            score = sum(1 for term in query_terms if term in text_terms)
            if score == 0 and document.kind != "spec":
                continue
            selected.setdefault(document.kind, []).append((score, document))  # type: ignore[arg-type]
        result: dict[str, list[Document]] = {}
        for kind, entries in selected.items():
            ordered = sorted(entries, key=lambda item: (-item[0], item[1].doc_id))  # type: ignore[index]
            result[kind] = [item[1] for item in ordered[:per_kind]]  # type: ignore[index]
        return result

    @property
    def source(self) -> str:
        if self.backend == "seekdb":
            return f"seekdb://{self.db_path}"
        return f"sqlite://{self.sqlite_path}"


def _version_from_spec(text: str) -> int:
    match = re.search(r"^-\s*Version:\s*(\d+)\s*$", text, re.MULTILINE)
    return int(match.group(1)) if match else 1
