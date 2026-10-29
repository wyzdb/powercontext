#!/usr/bin/env python
"""MiniMax 环境连通性检查。

用途：在正式写上下文模块之前，确认「Key + 区域 + Base URL + 模型」这一整套
配置可用，并把这次调用写进 ``records/minimax/*.jsonl``。

用法::

    python tools/check_minimax.py
    python tools/check_minimax.py --prompt "用一句话介绍 seekdb" --model MiniMax-M3.1-Flash

退出码：0 成功；2 配置缺失；3 调用失败。
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path

# 允许 ``python tools/check_minimax.py`` 直接运行
sys.path.insert(0, str(Path(__file__).resolve().parent))

import openai  # noqa: E402

from minimax_client import (  # noqa: E402
    MiniMaxClient,
    MiniMaxConfig,
    MiniMaxConfigError,
    REGION_ANTHROPIC_BASE_URLS,
    ensure_utf8_stdout,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="检查 MiniMax API 是否可用")
    parser.add_argument(
        "--prompt",
        default="请只回复这一行：MINIMAX_OK",
        help="测试用的用户消息",
    )
    parser.add_argument("--model", default=None, help="覆盖 MINIMAX_MODEL")
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=1024,
        help="max_completion_tokens（M3.1-Flash 思考也计入，别设太小）",
    )
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    return parser


def main(argv: list[str] | None = None) -> int:
    ensure_utf8_stdout()
    args = build_parser().parse_args(argv)

    try:
        config = MiniMaxConfig.from_env()
    except MiniMaxConfigError as exc:
        print(f"[config] 配置不可用：{exc}", file=sys.stderr)
        print(
            "\n下一步：把 minimax/.env.example 复制成 minimax/.env，"
            "填入 MINIMAX_API_KEY（M Plan 订阅 Key，形如 sk-cp-...）。",
            file=sys.stderr,
        )
        return 2

    summary = config.describe()
    summary["python"] = platform.python_version()
    summary["openai_sdk"] = openai.__version__
    summary["anthropic_base_url"] = REGION_ANTHROPIC_BASE_URLS.get(config.region, "")

    if not args.json:
        print("== MiniMax 环境 ==")
        for key, value in summary.items():
            print(f"  {key:20} {value}")

    client = MiniMaxClient(config)

    try:
        response = client.chat(
            [{"role": "user", "content": args.prompt}],
            model=args.model,
            purpose="env-check",
            max_completion_tokens=args.max_tokens,
        )
    except Exception as exc:  # 网络 / 鉴权 / 额度 / 模型名
        hint = _hint_for(exc)
        print(f"\n[error] 调用失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        if hint:
            print(f"[hint] {hint}", file=sys.stderr)
        return 3

    result = {
        "ok": True,
        "model": response.model,
        "latency_ms": response.latency_ms,
        "finish_reason": response.finish_reason,
        "usage": response.usage,
        "text": response.text,
        "reasoning_chars": len(response.reasoning or ""),
        "call_id": response.call_id,
        "log_dir": str(config.log_dir),
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("\n== 调用结果 ==")
        print(f"  latency            {response.latency_ms} ms")
        print(f"  finish_reason      {response.finish_reason}")
        print(f"  usage              {response.usage}")
        print(f"  reasoning_chars    {len(response.reasoning or '')}")
        print(f"  text               {response.text.strip()[:300]!r}")
        print(f"  call_id            {response.call_id}")
        print(f"  log                {config.log_dir}")

        if not response.text.strip():
            print(
                "\n[warn] 正文为空：M3.1-Flash 的思考 token 也计入上限，"
                "可以调大 --max-tokens 重试。",
                file=sys.stderr,
            )
    return 0


def _hint_for(exc: Exception) -> str:
    status = getattr(exc, "status_code", None)
    message = str(exc)
    if status == 401 or "401" in message:
        return "Key 无效或与区域不匹配：国内站用 MINIMAX_REGION=cn，国际站用 io。"
    if status == 402 or "402" in message or "quota" in message.lower():
        return "额度不足：确认 Token Plan 已开通，且订阅 Key 与按量付费 Key 没有混用。"
    if status == 404 or "404" in message:
        return "模型名或 Base URL 不对：确认 MINIMAX_MODEL=MiniMax-M3.1-Flash、Base URL 以 /v1 结尾。"
    if status == 429 or "429" in message:
        return "触发限流：稍后重试，或调低并发。"
    if "Connection" in type(exc).__name__ or "timeout" in message.lower():
        return "网络不通：检查代理/VPN，或先 curl https://api.minimax.cn/v1/models 看是否 401。"
    return ""


if __name__ == "__main__":
    raise SystemExit(main())
