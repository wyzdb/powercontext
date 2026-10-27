# Copyright (c) 2026 OceanBase.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Pi session branch Sources with durable incremental collection."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, JsonValue

from powercontext.limits import MAX_SOURCE_ID_LENGTH
from powercontext.sources import (
    TEXT_EVIDENCE_PROJECTION_KEY,
    AdapterSourceDefinition,
    ConnectorRunCompletion,
    ConnectorRunSession,
    ConnectorRunStatus,
    ConnectorSubmissionStatus,
    Source,
    SourceMaterialization,
    TextEvidence,
)

PI_EVENT_SOURCE_NAME = "pi-event"
PI_EVENT_SOURCE_VERSION = "1"
PI_SESSION_CONNECTOR_NAME = "pi-session-history"
PI_SESSION_CONNECTOR_VERSION = "1"


class PiSessionInput(BaseModel):
    """One offline Pi v3 JSONL archive and its optional selected leaf."""

    model_config = ConfigDict(frozen=True)

    content: bytes
    leaf_id: str | None = None


class PiEventInput(BaseModel):
    """One visible event on the selected Pi branch."""

    model_config = ConfigDict(frozen=True)

    session_id: str
    event_id: str
    parent_id: str | None
    event_type: str
    role: str
    content: str
    record: dict[str, JsonValue]


class PiEventSource(Source):
    """Captured evidence for exactly one visible Pi event."""

    source_id: str
    session_id: str
    event_id: str
    parent_id: str | None
    event_type: str
    role: str
    content: str
    record: dict[str, JsonValue]


def pi_event_source_id(session_id: str, event_id: str, /) -> str:
    """Build the stable, delimiter-safe identity for one Pi event."""

    if not isinstance(session_id, str) or not session_id:
        raise ValueError("session_id must be a non-empty string")
    if not isinstance(event_id, str) or not event_id:
        raise ValueError("event_id must be a non-empty string")
    source_id = f"pi:{quote(session_id, safe='')}:{quote(event_id, safe='')}"
    if len(source_id) > MAX_SOURCE_ID_LENGTH:
        raise ValueError(f"pi-event source_id must not exceed {MAX_SOURCE_ID_LENGTH} characters")
    return source_id


def parse_pi_session(value: PiSessionInput, /) -> tuple[PiEventInput, ...]:
    """Parse one Pi v3 archive and return the selected branch's visible events."""

    try:
        text = value.content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("Pi session must be valid UTF-8") from error

    records: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"malformed Pi session JSON: {error}") from error
        if not isinstance(record, dict):
            raise ValueError("each Pi session line must be a JSON object")
        records.append(record)

    if not records:
        raise ValueError("Pi session must start with a session header")
    header = records[0]
    if header.get("type") != "session" or header.get("version") != 3:
        raise ValueError("Pi session header must be type=session and version=3")
    session_id = header.get("id")
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("Pi session header id must be a non-empty string")

    seen_ids: set[str] = {session_id}
    by_id: dict[str, dict[str, Any]] = {}
    parent_by_id: dict[str, str | None] = {}
    for record in records[1:]:
        event_id = record.get("id")
        if not isinstance(event_id, str) or not event_id:
            raise ValueError("Pi session event id must be a non-empty string")
        if event_id in seen_ids:
            raise ValueError("Pi session event ids must be unique")
        seen_ids.add(event_id)
        raw_parent = record.get("parentId")
        if raw_parent is None or raw_parent == "":
            parent_id = None
        elif isinstance(raw_parent, str):
            if raw_parent not in by_id:
                raise ValueError("Pi session parent must reference an earlier node")
            parent_id = raw_parent
        else:
            raise ValueError("Pi session parentId must be a string or null")
        by_id[event_id] = record
        parent_by_id[event_id] = parent_id

    if not by_id:
        raise ValueError("Pi session must contain at least one event node")
    if value.leaf_id is None:
        leaf_id = next(reversed(by_id))
    else:
        leaf_id = value.leaf_id
        if leaf_id not in by_id:
            raise ValueError("Pi session leaf_id does not exist")

    path: list[str] = []
    current: str | None = leaf_id
    while current is not None:
        path.append(current)
        current = parent_by_id[current]
    path.reverse()

    events: list[PiEventInput] = []
    for event_id in path:
        record = by_id[event_id]
        rendered = _render_event(record)
        if rendered is None:
            continue
        role, body = rendered
        events.append(
            PiEventInput(
                session_id=session_id,
                event_id=event_id,
                parent_id=parent_by_id[event_id],
                event_type=record["type"],
                role=role,
                content=f"{role}: {body}",
                record=record,
            )
        )
    return tuple(events)


def _render_event(record: dict[str, Any]) -> tuple[str, str] | None:
    event_type = record.get("type")
    if event_type == "message":
        message = record.get("message")
        if not isinstance(message, dict):
            return None
        role = message.get("role")
        if not isinstance(role, str) or not role:
            return None
        if role == "toolResult":
            body = _render_tool_result(message)
        elif role == "bashExecution":
            body = _render_bash(message)
        else:
            body = _render_content(message.get("content"))
        if not body:
            return None
        return role, body
    if event_type in {"compaction", "branch_summary"}:
        summary = record.get("summary")
        if not isinstance(summary, str) or not summary:
            return None
        return event_type, summary
    if event_type == "custom_message":
        body = _render_content(record.get("content"))
        if not body:
            return None
        return "custom", body
    return None


def _render_tool_result(message: dict[str, Any]) -> str | None:
    body = _render_content(message.get("content")) or ""
    name = message.get("toolName")
    call_id = message.get("toolCallId")
    return f"[tool_result {name if isinstance(name, str) else ''} {call_id if isinstance(call_id, str) else ''}] {body}"


