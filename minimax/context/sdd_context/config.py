"""Runtime settings for the SDD context module."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]  # .../minimax


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


@dataclass(frozen=True)
class Settings:
    """Resolved configuration, one instance per command invocation."""

    root: Path = field(default_factory=lambda: MODULE_ROOT)
    business_root: Path = field(default_factory=lambda: MODULE_ROOT / "business")
    records_dir: Path = field(default_factory=lambda: MODULE_ROOT / "records")
    artifacts_dir: Path = field(default_factory=lambda: MODULE_ROOT / "artifacts")
    state_dir: Path = field(default_factory=lambda: MODULE_ROOT / ".state")

    db_host: str = "127.0.0.1"
    db_port: int = 2881
    db_user: str = "root"
    db_password: str = ""
    db_database: str = "sdd"

    minimax_base_url: str = "https://api.minimax.chat/v1"
    minimax_model: str = "MiniMax-M3"
    minimax_api_key: str = ""

    powercontext_url: str = "http://127.0.0.1:8765"
    powercontext_token: str = ""
    powercontext_scope_name: str = "sdd-context"

    @property
    def spec_dir(self) -> Path:
        return self.business_root / "specs"

    @property
    def source_dir(self) -> Path:
        return self.business_root / "src"

    @property
    def test_dir(self) -> Path:
        return self.business_root / "tests"

    @property
    def powercontext_db(self) -> Path:
        return self.state_dir / "powercontext.db"

    def require_minimax_key(self) -> str:
        if not self.minimax_api_key:
            raise RuntimeError(
                "MINIMAX_API_KEY is not configured; copy .env.example to .env and set it"
            )
        return self.minimax_api_key

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None, root: Path | None = None) -> "Settings":
        base = root or MODULE_ROOT
        file_values = _read_env_file(base / ".env")
        merged = {**file_values, **(env if env is not None else os.environ)}

        def text(name: str, default: str) -> str:
            value = merged.get(name)
            return value if value not in (None, "") else default

        return cls(
            root=base,
            business_root=Path(text("SDD_BUSINESS_ROOT", str(base / "business"))),
            records_dir=Path(text("SDD_RECORDS_DIR", str(base / "records"))),
            artifacts_dir=Path(text("SDD_ARTIFACTS_DIR", str(base / "artifacts"))),
            state_dir=Path(text("SDD_STATE_DIR", str(base / ".state"))),
            db_host=text("SDD_SEEKDB_HOST", "127.0.0.1"),
            db_port=int(text("SDD_SEEKDB_PORT", "2881")),
            db_user=text("SDD_SEEKDB_USER", "root"),
            db_password=text("SDD_SEEKDB_PASSWORD", ""),
            db_database=text("SDD_SEEKDB_DATABASE", "sdd"),
            minimax_base_url=text("MINIMAX_BASE_URL", "https://api.minimax.chat/v1").rstrip("/"),
            minimax_model=text("MINIMAX_MODEL", "MiniMax-M3"),
            minimax_api_key=text("MINIMAX_API_KEY", ""),
            powercontext_url=text("POWERCONTEXT_SERVER_URL", "http://127.0.0.1:8765").rstrip("/"),
            powercontext_token=text("POWERCONTEXT_SERVER_AUTH_TOKEN", ""),
            powercontext_scope_name=text("SDD_SCOPE_NAME", "sdd-context"),
        )
