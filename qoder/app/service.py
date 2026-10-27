"""ResearchFlow service: notes in seekdb + researcher memory in PowerContext."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .memory import ProfileMemory
from .store import Note, NoteStore


class ResearchFlow:
    def __init__(self, root: Path, *, backend: str | None = None) -> None:
        self.root = root
        self.notes = NoteStore(root, backend=backend)
        self.memory = ProfileMemory(root / ".qoder" / "powercontext.db")

    def seed(self) -> int:
        payload = json.loads((self.root / "data" / "notes.json").read_text(encoding="utf-8"))
        return self.notes.seed(
            Note(
                note_id=item["note_id"],
                title=item["title"],
                content=item["content"],
                tags=",".join(item.get("tags", [])),
                created_at=item.get("created_at", "2026-01-01T00:00:00Z"),
            )
            for item in payload["notes"]
        )

    def search(self, query: str, *, limit: int = 5) -> dict[str, Any]:
        return {
            "query": query,
            "results": self.notes.search(query, limit=limit),
            "source": self.notes.source,
        }

    def save_profile(self, user_id: str, interests: list[str], stage: str, goal: str) -> dict[str, Any]:
        profile = {"interests": interests, "stage": stage, "goal": goal}
        self.memory.save(user_id, profile)
        return {"user_id": user_id, **profile, "source": self.memory.source}

    def recommend(self, user_id: str, *, limit: int = 5) -> dict[str, Any]:
        profile = self.memory.load(user_id) or {}
        query = " ".join(profile.get("interests", [])) or profile.get("goal", "") or "research"
        return {
            "user_id": user_id,
            "profile": profile,
            "query": query,
            "results": self.notes.search(query, limit=limit),
            "sources": {"notes": self.notes.source, "memory": self.memory.source},
        }

    def close(self) -> None:
        self.notes.close()
