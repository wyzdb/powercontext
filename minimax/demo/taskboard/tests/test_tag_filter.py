"""目标功能测试：SPEC-002（按标签筛选）。

改前全部失败（接口忽略 tag 参数，返回全量任务），改后必须全部通过。
测试本身不修改，也不允许为了让测试通过而改预期值。
"""

from __future__ import annotations


def test_filter_by_tag(client):
    """REQ-TAG-01：只返回 tags 中包含该标签的任务。"""
    body = client.get("/api/tasks?tag=backend").get_json()
    assert body["count"] == 4
    assert {task["id"] for task in body["items"]} == {1, 2, 7, 10}
    assert all("backend" in task["tags"] for task in body["items"])


def test_tag_match_is_case_insensitive(client):
    """REQ-TAG-02：大小写不敏感，Backend 与 backend 等价。"""
    lower = client.get("/api/tasks?tag=backend").get_json()
    upper = client.get("/api/tasks?tag=Backend").get_json()

    # 先确认筛选本身生效，再比较两种大小写结果（避免改前"两边都是全量"而假通过）。
    assert lower["count"] == 4
    assert upper["count"] == lower["count"]
    assert {t["id"] for t in upper["items"]} == {t["id"] for t in lower["items"]}


def test_tag_requires_exact_token(client):
    """REQ-TAG-02：按完整标签匹配，不做子串匹配。"""
    body = client.get("/api/tasks?tag=back").get_json()
    assert body["count"] == 0
    assert body["items"] == []


def test_unknown_tag_returns_empty_list(client):
    """REQ-TAG-04：未知标签返回空列表，HTTP 状态仍是 200。"""
    resp = client.get("/api/tasks?tag=does-not-exist")
    assert resp.status_code == 200

    body = resp.get_json()
    assert body["items"] == []
    assert body["count"] == 0


def test_empty_tag_is_treated_as_absent(client):
    """REQ-TAG-04：tag= 视为未提供，不做任何过滤。"""
    body = client.get("/api/tasks?tag=").get_json()
    assert body["count"] == 10

    # 同时确认非空 tag 确实会过滤，否则"空 tag 返回全量"在改前也是假通过。
    assert client.get("/api/tasks?tag=backend").get_json()["count"] == 4


def test_tag_combined_with_status(client):
    """REQ-TAG-03：tag 与 status 同时出现时取交集。"""
    body = client.get("/api/tasks?status=open&tag=backend").get_json()
    assert {task["id"] for task in body["items"]} == {1, 10}
    assert all(task["status"] == "open" and "backend" in task["tags"] for task in body["items"])


def test_tag_filter_keeps_response_shape(client):
    """REQ-TAG-05：响应结构与排序不变。"""
    body = client.get("/api/tasks?tag=urgent").get_json()
    assert body["count"] == 3
    assert set(body) == {"items", "count"}
    ids = [task["id"] for task in body["items"]]
    assert ids == sorted(ids)
    assert set(body["items"][0]) == {"id", "title", "status", "tags", "owner", "due"}
