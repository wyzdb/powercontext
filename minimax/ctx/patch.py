"""用 MiniMax 按上下文生成补丁。

流程：上下文 JSON → 提示词 → MiniMax Chat Completions → 提取 unified diff →
落盘到 ``records/patches/``（可选直接应用到样例工程）。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import ROOT, DEMO_DIR

PATCH_DIR = ROOT / "records" / "patches"
DIFF_BLOCK_RE = re.compile(r"```(?:diff|patch)?\s*\n(.*?)```", re.DOTALL)

SYSTEM_PROMPT = """\
你是一位严格的 Python 后端工程师。你会拿到：项目规格、需要修改的源码、验证测试。
要求：
1. 只输出一个 unified diff（git diff 格式），不要解释、不要输出完整文件。
2. 不得修改任何测试文件，不得修改测试预期。
3. 必须同时满足新规格与既有规格（兼容性约束）。
4. diff 的路径相对于工程根目录，例如 a/taskboard/store.py。
"""


@dataclass
class PatchResult:
    diff: str
    raw_text: str
    path: Path
    call_id: str
    latency_ms: int
    usage: dict[str, Any]


def _read(rel_path: str, root: Path) -> str:
    return (root / rel_path).read_text(encoding="utf-8")


def render_prompt(context: dict[str, Any], root: Path = DEMO_DIR) -> str:
    lines: list[str] = ["# 任务", context.get("task", ""), ""]

    lines.append("# 规格")
    for spec in context.get("specs", []):
        role = "主规格" if spec["role"] == "primary" else "兼容性约束"
        lines.append(f"## {spec['key']}（{role}）{spec['title']}")
        lines.append(_read(spec["path"], root).strip())
        lines.append("")

    lines.append("# 需要修改的代码")
    for code in context.get("code", []):
        symbols = ", ".join(f"{s['name']}(L{s['line']}-{s['end_line']})" for s in code.get("symbols", []))
        lines.append(f"## {code['path']}  相关符号: {symbols}")
        lines.append("```python")
        lines.append(_read(code["path"], root).rstrip())
        lines.append("```")
        lines.append("")

    lines.append("# 验证测试（不得修改）")
    for test in context.get("tests", []):
        role = "目标测试（改前失败，改后必须通过）" if test["role"] == "target" else "回归测试（必须保持通过）"
        lines.append(f"## {test['path']}（{role}）")
        lines.append("```python")
        lines.append(_read(test["path"], root).rstrip())
        lines.append("```")
        lines.append("")

    lines.append("# 输出")
    lines.append("只输出 unified diff，放在 ```diff 代码块里。")
    return "\n".join(lines)


def extract_diff(text: str) -> str:
    """从模型输出里取出 diff 文本。"""

    blocks = DIFF_BLOCK_RE.findall(text)
    for block in blocks:
        stripped = block.strip("\n")
        if "diff --git" in stripped or stripped.startswith("--- "):
            return stripped + "\n"

    # 没有代码块时，退而求其次：从第一个 diff 标记截到结尾
    for marker in ("diff --git", "--- a/"):
        index = text.find(marker)
        if index >= 0:
            return text[index:].strip("\n") + "\n"
    raise ValueError("模型输出里没有找到 unified diff")


def write_prompt(context: dict[str, Any], messages: list[dict[str, str]] | None = None) -> tuple[Path, int]:
    """把完整提示词落盘（不调用模型），返回 (路径, 字符数)。"""

    messages = messages or build_messages(context)
    PATCH_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = PATCH_DIR / f"TASK-001-{stamp}.prompt.md"
    text = "\n\n".join(f"## {m['role']}\n{m['content']}" for m in messages)
    path.write_text(text, encoding="utf-8")
    return path, len(text)


def build_messages(context: dict[str, Any], root: Path = DEMO_DIR) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": render_prompt(context, root)},
    ]


def generate(context: dict[str, Any], *, root: Path = DEMO_DIR, model: str | None = None) -> PatchResult:
    """调用 MiniMax 生成补丁并落盘。"""

    from ._client import get_client  # 延迟导入，避免没有 Key 时模块不可用

    client = get_client()
    messages = build_messages(context, root)
    response = client.chat(
        messages,
        model=model,
        purpose="patch-generation",
        metadata={
            "task": context.get("task"),
            "primary_spec": (context.get("specs") or [{}])[0].get("key"),
            "task_id": context.get("task_id") or "TASK-001",
        },
        max_completion_tokens=8192,
    )

    diff = extract_diff(response.text)
    PATCH_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = PATCH_DIR / f"TASK-001-{stamp}.diff"
    path.write_text(diff, encoding="utf-8")

    transcript = PATCH_DIR / f"TASK-001-{stamp}.prompt.md"
    transcript.write_text(
        "\n\n".join(f"## {m['role']}\n{m['content']}" for m in messages),
        encoding="utf-8",
    )

    return PatchResult(
        diff=diff,
        raw_text=response.text,
        path=path,
        call_id=response.call_id,
        latency_ms=response.latency_ms,
        usage=response.usage,
    )


def summarize(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "task": context.get("task"),
        "specs": [s["key"] for s in context.get("specs", [])],
        "code": [c["path"] for c in context.get("code", [])],
        "tests": [(t["path"], t["role"]) for t in context.get("tests", [])],
    }


def load_context(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
