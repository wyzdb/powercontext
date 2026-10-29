"""上下文模块的单元测试。

依赖外部服务的用例会先探测可用性，不可用则 skip，保证干净环境也能跑通
纯逻辑部分（切词、diff 提取）。
"""

from __future__ import annotations

import socket

import pytest

from ctx import patch, retrieve
from ctx.config import DBConfig


def _port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def test_tokenize_mixes_chinese_bigrams_and_words():
    tokens = retrieve.tokenize("为任务列表增加 tag 筛选")
    assert "tag" in tokens
    assert "标签" not in tokens  # 任务文本里没有"标签"这个词
    assert "任务" in tokens
    assert "筛选" in tokens


def test_extract_diff_from_fenced_block():
    text = "说明文字\n```diff\ndiff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-a\n+b\n```"
    diff = patch.extract_diff(text)
    assert diff.startswith("diff --git a/x.py")
    assert diff.endswith("\n")


def test_extract_diff_without_fence_raises():
    with pytest.raises(ValueError):
        patch.extract_diff("这里没有补丁")


@pytest.mark.skipif(
    not _port_open(DBConfig.from_env().host, DBConfig.from_env().port),
    reason="seekdb 未启动",
)
def test_build_context_contains_required_sources():
    context = retrieve.build_context("为任务列表增加按标签筛选")

    assert [s["key"] for s in context["specs"]] == ["SPEC-002", "SPEC-001"]
    assert context["specs"][0]["role"] == "primary"
    assert "REQ-TAG-01" in {r["id"] for r in context["specs"][0]["requirements"]}

    code_paths = {c["path"] for c in context["code"]}
    assert code_paths == {"taskboard/app.py", "taskboard/store.py"}

    symbols = {s["name"] for c in context["code"] for s in c["symbols"]}
    assert {"list_tasks", "filter_tasks"} <= symbols

    roles = {t["path"]: t["role"] for t in context["tests"]}
    assert roles["tests/test_tag_filter.py"] == "target"
    assert roles["tests/test_tasks_api.py"] == "regression"


@pytest.mark.skipif(
    not _port_open("127.0.0.1", 18080),
    reason="PowerContext Server 未启动",
)
def test_state_roundtrip():
    from ctx import state

    payload = {"stage": "test", "done": ["x"], "todo": [], "verifications": []}
    saved = state.save("TASK-TEST", payload)
    loaded = state.load("TASK-TEST")

    assert loaded is not None
    assert loaded["artifact"] == saved["artifact"]
    assert loaded["state"]["done"] == ["x"]
