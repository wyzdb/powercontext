"""路径与数据库配置。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

#: minimax/ 目录
ROOT = Path(__file__).resolve().parent.parent

#: 验证样例工程根目录
DEMO_DIR = ROOT / "demo" / "taskboard"


@dataclass(frozen=True)
class DBConfig:
    host: str = "127.0.0.1"
    port: int = 2881
    user: str = "root"
    password: str = ""
    database: str = "mmx_ctx"

    @classmethod
    def from_env(cls) -> "DBConfig":
        return cls(
            host=os.getenv("SEEKDB_HOST", "127.0.0.1"),
            port=int(os.getenv("SEEKDB_PORT", "2881")),
            user=os.getenv("SEEKDB_USER", "root"),
            password=os.getenv("SEEKDB_PASSWORD", ""),
            database=os.getenv("SEEKDB_DB", "mmx_ctx"),
        )
