"""Deterministic bilingual tokenizer used for indexing and querying.

The corpus mixes Chinese specification prose with English identifiers such as
``created_after``. A statistical segmenter would need a model dependency, so
the tokenizer emits identifier parts plus Chinese character bigrams: both the
index and the query go through the same function, which keeps matching
symmetric and reproducible on a clean machine.
"""

from __future__ import annotations

import re

_ASCII_TOKEN = re.compile(r"[a-z][a-z0-9_]*")
_CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")
_IDENTIFIER_SPLIT = re.compile(r"[^a-z0-9]+")
_SPEC_ID = re.compile(r"\b(spec)-(ord|api|ui|db)-(\d{3})(?:/(r\d+))?\b", re.IGNORECASE)

_CJK_STOPWORDS = {
    "的",
    "了",
    "和",
    "与",
    "或",
    "在",
    "是",
    "把",
    "被",
    "对",
    "为",
    "从",
    "到",
    "中",
    "并",
    "且",
    "等",
    "该",
    "其",
    "这",
    "那",
    "有",
    "无",
    "不",
    "必须",
    "可以",
    "需要",
    "不得",
    "用于",
    "进行",
}


def _ascii_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for match in _ASCII_TOKEN.finditer(text):
        token = match.group(0)
        if len(token) >= 2:
            tokens.append(token)
        parts = [part for part in _IDENTIFIER_SPLIT.split(token) if len(part) >= 2]
        if len(parts) > 1:
            tokens.extend(parts)
    return tokens


def _cjk_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for match in _CJK_RUN.finditer(text):
        run = match.group(0)
        if all(character in _CJK_STOPWORDS for character in run):
            continue
        # Bigrams carry most of the signal without a dictionary.
        for index in range(len(run) - 1):
            bigram = run[index : index + 2]
            if bigram in _CJK_STOPWORDS:
                continue
            if all(character in _CJK_STOPWORDS for character in bigram):
                continue
            tokens.append(bigram)
        if 2 <= len(run) <= 6:
            tokens.append(run)
    return tokens


def tokenize(text: str) -> list[str]:
    """Return distinct tokens ordered by first appearance."""

    lowered = text.lower()
    ordered: dict[str, None] = {}
    for token in [
        *_spec_tokens(lowered),
        *_ascii_tokens(lowered),
        *_cjk_tokens(lowered),
    ]:
        if token in _CJK_STOPWORDS:
            continue
        ordered.setdefault(token, None)
    return list(ordered)


def _spec_tokens(text: str) -> list[str]:
    """Emit ``spec-ord-004`` / ``spec-ord-004/r2`` for explicit identifiers."""

    tokens: list[str] = []
    for match in _SPEC_ID.finditer(text):
        base = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
        tokens.append(base)
        if match.group(4):
            tokens.append(f"{base}/{match.group(4)}")
    return tokens


def keyword_echo(text: str, limit: int = 12) -> list[str]:
    """Human-facing keyword list: identifiers and Chinese phrases only."""

    seen: list[str] = []
    for token in tokenize(text):
        if re.fullmatch(r"[a-z0-9_]+", token) and "_" not in token and len(token) < 2:
            continue
        if token not in seen:
            seen.append(token)
        if len(seen) >= limit:
            break
    return seen
