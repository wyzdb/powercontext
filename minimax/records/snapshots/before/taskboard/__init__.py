"""taskboard —— 一个最小可运行的业务工程，用于比赛验证样例。

只有两层：``store`` 保存任务数据，``app`` 暴露 REST 接口。依赖仅 Flask。
"""

from .app import create_app

__all__ = ["create_app"]
