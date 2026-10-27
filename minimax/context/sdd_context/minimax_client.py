"""MiniMax chat-completions client plus patch extraction.

Only the OpenAI-compatible surface is used, so the recorded base URL and model
name fully describe the call. Reasoning models may wrap answers in
``<think>`` blocks; those are stripped before the patch is extracted.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from sdd_context.config import Settings

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_FENCED = re.compile(r"```(?:diff|patch)?\s*\n(.*?)```", re.DOTALL)


class MiniMaxError(RuntimeError):
    """A model call or response parsing failure."""


@dataclass(frozen=True)
class Completion:
    text: str
    model: str
    usage: dict[str, Any] = field(default_factory=dict)
    request_id: str | None = None
    finish_reason: str | None = None
    duration_ms: int = 0
    attempts: int = 1
    raw: dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "request_id": self.request_id,
            "finish_reason": self.finish_reason,
            "duration_ms": self.duration_ms,
            "attempts": self.attempts,
            "usage": self.usage,
            "text": self.text,
        }


class MiniMaxClient:
    """Minimal, dependency-free client for the MiniMax chat endpoint."""

    def __init__(self, settings: Settings, *, timeout: float = 180.0, max_attempts: int = 3) -> None:
        self.settings = settings
        self.timeout = timeout
        self.max_attempts = max_attempts

    def complete(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        disable_thinking: bool = True,
    ) -> Completion:
        api_key = self.settings.require_minimax_key()
        payload: dict[str, Any] = {
            "model": self.settings.minimax_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if disable_thinking and self.settings.minimax_model.startswith("MiniMax-M3"):
            # M3 otherwise spends the whole completion budget on reasoning and
            # returns an empty content field.
            payload["thinking"] = {"type": "disabled"}
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.settings.minimax_base_url}/chat/completions",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            started = time.perf_counter()
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    raw = json.loads(response.read().decode("utf-8"))
                duration_ms = int((time.perf_counter() - started) * 1000)
                content = _message_content(raw)
                return Completion(
                    text=_strip_reasoning(content),
                    model=str(raw.get("model") or self.settings.minimax_model),
                    usage=dict(raw.get("usage") or {}),
                    request_id=raw.get("id") or raw.get("request_id"),
                    finish_reason=_finish_reason(raw),
                    duration_ms=duration_ms,
                    attempts=attempt,
                    raw=raw,
                )
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")[:600]
                last_error = MiniMaxError(f"HTTP {exc.code}: {detail}")
                if exc.code not in (408, 409, 429, 500, 502, 503, 504):
                    raise last_error from exc
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = MiniMaxError(f"{type(exc).__name__}: {exc}")
            time.sleep(min(2 ** attempt, 8))
        raise last_error or MiniMaxError("MiniMax request failed")


def _message_content(raw: dict[str, Any]) -> str:
    choices = raw.get("choices") or []
    if not choices:
        raise MiniMaxError(f"response has no choices: {json.dumps(raw)[:400]}")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, list):  # multi-part content
        return "".join(part.get("text", "") for part in content if isinstance(part, dict))
    if not isinstance(content, str) or not content.strip():
        raise MiniMaxError("response message content is empty")
    return content


def _finish_reason(raw: dict[str, Any]) -> str | None:
    choices = raw.get("choices") or []
    return choices[0].get("finish_reason") if choices else None


def _strip_reasoning(text: str) -> str:
    return _THINK_BLOCK.sub("", text).strip()


def extract_patch(text: str) -> str:
    """Return the unified diff from the model answer.

    Accepted forms, in order: an explicit ``<<<PATCH`` fence, a fenced diff
    block, or a bare diff that starts with ``---``.
    """

    marker_start = text.find("<<<PATCH")
    marker_end = text.find("PATCH>>>")
    if marker_start != -1 and marker_end > marker_start:
        return text[marker_start + len("<<<PATCH") : marker_end].strip()

    fenced = _FENCED.search(text)
    if fenced:
        candidate = fenced.group(1).strip()
        if candidate.startswith("---"):
            return candidate

    index = text.find("--- ")
    if index != -1 and "+++ " in text[index:]:
        return text[index:].strip()

    raise MiniMaxError("model answer does not contain a unified diff")
