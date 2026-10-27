"""Note storage for ResearchFlow, backed by seekdb or SQLite."""

from __future__ import annotations

import asyncio
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

STOPWORDS = frozenset(
    "a an and are as at be by for from has have in is it its of on or that the their this to was were what when where which who with".split()
)


def terms(text: str) -> list[str]:
    return [word for word in re.findall(r"[a-z0-9]+", text.casefold()) if len(word) > 2 and word not in STOPWORDS]


@dataclass(frozen=True)
class Note:
    note_id: str
    title: str
    content: str
    tags: str
    created_at: str


class NoteStore:
    def __init__(self, root: Path, *, backend: str | None = None) -> None:
        self.root = root
        self.backend = (backend or os.environ.get("RF_STORE_BACKEND") or "seekdb").lower()
        self.db_path = root / ".qoder" / "store"
        self._instance: Any = None
        self._connection: Any = None
        if self.backend == "seekdb":
            try:
                self._open_seekdb()
            except Exception:
                self.backend = "sqlite"
        if self.backend == "sqlite":
            self.sqlite_path = root / ".qoder" / "researchflow.sqlite3"
            self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(self.sqlite_path, check_same_thread=False)
        self._create()

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

    def _create(self) -> None:
        self._connection.cursor().execute(
            """
            CREATE TABLE IF NOT EXISTS rf_notes (
                note_id VARCHAR(128) NOT NULL PRIMARY KEY,
                title VARCHAR(512) NOT NULL,
                content LONGTEXT NOT NULL,
                tags VARCHAR(512) NOT NULL,
                created_at VARCHAR(64) NOT NULL
            )
            """
        )
        self._connection.commit()

    def add(self, note: Note) -> None:
        p = self._placeholder()
        sql = (
            f"INSERT INTO rf_notes (note_id, title, content, tags, created_at) "
            f"VALUES ({p}, {p}, {p}, {p}, {p}) ON DUPLICATE KEY UPDATE "
            f"title=VALUES(title), content=VALUES(content), tags=VALUES(tags)"
            if self.backend == "seekdb"
            else f"INSERT OR REPLACE INTO rf_notes (note_id, title, content, tags, created_at) "
            f"VALUES ({p}, {p}, {p}, {p}, {p})"
        )
        self._connection.cursor().execute(sql, (note.note_id, note.title, note.content, note.tags, note.created_at))
        self._connection.commit()

    def seed(self, notes: Iterable[Note]) -> int:
        count = 0
        for note in notes:
            self.add(note)
            count += 1
        return count

    def all(self) -> list[Note]:
        rows = self._connection.cursor().execute(
            "SELECT note_id, title, content, tags, created_at FROM rf_notes ORDER BY note_id"
        ).fetchall()
        return [Note(*row) for row in rows]

    def search(self, query: str, *, limit: int = 5) -> list[dict[str, Any]]:
        query_terms = terms(query)
        notes = self.all()
        scored = []
        for note in notes:
            haystack = f"{note.title} {note.content} {note.tags}".casefold()
            title_hits = sum(1 for term in query_terms if term in note.title.casefold())
            body_hits = sum(1 for term in query_terms if term in haystack)
            score = title_hits * 3 + body_hits
            if score:
                scored.append((score, note))
        scored.sort(key=lambda item: (-item[0], item[1].note_id))
        return [
            {
                "note_id": note.note_id,
                "title": note.title,
                "snippet": note.content[:220],
                "tags": note.tags.split(",") if note.tags else [],
                "score": score,
                "source": f"{self.backend}://rf_notes/{note.note_id}",
            }
            for score, note in scored[:limit]
        ]

    @property
    def source(self) -> str:
        return f"seekdb://{self.db_path}" if self.backend == "seekdb" else f"sqlite://{self.sqlite_path}"

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
        if self._instance is not None:
            self._instance.close()
