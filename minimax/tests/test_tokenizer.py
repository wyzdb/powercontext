"""Tokenizer behaviour that the inverted index depends on."""

from __future__ import annotations

from sdd_context.tokenizer import tokenize


def test_identifier_parts_are_indexed() -> None:
    tokens = tokenize("created_after")
    assert "created_after" in tokens
    assert "created" in tokens
    assert "after" in tokens


def test_chinese_bigrams_and_phrase() -> None:
    tokens = tokenize("按创建时间筛选")
    assert "创建" in tokens
    assert "时间" in tokens
    assert "筛选" in tokens


def test_stopwords_do_not_dominate() -> None:
    tokens = tokenize("的是和了")
    assert tokens == []


def test_spec_identifier_is_a_single_token() -> None:
    tokens = tokenize("必须满足 SPEC-ORD-004/R2 的边界要求")
    assert "spec-ord-004" in tokens
    assert "spec-ord-004/r2" in tokens


def test_tokenize_is_stable() -> None:
    text = "GET /orders 支持 created_after 参数"
    assert tokenize(text) == tokenize(text)
