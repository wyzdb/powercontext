"""回归测试：SPEC-001 描述的既有行为，改动前后都必须通过。"""

from __future__ import annotations

TASK_FIELDS = {"id", "title", "status", "tags", "owner", "due"}


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_list_all_tasks_sorted_by_id(client):
    """REQ-LIST-01 / REQ-LIST-03：默认返回全部任务，按 id 升序。"""
    resp = client.get("/api/tasks")
    assert resp.status_code == 200

    body = resp.get_json()
    assert body["count"] == 10
    assert len(body["items"]) == 10
    ids = [task["id"] for task in body["items"]]
    assert ids == sorted(ids)


def test_task_shape(client):
    """REQ-LIST-04：字段齐全、类型正确。"""
    body = client.get("/api/tasks").get_json()
    for task in body["items"]:
        assert set(task) == TASK_FIELDS
        assert isinstance(task["tags"], list)
        assert all(isinstance(tag, str) for tag in task["tags"])


def test_filter_by_status_open(client):
    """REQ-LIST-02：status=open 只返回未完成任务。"""
    body = client.get("/api/tasks?status=open").get_json()
    assert body["count"] == 5
    assert {task["id"] for task in body["items"]} == {1, 4, 5, 8, 10}
    assert all(task["status"] == "open" for task in body["items"])


def test_filter_by_status_done(client):
    body = client.get("/api/tasks?status=done").get_json()
    assert {task["id"] for task in body["items"]} == {3, 7, 9}


def test_invalid_status_rejected(client):
    """REQ-LIST-02：非法状态返回 400，而不是静默返回空列表。"""
    resp = client.get("/api/tasks?status=blocked")
    assert resp.status_code == 400

    body = resp.get_json()
    assert body["error"] == "invalid_status"
    assert set(body["allowed"]) == {"open", "in_progress", "done"}


def test_count_matches_items(client):
    """REQ-LIST-03：count 必须与 items 长度一致。"""
    for query in ("", "?status=open", "?status=done"):
        body = client.get(f"/api/tasks{query}").get_json()
        assert body["count"] == len(body["items"])


def test_unknown_query_parameter_is_ignored(client):
    """未定义的查询参数不影响既有结果。"""
    body = client.get("/api/tasks?foo=bar").get_json()
    assert body["count"] == 10
