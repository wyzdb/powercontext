#!/usr/bin/env python
"""MiniMax 调用客户端（OpenAI 兼容协议）。

设计目标
--------
1. 只用一个入口 ``MiniMaxClient.chat()`` 完成文本/代码调用，方便上下文模块、
   Agent 编排脚本和验证样例复用。
2. 每次调用都写一条 JSONL 记录（默认 ``records/minimax/calls-YYYYMMDD.jsonl``），
   作为提交材料里的"MiniMax 开发记录"和成本/时延统计的来源。
3. 配置全部来自环境变量 / ``.env``，不把 Key 写进代码。

用法::

    from tools.minimax_client import MiniMaxClient

    client = MiniMaxClient.from_env()
    resp = client.chat([{"role": "user", "content": "你好"}], purpose="smoke")
    print(resp.text)

命令行::

    python tools/minimax_client.py "用一句话介绍 seekdb"
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from dotenv import load_dotenv
from openai import OpenAI

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

#: 国内站 / 国际站的 OpenAI 兼容入口
REGION_BASE_URLS: dict[str, str] = {
    "cn": "https://api.minimax.cn/v1",
    "io": "https://api.minimax.io/v1",
}

#: 国内站 / 国际站的 Anthropic 兼容入口（给 Claude Code 之类的工具用）
REGION_ANTHROPIC_BASE_URLS: dict[str, str] = {
    "cn": "https://api.minimax.cn/anthropic",
    "io": "https://api.minimax.io/anthropic",
}

DEFAULT_MODEL = "MiniMax-M3.1-Flash"
DEFAULT_LOG_DIR = Path("records/minimax")

#: 单条消息写日志时的最大字符数，避免异常输入把记录文件撑爆
MAX_LOGGED_CHARS = 200_000


class MiniMaxConfigError(RuntimeError):
    """配置缺失或非法（例如没有填写 MINIMAX_API_KEY）。"""


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def find_env_file(start: Path | None = None) -> Path | None:
    """从给定目录逐级向上查找 ``.env``。"""

    here = (start or Path(__file__).resolve().parent).resolve()
    for parent in (here, *here.parents):
        candidate = parent / ".env"
        if candidate.is_file():
            return candidate
    return None


def ensure_utf8_stdout() -> None:
    """Windows 控制台默认 GBK，统一改成 UTF-8，避免中文日志乱码。"""

    for stream in (sys.stdout, sys.stderr):
        encoding = (getattr(stream, "encoding", "") or "").lower()
        if encoding.replace("-", "") == "utf8":
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover - 老版本/被重定向时忽略
            pass


def mask_key(key: str) -> str:
    """日志/终端里安全展示 Key。"""

    if not key:
        return "<empty>"
    if len(key) <= 10:
        return key[:2] + "*" * max(len(key) - 4, 0) + key[-2:]
    return f"{key[:6]}...{key[-4:]} ({len(key)} chars)"


@dataclass(frozen=True)
class MiniMaxConfig:
    """一次运行所需的全部 MiniMax 配置。"""

    api_key: str
    base_url: str
    model: str = DEFAULT_MODEL
    region: str = "cn"
    timeout: float = 180.0
    max_retries: int = 3
    reasoning_effort: str | None = None
    log_dir: Path = DEFAULT_LOG_DIR

    @classmethod
    def from_env(cls, env_file: str | Path | None = None) -> "MiniMaxConfig":
        """读取 ``.env`` 与环境变量，构造配置。"""

        if env_file is not None:
            path = Path(env_file)
            if not path.is_file():
                raise MiniMaxConfigError(f"指定的 env 文件不存在: {path}")
            load_dotenv(path, override=True)
        else:
            discovered = find_env_file()
            if discovered is not None:
                load_dotenv(discovered, override=False)

        region = (_env("MINIMAX_REGION", "cn") or "cn").lower()
        base_url = _env("MINIMAX_BASE_URL") or REGION_BASE_URLS.get(region, "")
        if not base_url:
            raise MiniMaxConfigError(
                f"不认识的 MINIMAX_REGION={region!r}，请填写 cn / io，"
                "或显式设置 MINIMAX_BASE_URL。"
            )

        api_key = _env("MINIMAX_API_KEY")
        if not api_key:
            raise MiniMaxConfigError(
                "没有找到 MINIMAX_API_KEY。请在 minimax/.env 中填写订阅 Key"
                "（M Plan / Token Plan，通常以 sk-cp- 开头），"
                "参考 .env.example。"
            )

        model = _env("MINIMAX_MODEL", DEFAULT_MODEL) or DEFAULT_MODEL

        try:
            timeout = float(_env("MINIMAX_TIMEOUT", "180") or 180)
        except ValueError as exc:  # pragma: no cover - 防御式
            raise MiniMaxConfigError("MINIMAX_TIMEOUT 必须是数字") from exc

        try:
            max_retries = int(_env("MINIMAX_MAX_RETRIES", "3") or 3)
        except ValueError as exc:  # pragma: no cover - 防御式
            raise MiniMaxConfigError("MINIMAX_MAX_RETRIES 必须是整数") from exc

        log_dir = Path(_env("MINIMAX_LOG_DIR", str(DEFAULT_LOG_DIR)) or DEFAULT_LOG_DIR)

        return cls(
            api_key=api_key,
            base_url=base_url.rstrip("/"),
            model=model,
            region=region,
            timeout=timeout,
            max_retries=max(0, max_retries),
            reasoning_effort=_env("MINIMAX_REASONING_EFFORT") or None,
            log_dir=log_dir,
        )

    def describe(self) -> dict[str, Any]:
        """可安全打印的配置摘要。"""

        return {
            "region": self.region,
            "base_url": self.base_url,
            "model": self.model,
            "api_key": mask_key(self.api_key),
            "timeout_s": self.timeout,
            "max_retries": self.max_retries,
            "reasoning_effort": self.reasoning_effort,
            "log_dir": str(self.log_dir),
        }


# ---------------------------------------------------------------------------
# 返回对象
# ---------------------------------------------------------------------------


@dataclass
class MiniMaxResponse:
    """一次调用的结果。"""

    text: str
    reasoning: str | None
    model: str
    usage: dict[str, Any]
    latency_ms: int
    finish_reason: str | None
    call_id: str
    raw: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> str:
        return (
            f"{self.model} | {self.latency_ms} ms | "
            f"tokens in={self.usage.get('prompt_tokens', '?')} "
            f"out={self.usage.get('completion_tokens', '?')} "
            f"| finish={self.finish_reason}"
        )


# ---------------------------------------------------------------------------
# 客户端
# ---------------------------------------------------------------------------


class MiniMaxClient:
    """对 OpenAI SDK 的薄封装：配置、调用、日志。"""

    def __init__(self, config: MiniMaxConfig):
        self.config = config
        self._client = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout,
            max_retries=config.max_retries,
        )
        self._log_warned = False

    # -- 构造 ---------------------------------------------------------

    @classmethod
    def from_env(cls, env_file: str | Path | None = None) -> "MiniMaxClient":
        return cls(MiniMaxConfig.from_env(env_file))

    # -- 调用 ---------------------------------------------------------

    def chat(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        system: str | None = None,
        model: str | None = None,
        max_completion_tokens: int | None = None,
        reasoning_effort: str | None = None,
        tools: Sequence[Mapping[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        purpose: str = "chat",
        metadata: Mapping[str, Any] | None = None,
        extra_body: Mapping[str, Any] | None = None,
    ) -> MiniMaxResponse:
        """同步调用一次 Chat Completions，并记录 JSONL 日志。"""

        payload = self._build_payload(
            messages,
            system=system,
            model=model,
            max_completion_tokens=max_completion_tokens,
            reasoning_effort=reasoning_effort,
            tools=tools,
            tool_choice=tool_choice,
            extra_body=extra_body,
            stream=False,
        )

        call_id = uuid.uuid4().hex[:12]
        started = time.perf_counter()
        try:
            raw = self._client.chat.completions.create(**payload)
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            self._log(
                call_id=call_id,
                purpose=purpose,
                metadata=metadata,
                payload=payload,
                latency_ms=latency_ms,
                ok=False,
                error=f"{type(exc).__name__}: {exc}",
            )
            raise

        latency_ms = int((time.perf_counter() - started) * 1000)
        data = _as_dict(raw)
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        text = message.get("content") or ""
        reasoning = message.get("reasoning_content")
        usage = data.get("usage") or {}
        finish_reason = choice.get("finish_reason")

        response = MiniMaxResponse(
            text=text,
            reasoning=reasoning,
            model=data.get("model") or payload["model"],
            usage=usage,
            latency_ms=latency_ms,
            finish_reason=finish_reason,
            call_id=call_id,
            raw=data,
        )

        self._log(
            call_id=call_id,
            purpose=purpose,
            metadata=metadata,
            payload=payload,
            latency_ms=latency_ms,
            ok=True,
            response=response,
        )
        return response

    def chat_stream(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        system: str | None = None,
        model: str | None = None,
        max_completion_tokens: int | None = None,
        reasoning_effort: str | None = None,
        purpose: str = "chat-stream",
        metadata: Mapping[str, Any] | None = None,
    ) -> Iterator[str]:
        """流式调用，逐段 yield 文本；结束后写一条汇总日志。

        注意：MiniMax 的思考内容在 ``reasoning_content`` 增量里，这里只 yield
        正文；需要思考过程请改用 :meth:`chat` 并读取 ``response.reasoning``。
        """

        payload = self._build_payload(
            messages,
            system=system,
            model=model,
            max_completion_tokens=max_completion_tokens,
            reasoning_effort=reasoning_effort,
            tools=None,
            tool_choice=None,
            extra_body=None,
            stream=True,
        )
        payload["stream_options"] = {"include_usage": True}

        call_id = uuid.uuid4().hex[:12]
        started = time.perf_counter()
        chunks: list[str] = []
        usage: dict[str, Any] = {}
        finish_reason: str | None = None

        try:
            stream = self._client.chat.completions.create(**payload)
            for chunk in stream:
                data = _as_dict(chunk)
                if data.get("usage"):
                    usage = data["usage"]
                for choice in data.get("choices") or []:
                    delta = choice.get("delta") or {}
                    piece = delta.get("content")
                    if piece:
                        chunks.append(piece)
                        yield piece
                    if choice.get("finish_reason"):
                        finish_reason = choice["finish_reason"]
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            self._log(
                call_id=call_id,
                purpose=purpose,
                metadata=metadata,
                payload=payload,
                latency_ms=latency_ms,
                ok=False,
                error=f"{type(exc).__name__}: {exc}",
            )
            raise

        latency_ms = int((time.perf_counter() - started) * 1000)
        response = MiniMaxResponse(
            text="".join(chunks),
            reasoning=None,
            model=payload["model"],
            usage=usage,
            latency_ms=latency_ms,
            finish_reason=finish_reason,
            call_id=call_id,
        )
        self._log(
            call_id=call_id,
            purpose=purpose,
            metadata=metadata,
            payload=payload,
            latency_ms=latency_ms,
            ok=True,
            response=response,
        )

    # -- 内部 ---------------------------------------------------------

    def _build_payload(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        system: str | None,
        model: str | None,
        max_completion_tokens: int | None,
        reasoning_effort: str | None,
        tools: Sequence[Mapping[str, Any]] | None,
        tool_choice: str | dict[str, Any] | None,
        extra_body: Mapping[str, Any] | None,
        stream: bool,
    ) -> dict[str, Any]:
        full_messages: list[dict[str, Any]] = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(dict(m) for m in messages)

        payload: dict[str, Any] = {
            "model": model or self.config.model,
            "messages": full_messages,
            "stream": stream,
        }
        if max_completion_tokens is not None:
            payload["max_completion_tokens"] = max_completion_tokens

        effort = reasoning_effort or self.config.reasoning_effort
        if effort:
            # MiniMax-M3.1-Flash 用 reasoning_effort 控制思考深度
            payload["reasoning_effort"] = effort

        if tools:
            payload["tools"] = [dict(t) for t in tools]
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        if extra_body:
            payload["extra_body"] = dict(extra_body)
        return payload

    def _log(
        self,
        *,
        call_id: str,
        purpose: str,
        metadata: Mapping[str, Any] | None,
        payload: Mapping[str, Any],
        latency_ms: int,
        ok: bool,
        response: MiniMaxResponse | None = None,
        error: str | None = None,
    ) -> None:
        record: dict[str, Any] = {
            "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
            "call_id": call_id,
            "purpose": purpose,
            "ok": ok,
            "region": self.config.region,
            "base_url": self.config.base_url,
            "model": payload.get("model"),
            "latency_ms": latency_ms,
            "request": _sanitize_payload(payload),
            "metadata": dict(metadata or {}),
        }
        if response is not None:
            record["response"] = {
                "text": _clip(response.text),
                "reasoning": _clip(response.reasoning or ""),
                "finish_reason": response.finish_reason,
            }
            record["usage"] = response.usage
        if error is not None:
            record["error"] = error

        try:
            self.config.log_dir.mkdir(parents=True, exist_ok=True)
            path = self.config.log_dir / f"calls-{datetime.now():%Y%m%d}.jsonl"
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as exc:  # 日志失败不能影响主流程
            if not self._log_warned:
                self._log_warned = True
                print(f"[warn] 无法写入 MiniMax 调用记录: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _as_dict(obj: Any) -> dict[str, Any]:
    """把 SDK 对象/流式 chunk 统一转成 dict。"""

    if isinstance(obj, dict):
        return obj
    dump = getattr(obj, "model_dump", None)
    if callable(dump):
        try:
            return dump()
        except Exception:  # pragma: no cover - 防御式
            pass
    if hasattr(obj, "to_dict"):
        try:
            return obj.to_dict()
        except Exception:  # pragma: no cover - 防御式
            pass
    return json.loads(json.dumps(obj, default=str))


def _sanitize_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """日志里保留请求内容，但裁剪超长文本。"""

    safe: dict[str, Any] = {}
    for key, value in payload.items():
        if key == "messages":
            safe[key] = [
                {
                    "role": m.get("role"),
                    "content": _clip(m.get("content")),
                    **(  # 保留 tool_calls 等字段，便于复盘
                        {"tool_calls": m["tool_calls"]} if m.get("tool_calls") else {}
                    ),
                }
                for m in value
            ]
        elif key == "tools":
            safe[key] = [t.get("function", {}).get("name", "?") for t in value]
        else:
            safe[key] = value
    return safe


def _clip(value: Any) -> Any:
    if isinstance(value, str) and len(value) > MAX_LOGGED_CHARS:
        return value[:MAX_LOGGED_CHARS] + f"\n...[truncated {len(value) - MAX_LOGGED_CHARS} chars]"
    return value


# ---------------------------------------------------------------------------
# 命令行
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    ensure_utf8_stdout()
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("用法: python tools/minimax_client.py \"你的问题\"", file=sys.stderr)
        return 64

    prompt = " ".join(args)
    try:
        client = MiniMaxClient.from_env()
    except MiniMaxConfigError as exc:
        print(f"[config] {exc}", file=sys.stderr)
        return 2

    print(json.dumps(client.config.describe(), ensure_ascii=False, indent=2))
    response = client.chat(
        [{"role": "user", "content": prompt}],
        purpose="cli",
        max_completion_tokens=2048,
    )
    print("\n--- response ---")
    print(response.text)
    print("\n--- meta ---")
    print(response.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
