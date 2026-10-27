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

"""Chunked context packs and reusable-prefix incremental deltas."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from dataclasses import dataclass
from typing import Any

CONTEXT_PACK_SCHEMA = "powercontext.context-pack.v1"
CONTEXT_PACK_DELTA_SCHEMA = "powercontext.context-pack-delta.v1"
_DIGEST_PREFIX = "sha256:"
_HEX_DIGITS = frozenset("0123456789abcdef")


class ContextPackError(ValueError):
    """A context-pack protocol or chunking contract violation."""


@dataclass(frozen=True, slots=True)
class ContextPack:
    """One complete, chunked context payload."""

    items: tuple[bytes, ...]
    digest: str
    byte_count: int

    @classmethod
    def build(cls, items: tuple[bytes, ...], /) -> ContextPack:
        normalized = _normalize_items(items)
        digest = _pack_digest(normalized)
        return cls(items=normalized, digest=digest, byte_count=_solve_byte_count(normalized, digest))

    @classmethod
    def from_content(cls, content: str | bytes, /, *, chunk_bytes: int = 512) -> ContextPack:
        if type(chunk_bytes) is not int or chunk_bytes <= 0:
            raise ContextPackError("chunk_bytes must be a positive integer")
        if isinstance(content, bytes):
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError as error:
                raise ContextPackError("content must be valid UTF-8") from error
        elif isinstance(content, str):
            text = content
        else:
            raise ContextPackError("content must be str or bytes")

        chunks: list[bytes] = []
        buffer = bytearray()
        for character in text:
            try:
                encoded = character.encode("utf-8")
            except UnicodeEncodeError as error:
                raise ContextPackError("content must be valid UTF-8") from error
            if len(encoded) > chunk_bytes:
                raise ContextPackError("a UTF-8 character exceeds the chunk limit")
            if buffer and len(buffer) + len(encoded) > chunk_bytes:
                chunks.append(bytes(buffer))
                buffer = bytearray()
            buffer.extend(encoded)
        if buffer:
            chunks.append(bytes(buffer))
        return cls.build(tuple(chunks))

    def to_bytes(self) -> bytes:
        payload = {
            "schema": CONTEXT_PACK_SCHEMA,
            "items": _encode_items(self.items),
            "digest": self.digest,
            "byte_count": self.byte_count,
        }
        raw = _canonical_bytes(payload)
        if len(raw) != self.byte_count:
            raise ContextPackError("pack byte_count does not match its wire size")
        return raw

    @classmethod
    def from_bytes(cls, data: bytes, /) -> ContextPack:
        payload = _decode_object(data)
        if set(payload) != {"schema", "items", "digest", "byte_count"}:
            raise ContextPackError("pack must contain exactly schema, items, digest and byte_count")
        if payload["schema"] != CONTEXT_PACK_SCHEMA:
            raise ContextPackError("unsupported context-pack schema")
        items = _decode_items(payload["items"])
        digest = _require_digest(payload["digest"])
        if _pack_digest(items) != digest:
            raise ContextPackError("context-pack digest does not match its items")
        byte_count = payload["byte_count"]
        if type(byte_count) is not int or byte_count < 0 or byte_count != len(data):
            raise ContextPackError("context-pack byte_count does not match its wire size")
        return cls(items=items, digest=digest, byte_count=byte_count)


@dataclass(frozen=True, slots=True)
class ContextPackDelta:
    """A reusable base prefix plus the target suffix."""

    base_digest: str
    target_digest: str
    prefix_items: int
    appended: tuple[bytes, ...]

    @property
    def byte_count(self) -> int:
        return len(self.to_bytes())

    @classmethod
    def between(cls, base: ContextPack, target: ContextPack, /) -> ContextPackDelta:
        if not isinstance(base, ContextPack) or not isinstance(target, ContextPack):
            raise ContextPackError("delta endpoints must be ContextPack values")
        prefix = 0
        for base_item, target_item in zip(base.items, target.items, strict=False):
            if base_item != target_item:
                break
            prefix += 1
        return cls(
            base_digest=base.digest,
            target_digest=target.digest,
            prefix_items=prefix,
            appended=_normalize_items(target.items[prefix:]),
        )

    def to_bytes(self) -> bytes:
        _require_digest(self.base_digest)
        _require_digest(self.target_digest)
        if type(self.prefix_items) is not int or self.prefix_items < 0:
            raise ContextPackError("prefix_items must be a non-negative integer")
        payload = {
            "schema": CONTEXT_PACK_DELTA_SCHEMA,
            "base_digest": self.base_digest,
            "target_digest": self.target_digest,
            "prefix_items": self.prefix_items,
            "appended": _encode_items(_normalize_items(self.appended)),
        }
        return _canonical_bytes(payload)

    @classmethod
    def from_bytes(cls, data: bytes, /) -> ContextPackDelta:
        payload = _decode_object(data)
        if set(payload) != {"schema", "base_digest", "target_digest", "prefix_items", "appended"}:
            raise ContextPackError(
                "delta must contain exactly schema, base_digest, target_digest, prefix_items and appended"
            )
        if payload["schema"] != CONTEXT_PACK_DELTA_SCHEMA:
            raise ContextPackError("unsupported context-pack-delta schema")
        prefix = payload["prefix_items"]
        if type(prefix) is not int or prefix < 0:
            raise ContextPackError("prefix_items must be a non-negative integer")
        return cls(
            base_digest=_require_digest(payload["base_digest"]),
            target_digest=_require_digest(payload["target_digest"]),
            prefix_items=prefix,
            appended=_decode_items(payload["appended"]),
        )


def apply_context_pack_delta(base: ContextPack, delta: ContextPackDelta, /) -> ContextPack:
    """Validate a delta and rebuild its target pack."""

    if not isinstance(base, ContextPack) or not isinstance(delta, ContextPackDelta):
        raise ContextPackError("apply requires a ContextPack and a ContextPackDelta")
    if base.digest != delta.base_digest:
        raise ContextPackError("delta base digest does not match the supplied base pack")
    if type(delta.prefix_items) is not int or delta.prefix_items < 0 or delta.prefix_items > len(base.items):
        raise ContextPackError("delta prefix_items is outside the base pack")
    target = ContextPack.build((*base.items[: delta.prefix_items], *delta.appended))
    if target.digest != delta.target_digest:
        raise ContextPackError("delta target digest does not match the rebuilt pack")
    return target


def _normalize_items(items: object) -> tuple[bytes, ...]:
    if not isinstance(items, tuple):
        try:
            items = tuple(items)  # type: ignore[arg-type]
        except TypeError as error:
            raise ContextPackError("items must be an iterable of bytes") from error
    for item in items:
        if not isinstance(item, bytes):
            raise ContextPackError("items must contain only bytes")
    return items


def _encode_items(items: tuple[bytes, ...]) -> list[str]:
    return [base64.b64encode(item).decode("ascii") for item in items]


def _decode_items(value: object) -> tuple[bytes, ...]:
    if not isinstance(value, list):
        raise ContextPackError("items must be a list of base64 strings")
    decoded: list[bytes] = []
    for entry in value:
        if not isinstance(entry, str):
            raise ContextPackError("items must be a list of base64 strings")
        try:
            decoded.append(base64.b64decode(entry, validate=True))
        except (binascii.Error, ValueError) as error:
            raise ContextPackError("items contains invalid base64") from error
    return tuple(decoded)


def _pack_digest(items: tuple[bytes, ...]) -> str:
    unsigned = {"schema": CONTEXT_PACK_SCHEMA, "items": _encode_items(items)}
    return _DIGEST_PREFIX + hashlib.sha256(_canonical_bytes(unsigned)).hexdigest()


def _solve_byte_count(items: tuple[bytes, ...], digest: str) -> int:
    candidate = 0
    seen: set[int] = set()
    for _ in range(20):
        raw = _canonical_bytes(
            {
                "schema": CONTEXT_PACK_SCHEMA,
                "items": _encode_items(items),
                "digest": digest,
                "byte_count": candidate,
            }
        )
        if len(raw) == candidate:
            return candidate
        if len(raw) in seen:
            break
        seen.add(len(raw))
        candidate = len(raw)
    for fallback in range(max(0, candidate - 20), candidate + 40):
        raw = _canonical_bytes(
            {
                "schema": CONTEXT_PACK_SCHEMA,
                "items": _encode_items(items),
                "digest": digest,
                "byte_count": fallback,
            }
        )
        if len(raw) == fallback:
            return fallback
    raise ContextPackError("could not determine a stable byte_count")


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _decode_object(data: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ContextPackError("pack must be valid UTF-8 JSON") from error
    if not isinstance(payload, dict):
        raise ContextPackError("pack must be a JSON object")
    return payload


def _require_digest(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value.startswith(_DIGEST_PREFIX)
        or len(value) != len(_DIGEST_PREFIX) + 64
        or any(character not in _HEX_DIGITS for character in value[len(_DIGEST_PREFIX) :])
    ):
        raise ContextPackError("digest must be a sha256:<hex> value")
    return value


__all__ = [
    "CONTEXT_PACK_DELTA_SCHEMA",
    "CONTEXT_PACK_SCHEMA",
    "ContextPack",
    "ContextPackDelta",
    "ContextPackError",
    "apply_context_pack_delta",
]
