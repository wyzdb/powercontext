"""用 MiniMax 按上下文生成补丁。

流程：上下文 JSON → 提示词 → MiniMax Chat Completions → 得到修改后的完整文件 →
用 difflib 计算 unified diff → 落盘并（可选）应用。

为什么不直接让模型输出 diff：模型给的 hunk 行数经常对不上（本次第一次尝试就出现
``corrupt patch``）。让模型只负责"改成什么"，diff 由本地计算，格式永远合法，
也更容易核对模型到底改了哪几行。
"""

from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import DEMO_DIR, ROOT

PATCH_DIR = ROOT / "records" / "patches"
DIFF_BLOCK_RE = re.compile(r"```(?:diff|patch)?\s*\n(.*?)```", re.DOTALL)
FILE_BLOCK_RE = re.compile(r"###\s*FILE:\s*(\S+)\s*\n```[a-zA-Z0-9_+-]*\n(.*?)\n```", re.DOTALL)

SYSTEM_PROMPT = """\
你是一位严格的 Python 后端工程师。你会拿到：项目规格、需要修改的源码、验证测试。
要求：
1. 不得修改任何测试文件，不得修改测试预期。
2. 必须同时满足新规格与既有规格（兼容性约束）。
3. 只改必要的代码，保持既有风格与函数签名。
"""

OUTPUT_RULE_FILES = """\
# 输出
只输出被修改的文件，每个文件一个块，格式严格如下（不要输出 diff、不要解释、不要省略内容）：

### FILE: taskboard/store.py
```python
<该文件的完整内容>
```

只列出真正需要修改的文件。
"""

OUTPUT_RULE_DIFF = """\
# 输出
只输出一个 unified diff，放在 ```diff 代码块里，路径相对工程根目录（a/taskboard/store.py）。
"""


@dataclass
class PatchResult:
    diff: str
    raw_text: str
    path: Path
    call_id: str
    latency_ms: int
    usage: dict[str, Any]
    files: dict[str, str]


def _read(rel_path: str, root: Path) -> str:
    return (root / rel_path).read_text(encoding="utf-8")


def render_prompt(context: dict[str, Any], root: Path = DEMO_DIR, output_format: str = "files") -> str:
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

    lines.append(OUTPUT_RULE_DIFF if output_format == "diff" else OUTPUT_RULE_FILES)
    return "\n".join(lines)


def build_messages(context: dict[str, Any], root: Path = DEMO_DIR, output_format: str = "files") -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": render_prompt(context, root, output_format)},
    ]


def parse_files(text: str) -> dict[str, str]:
    """从模型输出里解析 "### FILE: path + fenced block"。"""

    files = {path.strip(): content for path, content in FILE_BLOCK_RE.findall(text)}
    if not files:
        raise ValueError("模型输出里没有找到 `### FILE: <path>` 代码块")
    return files


def extract_diff(text: str) -> str:
    """从模型输出里取出 diff 文本（兼容旧模式）。"""

    for block in DIFF_BLOCK_RE.findall(text):
        stripped = block.strip("\n")
        if "diff --git" in stripped or stripped.startswith("--- "):
            return stripped + "\n"

    for marker in ("diff --git", "--- a/"):
        index = text.find(marker)
        if index >= 0:
            return text[index:].strip("\n") + "\n"
    raise ValueError("模型输出里没有找到 unified diff")


def diff_from_files(files: dict[str, str], root: Path = DEMO_DIR) -> str:
    """用 difflib 计算 unified diff（保证行数正确、格式合法）。"""

    chunks: list[str] = []
    for path, new_text in files.items():
        old_text = _read(path, root)
        if not old_text.endswith("\n"):
            old_text += "\n"
        if not new_text.endswith("\n"):
            new_text += "\n"
        if old_text == new_text:
            continue

        diff_lines = difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            n=3,
        )
        body = "".join(diff_lines)
        chunks.append(f"diff --git a/{path} b/{path}\n{body}")

    if not chunks:
        raise ValueError("模型给出的文件与现有内容完全一致，没有产生改动")
    return "".join(chunks)


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def generate(
    context: dict[str, Any],
    *,
    root: Path = DEMO_DIR,
    model: str | None = None,
    output_format: str = "files",
) -> PatchResult:
    """调用 MiniMax 生成改动并落盘。"""

    from ._client import get_client  # 延迟导入，避免没有 Key 时模块不可用

    client = get_client()
    messages = build_messages(context, root, output_format)
    response = client.chat(
        messages,
        model=model,
        purpose="patch-generation",
        metadata={
            "task": context.get("task"),
            "primary_spec": (context.get("specs") or [{}])[0].get("key"),
            "task_id": context.get("task_id") or "TASK-001",
            "output_format": output_format,
        },
        max_completion_tokens=8192,
    )

    if output_format == "files":
        files = parse_files(response.text)
        diff = diff_from_files(files, root)
    else:
        files = {}
        diff = extract_diff(response.text)

    PATCH_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    path = PATCH_DIR / f"TASK-001-{stamp}.diff"
    _write_text(path, diff)

    _write_text(
        PATCH_DIR / f"TASK-001-{stamp}.prompt.md",
        "\n\n".join(f"## {m['role']}\n{m['content']}" for m in messages),
    )
    _write_text(PATCH_DIR / f"TASK-001-{stamp}.response.md", response.text)

    if files:
        snapshot = PATCH_DIR / f"TASK-001-{stamp}.files"
        for rel, content in files.items():
            target = snapshot / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            _write_text(target, content)

    return PatchResult(
        diff=diff,
        raw_text=response.text,
        path=path,
        call_id=response.call_id,
        latency_ms=response.latency_ms,
        usage=response.usage,
        files=files,
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