def _render_bash(message: dict[str, Any]) -> str:
    command = message.get("command")
    output = message.get("output")
    return f"$ {command if isinstance(command, str) else ''}\n{output if isinstance(output, str) else ''}"


def _render_content(content: object) -> str | None:
    if isinstance(content, str):
        return content or None
    if not isinstance(content, list):
        return None
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "text":
            text = block.get("text")
            if isinstance(text, str) and text:
                parts.append(text)
        elif block_type == "toolCall":
            name = block.get("name")
            call_id = block.get("id")
            arguments = block.get("arguments", {})
            arguments_text = json.dumps(arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            parts.append(
                f"[tool_call {name if isinstance(name, str) else ''} "
                f"{call_id if isinstance(call_id, str) else ''}] {arguments_text}"
            )
    if not parts:
        return None
    return "\n".join(parts)


def _event_fingerprint(event: PiEventInput) -> str:
    payload = json.dumps(
        event.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class PiEventSourceAdapter:
    """Resolve and read the captured Pi event Source."""

    input_class = PiEventInput
    name = PI_EVENT_SOURCE_NAME
    source_class = PiEventSource

    async def resolve(self, value: PiEventInput, /) -> PiEventSource:
        source_id = pi_event_source_id(value.session_id, value.event_id)
        return PiEventSource(
            name=source_id,
            source_id=source_id,
            materialization=SourceMaterialization.CAPTURED,
            session_id=value.session_id,
            event_id=value.event_id,
            parent_id=value.parent_id,
            event_type=value.event_type,
            role=value.role,
            content=value.content,
            record=value.record,
        )

    async def read(self, source: PiEventSource, /) -> PiEventInput:
        return PiEventInput(
            session_id=source.session_id,
            event_id=source.event_id,
            parent_id=source.parent_id,
            event_type=source.event_type,
            role=source.role,
            content=source.content,
            record=source.record,
        )


class PiEventTextEvidenceProjection:
    """Expose one Pi event as standard text evidence."""

    name = TEXT_EVIDENCE_PROJECTION_KEY.name
    version = TEXT_EVIDENCE_PROJECTION_KEY.version
    source_class = PiEventSource
    output_class: type[BaseModel] = TextEvidence

    def project(self, source: PiEventSource, /) -> TextEvidence:
        return TextEvidence(
            source_type=PI_EVENT_SOURCE_NAME,
            source_id=source.source_id,
            content=source.content,
            metadata={
                "session_id": source.session_id,
                "event_id": source.event_id,
                "parent_id": source.parent_id,
                "event_type": source.event_type,
                "role": source.role,
            },
        )


PI_EVENT_SOURCE_ADAPTER = PiEventSourceAdapter()
PI_EVENT_SOURCE_DEFINITION = AdapterSourceDefinition(
    PI_EVENT_SOURCE_ADAPTER,
    version=PI_EVENT_SOURCE_VERSION,
    projections=(PiEventTextEvidenceProjection(),),
)


class PiSessionConnector:
    """Collect the selected Pi branch incrementally with a durable checkpoint."""

    name = PI_SESSION_CONNECTOR_NAME
    version = PI_SESSION_CONNECTOR_VERSION
    source_definitions = frozenset({PI_EVENT_SOURCE_NAME})

    def __init__(self, path: Path | str, leaf_id: str | None = None) -> None:
        self.path = Path(path)
        self.leaf_id = leaf_id

    async def run(self, session: ConnectorRunSession, /) -> ConnectorRunCompletion:
        events = parse_pi_session(PiSessionInput(content=self.path.read_bytes(), leaf_id=self.leaf_id))
        imported: dict[str, str] = {}
        checkpoint = session.checkpoint
        if checkpoint is not None:
            if not isinstance(checkpoint, dict):
                raise ValueError("Pi connector checkpoint must be an object")
            stored = checkpoint.get("events", {})
            if not isinstance(stored, dict):
                raise ValueError("Pi connector checkpoint events must be an object")
            for event_id, fingerprint in stored.items():
                if not isinstance(event_id, str) or not isinstance(fingerprint, str):
                    raise ValueError("Pi connector checkpoint contains invalid entries")
                imported[event_id] = fingerprint

        fingerprints = {event.event_id: _event_fingerprint(event) for event in events}
        for event in events:
            stored = imported.get(event.event_id)
            if stored is not None and stored != fingerprints[event.event_id]:
                raise ValueError("an imported Pi event was rewritten")

        updated = dict(imported)
        for event in events:
            if event.event_id in imported:
                continue
            outcome = await session.submit(event.event_id, PI_EVENT_SOURCE_NAME, event)
            if outcome.status is not ConnectorSubmissionStatus.ACCEPTED:
                raise ValueError(f"Pi event submission was {outcome.status}")
            updated[event.event_id] = fingerprints[event.event_id]

        return ConnectorRunCompletion(
            status=ConnectorRunStatus.COMPLETE,
            checkpoint={"events": updated},
        )


__all__ = [
    "PI_EVENT_SOURCE_ADAPTER",
    "PI_EVENT_SOURCE_DEFINITION",
    "PI_EVENT_SOURCE_NAME",
    "PI_EVENT_SOURCE_VERSION",
    "PI_SESSION_CONNECTOR_NAME",
    "PI_SESSION_CONNECTOR_VERSION",
    "PiEventInput",
    "PiEventSource",
    "PiEventSourceAdapter",
    "PiEventTextEvidenceProjection",
    "PiSessionConnector",
    "PiSessionInput",
    "parse_pi_session",
    "pi_event_source_id",
]
