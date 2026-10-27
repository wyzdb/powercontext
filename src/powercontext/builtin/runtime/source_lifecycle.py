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

"""Dependency-aware Source lifecycle propagation for Memory and Topic Memory."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import insert, select, update

from powercontext.artifacts import ArtifactRef
from powercontext.builtin.artifacts.memory import MemoryCitation
from powercontext.builtin.persistence.tables import (
    SOURCE_LIFECYCLE_EVENTS_TABLE,
    SOURCE_LIFECYCLE_NODES_TABLE,
)
from powercontext.builtin.runtime.models import GetMemoryEntryRequest
from powercontext.sources import SourceRef


class SourceLifecycleError(ValueError):
    """A lifecycle graph, event, or resolution contract violation."""


class SourceLifecycleEvent(BaseModel):
    """One explicit availability change for a registered Source."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    node_id: str = Field(min_length=1, max_length=128)
    revision: int = Field(gt=0)
    sequence: int = Field(gt=0)
    available: bool
    reason: str = Field(min_length=1, max_length=512)

    @field_validator("node_id", "reason")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("lifecycle text must be trimmed")
        return value


@dataclass(frozen=True, slots=True)
class _Node:
    node_id: str
    kind: str
    payload: dict[str, Any]
    active: bool
    ordinal: int
    last_sequence: int
    last_digest: str | None


class SourceLifecycleApplication:
    """Expose one scope-bound lifecycle graph through the Runtime."""

    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime

    def for_scope(self, scope_id: str) -> ScopedSourceLifecycle:
        if not isinstance(scope_id, str) or not scope_id.strip():
            raise SourceLifecycleError("scope_id must be non-empty")
        return ScopedSourceLifecycle(self._runtime, scope_id)


