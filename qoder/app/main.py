from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .service import ResearchFlow

ROOT = Path(__file__).resolve().parents[1]
flow = ResearchFlow(ROOT)
app = FastAPI(title="ResearchFlow", version="0.1.0")
app.mount("/static", StaticFiles(directory=ROOT / "app" / "static"), name="static")


class SearchBody(BaseModel):
    query: str
    limit: int = 5


class ProfileBody(BaseModel):
    user_id: str
    interests: list[str]
    stage: str = ""
    goal: str = ""


@app.get("/")
def index() -> FileResponse:
    return FileResponse(ROOT / "app" / "static" / "index.html")


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "notes": len(flow.notes.all()),
        "store": flow.notes.source,
        "memory": flow.memory.source,
    }


@app.post("/api/seed")
def seed() -> dict[str, int]:
    return {"seeded": flow.seed()}


@app.post("/api/search")
def search(body: SearchBody) -> dict[str, Any]:
    return flow.search(body.query, limit=body.limit)


@app.post("/api/profile")
def profile(body: ProfileBody) -> dict[str, Any]:
    return flow.save_profile(body.user_id, body.interests, body.stage, body.goal)


@app.get("/api/recommend/{user_id}")
def recommend(user_id: str) -> dict[str, Any]:
    return flow.recommend(user_id)
