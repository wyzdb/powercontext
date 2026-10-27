"""MiniMax chat-completion adapter used by the SDD development task."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx

DEFAULT_BASE_URL = "https://api.minimax.chat/v1"
DEFAULT_MODEL = "MiniMax-Text-01"


class MiniMaxError(RuntimeError):
    pass


def build_messages(context: dict[str, Any]) -> list[dict[str, str]]:
    system = (
        "You are a careful software engineer. Use only the supplied specification, "
        "code and test sources. Return the complete revised source file, preserving "
        "every compatibility requirement. Do not edit tests or specs."
    )
    user = (
        "Task context (JSON):\n"
        + json.dumps(context, ensure_ascii=False, indent=2)
        + "\n\nThe implementation to edit is exactly "
        "workspace/expense_approval/approvals.py. Do not edit data/code or data/tests; "
        "those are imported source snapshots. Return only the complete revised "
        "contents of workspace/expense_approval/approvals.py inside one fenced "
        "```python block. Do not include prose."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def complete(context: dict[str, Any], *, timeout: float = 120.0) -> dict[str, Any]:
    api_key = os.environ.get("MINIMAX_API_KEY")
    if not api_key:
        raise MiniMaxError("MINIMAX_API_KEY is not set")
    base_url = os.environ.get("MINIMAX_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    model = os.environ.get("MINIMAX_MODEL", DEFAULT_MODEL)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": build_messages(context),
        "temperature": 0.1,
        "max_tokens": 2048,
    }
    with httpx.Client(timeout=timeout) as client:
        response = client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
    if response.status_code >= 400:
        raise MiniMaxError(f"MiniMax HTTP {response.status_code}: {response.text[:500]}")
    data = response.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise MiniMaxError(f"unexpected MiniMax response: {data}") from error
    return {"model": model, "content": content, "usage": data.get("usage", {})}


def recorded_response(path: Path) -> dict[str, Any]:
    return {
        "model": os.environ.get("MINIMAX_MODEL", DEFAULT_MODEL),
        "content": path.read_text(encoding="utf-8"),
        "usage": {"recorded": True},
    }
