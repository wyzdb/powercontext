from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.service import ResearchFlow  # noqa: E402


def main() -> None:
    backend = sys.argv[1] if len(sys.argv) > 1 else None
    flow = ResearchFlow(ROOT, backend=backend)
    try:
        seeded = flow.seed()
        search = flow.search("transformer attention")
        assert search["results"], "expected a transformer note"
        profile = flow.save_profile(
            "demo-researcher",
            ["retrieval", "memory"],
            "文献调研",
            "完成 retrieval baseline 的消融实验",
        )
    finally:
        flow.close()

    # Simulate a restart: a fresh service reads PowerContext Memory again.
    restarted = ResearchFlow(ROOT, backend=backend)
    try:
        recommendation = restarted.recommend("demo-researcher")
        assert recommendation["profile"]["interests"] == ["retrieval", "memory"]
        assert recommendation["results"], "expected memory-driven recommendations"
        notes_count = len(restarted.notes.all())
        result = {
            "backend": restarted.notes.backend,
            "seeded": seeded,
            "notes": notes_count,
            "search_query": search["query"],
            "search_hits": [item["note_id"] for item in search["results"]],
            "profile": profile,
            "recommendation_hits": [item["note_id"] for item in recommendation["results"]],
            "memory_source": recommendation["sources"]["memory"],
            "notes_source": recommendation["sources"]["notes"],
            "state_reused": recommendation["profile"]["goal"],
        }
    finally:
        restarted.close()
    (ROOT / "record" / "validation_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