class ScopedSourceLifecycle:
    """Register dependency nodes and propagate Source availability in one Scope."""

    def __init__(self, runtime: Any, scope_id: str) -> None:
        self._runtime = runtime
        self.scope_id = scope_id

    async def register_source(self, node_id: str, source_ref: SourceRef, revision: int) -> None:
        _validate_node_id(node_id)
        if type(revision) is not int or revision < 1:
            raise SourceLifecycleError("revision must be a positive integer")
        if not isinstance(source_ref, SourceRef):
            raise SourceLifecycleError("source_ref must be a SourceRef")
        try:
            await self._runtime.records.for_scope(self.scope_id).get_source(
                source_ref.source_type, source_ref.source_id
            )
        except Exception as error:
            raise SourceLifecycleError("registered source does not exist") from error
        payload = {
            "kind": "source",
            "source_ref": source_ref.model_dump(),
            "revision": revision,
            "parents": [],
            "policy": "all",
        }
        await self._register(node_id, "source", payload, source_ref, None, None)

    async def register_memory(
        self,
        node_id: str,
        citation: MemoryCitation,
        parents: tuple[str, ...],
        policy: str,
    ) -> None:
        _validate_node_id(node_id)
        if not isinstance(citation, MemoryCitation):
            raise SourceLifecycleError("citation must be a MemoryCitation")
        try:
            await self._runtime.memory.for_scope(self.scope_id).get(GetMemoryEntryRequest(citation=citation))
        except Exception as error:
            raise SourceLifecycleError("Memory citation does not exist") from error
        payload = {
            "kind": "memory",
            "citation": citation.model_dump(),
            "parents": list(parents),
            "policy": policy,
        }
        reference = citation.memory_ref
        await self._register(node_id, "memory", payload, None, reference, None)

    async def register_topic(
        self,
        node_id: str,
        reference: ArtifactRef,
        parents: tuple[str, ...],
        policy: str,
    ) -> None:
        _validate_node_id(node_id)
        if not isinstance(reference, ArtifactRef):
            raise SourceLifecycleError("reference must be an ArtifactRef")
        try:
            await self._runtime.records.for_scope(self.scope_id).get_artifact_revision(
                reference.family, reference.artifact_id, reference.revision
            )
        except Exception as error:
            raise SourceLifecycleError("Topic Memory artifact does not exist") from error
        payload = {
            "kind": "topic",
            "artifact_ref": reference.model_dump(),
            "parents": list(parents),
            "policy": policy,
        }
        await self._register(node_id, "topic", payload, None, None, reference)

    async def apply(self, event: SourceLifecycleEvent, /) -> list[str]:
        if not isinstance(event, SourceLifecycleEvent):
            raise SourceLifecycleError("event must be a SourceLifecycleEvent")
        digest = _event_digest(event)
        async with self._database().transaction() as connection:
                nodes = await self._load_nodes(connection)
                node = nodes.get(event.node_id)
                if node is None or node.kind != "source":
                    raise SourceLifecycleError("event node is not a registered Source")
                if event.revision != int(node.payload["revision"]):
                    raise SourceLifecycleError("event revision does not match the Source")
                prior = (
                    await connection.execute(
                        select(SOURCE_LIFECYCLE_EVENTS_TABLE).where(
                            SOURCE_LIFECYCLE_EVENTS_TABLE.c.scope_id == self.scope_id,
                            SOURCE_LIFECYCLE_EVENTS_TABLE.c.node_id == event.node_id,
                            SOURCE_LIFECYCLE_EVENTS_TABLE.c.sequence == event.sequence,
                        )
                    )
                ).mappings().one_or_none()
                if prior is not None:
                    if prior["digest"] != digest:
                        raise SourceLifecycleError("event sequence is already used by different content")
                elif event.sequence <= node.last_sequence:
                    raise SourceLifecycleError("event sequence must increase monotonically")
                else:
                    await connection.execute(
                        insert(SOURCE_LIFECYCLE_EVENTS_TABLE).values(
                            scope_id=self.scope_id,
                            node_id=event.node_id,
                            sequence=event.sequence,
                            digest=digest,
                            payload=_canonical(
                                {
                                    "node_id": event.node_id,
                                    "revision": event.revision,
                                    "sequence": event.sequence,
                                    "available": event.available,
                                    "reason": event.reason,
                                }
                            ),
                        )
                    )
                    node.payload["_available"] = event.available
                    node = _Node(
                        node_id=node.node_id,
                        kind=node.kind,
                        payload=node.payload,
                        active=event.available,
                        ordinal=node.ordinal,
                        last_sequence=event.sequence,
                        last_digest=digest,
                    )
                    nodes[node.node_id] = node
                    await connection.execute(
                        update(SOURCE_LIFECYCLE_NODES_TABLE)
                        .where(
                            SOURCE_LIFECYCLE_NODES_TABLE.c.scope_id == self.scope_id,
                            SOURCE_LIFECYCLE_NODES_TABLE.c.node_id == event.node_id,
                        )
                        .values(active=event.available, last_sequence=event.sequence, last_digest=digest)
                    )

                recomputed = _recompute(nodes)
                reconcile_memory = [
                    (node.payload, recomputed[node_id])
                    for node_id, node in nodes.items()
                    if node.kind == "memory"
                ]
                for node_id, active in recomputed.items():
                    current = nodes[node_id]
                    if current.active != active:
                        await connection.execute(
                            update(SOURCE_LIFECYCLE_NODES_TABLE)
                            .where(
                                SOURCE_LIFECYCLE_NODES_TABLE.c.scope_id == self.scope_id,
                                SOURCE_LIFECYCLE_NODES_TABLE.c.node_id == node_id,
                            )
                            .values(active=active)
                        )
        await self._reconcile_memory(reconcile_memory)

        async with self._database().transaction() as connection:
                nodes = await self._load_nodes(connection)
        return sorted(node_id for node_id, node in nodes.items() if node.active)

    async def resolve(self, node_id: str, *, purpose: str) -> SourceRef | MemoryCitation | ArtifactRef:
        if purpose not in {"generation", "audit"}:
            raise SourceLifecycleError("unknown lifecycle purpose")
        async with self._database().transaction() as connection:
                nodes = await self._load_nodes(connection)
        node = nodes.get(node_id)
        if node is None:
            raise SourceLifecycleError("unknown lifecycle node")
        if purpose == "generation" and not node.active:
            raise SourceLifecycleError("node is not available for generation")
        if node.kind == "memory":
            return MemoryCitation.model_validate(node.payload["citation"])
        if node.kind == "topic":
            return ArtifactRef.model_validate(node.payload["artifact_ref"])
        return SourceRef.model_validate(node.payload["source_ref"])

    async def filter_topic_hits(self, hits: Iterable[Any]) -> tuple[Any, ...]:
        async with self._database().transaction() as connection:
                nodes = await self._load_nodes(connection)
        topic_states = {
            (node.payload["artifact_ref"]["artifact_id"], node.payload["artifact_ref"]["revision"]): node.active
            for node in nodes.values()
            if node.kind == "topic"
        }
        return tuple(
            hit
            for hit in hits
            if topic_states.get((hit.artifact_ref.artifact_id, hit.artifact_ref.revision), True)
        )

    def _database(self):
        database = getattr(self._runtime, "_database", None)
        if database is None:
            raise SourceLifecycleError("runtime database is unavailable")
        return database

    async def _register(
        self,
        node_id: str,
        kind: str,
        payload: dict[str, Any],
        source_ref: SourceRef | None,
        memory_ref: ArtifactRef | None,
        artifact_ref: ArtifactRef | None,
    ) -> None:
        if kind in {"memory", "topic"}:
            if policy := payload["policy"]:
                if policy not in {"all", "any"}:
                    raise SourceLifecycleError("policy must be all or any")
            parents = tuple(payload["parents"])
            if not parents or len(set(parents)) != len(parents) or node_id in parents:
                raise SourceLifecycleError("derived nodes require distinct registered parents")
        encoded = _canonical(payload)
        async with self._database().transaction() as connection:
                nodes = await self._load_nodes(connection)
                existing = nodes.get(node_id)
                if existing is not None:
                    if _canonical(existing.payload) != encoded:
                        raise SourceLifecycleError("node id is already bound to another registration")
                    return
                parents = tuple(payload["parents"])
                for parent in parents:
                    if parent not in nodes:
                        raise SourceLifecycleError("parent node is not registered")
                active = True if kind == "source" else _policy(payload["policy"], [nodes[parent].active for parent in parents])
                ordinal = max((node.ordinal for node in nodes.values()), default=0) + 1
                reference = artifact_ref or memory_ref
                await connection.execute(
                    insert(SOURCE_LIFECYCLE_NODES_TABLE).values(
                        scope_id=self.scope_id,
                        node_id=node_id,
                        family=kind,
                        payload=encoded,
                        active=active,
                        ordinal=ordinal,
                        last_sequence=0,
                        last_digest=None,
                        artifact_family=None if reference is None else reference.family,
                        artifact_id=None if reference is None else reference.artifact_id,
                        artifact_revision=None if reference is None else reference.revision,
                    )
                )
        if kind == "memory" and not active:
            await self._set_memory_state(payload, False)

    async def _load_nodes(self, connection: Any) -> dict[str, _Node]:
        rows = (
            await connection.execute(
                select(SOURCE_LIFECYCLE_NODES_TABLE)
                .where(SOURCE_LIFECYCLE_NODES_TABLE.c.scope_id == self.scope_id)
                .order_by(SOURCE_LIFECYCLE_NODES_TABLE.c.ordinal)
            )
        ).mappings()
        return {
            str(row["node_id"]): _Node(
                node_id=str(row["node_id"]),
                kind=str(row["family"]),
                payload=json.loads(row["payload"]),
                active=bool(row["active"]),
                ordinal=int(row["ordinal"]),
                last_sequence=int(row["last_sequence"]),
                last_digest=None if row["last_digest"] is None else str(row["last_digest"]),
            )
            for row in rows
        }

    async def _reconcile_memory(self, states: list[tuple[dict[str, Any], bool]]) -> None:
        if not states:
            return
        async with self._runtime._context(self.scope_id) as context:
            service = context.artifacts.memory
            memory, entries = await service.head_entries(context.artifacts.memory_artifact_id)
            versions = {entry.entry_id: entry for entry in entries}
            states_by_entry = {item.entry_id: item.state for item in memory.content.manifest.entries}
            deactivate = []
            activate = []
            for payload, active in states:
                citation = MemoryCitation.model_validate(payload["citation"])
                entry = versions.get(citation.entry_id)
                if entry is None:
                    raise SourceLifecycleError("Memory entry no longer exists")
                current = states_by_entry.get(citation.entry_id)
                if current == "active" and not active:
                    deactivate.append(entry)
                elif current == "inactive" and active:
                    activate.append(entry)
            if deactivate:
                memory = await service.forget(memory, entries=tuple(deactivate), reason="Source lifecycle")
            if activate:
                await service.reactivate(memory, entries=tuple(activate), reason="Source lifecycle")

    async def _set_memory_state(self, payload: dict[str, Any], active: bool) -> None:
        citation = MemoryCitation.model_validate(payload["citation"])
        async with self._runtime._context(self.scope_id) as context:
            service = context.artifacts.memory
            memory, entries = await service.head_entries(context.artifacts.memory_artifact_id)
            entry = next((item for item in entries if item.entry_id == citation.entry_id), None)
            if entry is None:
                raise SourceLifecycleError("Memory entry no longer exists")
            states = {item.entry_id: item.state for item in memory.content.manifest.entries}
            current = states.get(entry.entry_id)
            if current == "active" and not active:
                await service.forget(memory, entries=(entry,), reason="Source lifecycle")
            elif current == "inactive" and active:
                await service.reactivate(memory, entries=(entry,), reason="Source lifecycle")


def _recompute(nodes: dict[str, _Node]) -> dict[str, bool]:
    active: dict[str, bool] = {}
    for node in sorted(nodes.values(), key=lambda item: item.ordinal):
        if node.kind == "source":
            active[node.node_id] = node.active
        else:
            active[node.node_id] = _policy(node.payload["policy"], [active[parent] for parent in node.payload["parents"]])
    return active


def _policy(policy: str, support: list[bool]) -> bool:
    return all(support) if policy == "all" else any(support)


def _validate_node_id(node_id: str) -> None:
    if not isinstance(node_id, str) or not node_id or node_id != node_id.strip() or len(node_id) > 128:
        raise SourceLifecycleError("node_id must be a non-empty trimmed identifier")


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _event_digest(event: SourceLifecycleEvent) -> str:
    return hashlib.sha256(
        _canonical(
            {
                "node_id": event.node_id,
                "revision": event.revision,
                "sequence": event.sequence,
                "available": event.available,
                "reason": event.reason,
            }
        ).encode("utf-8")
    ).hexdigest()


__all__ = [
    "ScopedSourceLifecycle",
    "SourceLifecycleApplication",
    "SourceLifecycleError",
    "SourceLifecycleEvent",
]
