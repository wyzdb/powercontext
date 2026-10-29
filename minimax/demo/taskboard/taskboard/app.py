"""HTTP 接口层。

视图函数放在模块级，便于上下文模块按符号定位到具体函数（而不是只能定位到
``create_app`` 这个工厂），也便于测试直接 import。
"""

from __future__ import annotations

from flask import Flask, jsonify, request

from .store import STATUSES, all_tasks, filter_tasks


def health():
    return jsonify({"status": "ok"})


def list_tasks():
    """GET /api/tasks：返回任务列表，支持 status 和 tag 过滤。"""

    status = request.args.get("status")
    if status is not None and status not in STATUSES:
        return (
            jsonify(
                {
                    "error": "invalid_status",
                    "message": f"status 只能是 {', '.join(STATUSES)}",
                    "allowed": list(STATUSES),
                }
            ),
            400,
        )

    tag = request.args.get("tag") or None
    items = filter_tasks(all_tasks(), status=status, tag=tag)
    return jsonify({"items": items, "count": len(items)})


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["JSON_AS_ASCII"] = False
    app.add_url_rule("/api/health", "health", health, methods=["GET"])
    app.add_url_rule("/api/tasks", "list_tasks", list_tasks, methods=["GET"])
    return app
