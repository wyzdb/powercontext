"""MiniMax 客户端工厂：让 ctx 包不直接依赖 tools/ 的相对路径。"""

from __future__ import annotations

import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from minimax_client import MiniMaxClient  # noqa: E402


def get_client() -> MiniMaxClient:
    return MiniMaxClient.from_env()
