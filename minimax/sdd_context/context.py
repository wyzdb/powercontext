"""Build an SDD task context from seekdb documents and PowerContext state."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .state import PowerContextState
from .store import DocumentStore


class ContextBuilder:
    def __init__(self, root: Path, *, backend: str | None = None) -> None:
        self.root = root
        self.store = DocumentStore(root, backend=backend)
        self.state = PowerContextState(root / ".sdd" / "powercontext.db")

    def initialize(self) -> dict[str, Any]:
        count = self.store.import_tree()
        return {"imported": count, "store": self.store.source}

    def build(self, task_id: str, task: str) -> dict[str, Any]:
        selected = self.store.search(task)
        state = self.state.load(task_id)
        return {
            "task": {"id": task_id, "description": task},
            "specs": [_document(item) for item in selected.get("spec", [])],
            "code": [_document(item) for item in selected.get("code", [])],
            "tests": [_document(item) for item in selected.get("test", [])],
            "state": state,
            "sources": {
                "documents": self.store.source,
                "state": self.state.source,
                "backend": self.store.backend,
            },
        }

    def save_state(
        self,
        task_id: str,
        task: str,
        *,
        completed: list[str],
        pending: list[str],
        validation: list[dict[str, Any]],
        updated_at: str,
    ) -> dict[str, Any]:
        state = {
            "task_id": task_id,
            "task": task,
            "completed": completed,
            "pending": pending,
            "validation": validation,
            "updated_at": updated_at,
        }
        self.state.save(state)
        return state

    def close(self) -> None:
        self.store.close()


def _document(document: Any) -> dict[str, Any]:
    return {
        "id": document.doc_id,
        "version": document.version,
        "path": document.path,
        "symbol": document.symbol,
        "source": f"{document.kind}://{document.doc_id}@v{document.version}",
        "text": document.text,
    }
