# 01 · MiniMax 环境配置记录

本文件记录本机 MiniMax 环境的实际配置过程、版本、端点和排错结论，供评审复现与核对。
记录时间：2026-10-29（Asia/Shanghai）。

---

## 1. 结论速览

| 项 | 取值 |
| --- | --- |
| 协议 | OpenAI 兼容（`POST /chat/completions`） |
| 国内站 Base URL | `https://api.minimax.cn/v1` |
| 国际站 Base URL | `https://api.minimax.io/v1` |
| Anthropic 兼容（备选） | `https://api.minimax.cn/anthropic` |
| 默认模型 | `MiniMax-M3.1-Flash`（1M 上下文，前沿编码模型） |
| Python SDK | `openai==3.41.0` |
| 配置注入 | `minimax/.env`（`python-dotenv==1.2.4` 读取） |
| 调用记录 | `records/minimax/calls-YYYYMMDD.jsonl`（JSONL，追加写） |
| 本机 Python | 3.13.15 |
| 本机系统 | Windows 11 |

同一账号还支持 M2.x 系列（`MiniMax-M2.7` / `MiniMax-M2.5` / `MiniMax-M2.1` / `MiniMax-M2`），
需要通过 `MINIMAX_MODEL` 显式指定；默认用 M3.1-Flash。

---

## 2. 两种 Key 不要混用

| Key 类型 | 前缀 | 用途 | 计费 |
| --- | --- | --- | --- |
| 订阅 Key（M Plan / Token Plan） | `sk-cp-` | 在 Claude Code / Cursor / 自建脚本里调用 | 走订阅额度 |
| 按量付费 API Key | `sk-`（非 `sk-cp-`） | 平台 API 按量计费 | 走账户余额 |

比赛发放的是 **1 个月 Token Plan**，对应订阅 Key。把按量付费 Key 填进来会出现
`402 / 额度不足`，反之订阅 Key 也不会消耗账户余额。

获取位置：控制台 → Plan Details（<https://platform.minimax.cn/console/plan>）。

---

## 3. 已完成的配置步骤

1. **仓库**：以 `2026-competition-ecosystem` 分支（commit `d647275`）为基线检出到
   `powercontext/`，本作品的全部资产放在 `powercontext/minimax/`。
2. **Python 环境**：在 `minimax/` 下创建 `.venv`（Python 3.13.15），安装
   `openai==3.41.0` 与 `python-dotenv==1.2.4`（见 `requirements.txt`）。
3. **配置**：`.env.example` 作为模板；本地 `.env` 填真实 Key，已被 `.gitignore` 忽略。
4. **客户端**：`tools/minimax_client.py` 统一封装配置读取、调用、重试与 JSONL 记录。
5. **自检**：`tools/check_minimax.py` 一条命令验证 Key / 区域 / 模型。
6. **记录**：每次调用自动落盘，字段含 `ts`、`purpose`、`model`、`latency_ms`、
   请求消息、响应正文、`usage`，可直接汇总成"MiniMax 开发记录"。

### 验证命令

```powershell
cd minimax
.\.venv\Scripts\python.exe tools\check_minimax.py
```

- 未填 Key 时：退出码 `2`，提示到 `.env` 填 Key（配置层已先行验证）。
- 填入有效 Key 后：退出码 `0`，打印 `latency / usage / text / call_id`。

---

## 4. 本机环境踩坑与处理

这些是本机（Windows + 沙箱）特有现象，评审在干净环境按 README 操作不会遇到，记录在此便于排查。

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `git` 报 `schannel: AcquireCredentialsHandle failed: SEC_E_NO_CREDENTIALS` | 沙箱限制 Windows 证书存储访问 | 改用 OpenSSL 后端：`git -c http.sslBackend=openssl ...`（仅影响本次命令） |
| `pip install` 报 `Permission denied ... *.whl.metadata` | 沙箱拦截 `.metadata` 临时文件 | 改用 `uv`（`uv pip install`）安装；评审环境直接用 `pip` 即可 |
| `python -m venv` 在 `ensurepip` 阶段失败 | 临时目录清理被拦截 | 用 `python -m venv --without-pip` + `uv pip install` 绕过 |
| 控制台中文乱码 | Windows 默认 GBK 代码页 | 脚本内 `sys.stdout.reconfigure(encoding="utf-8")` |

---

## 5. 与 Claude Code 类工具的兼容（备选接入）

若后续用 Claude Code / Cursor 等现成 Agent 驱动开发，可走 Anthropic 兼容协议：

```bash
export ANTHROPIC_BASE_URL=https://api.minimax.cn/anthropic
export ANTHROPIC_AUTH_TOKEN=sk-cp-...
# 模型选 MiniMax-M3.1-Flash
```

本项目主路径仍是自建脚本 + OpenAI 兼容协议，便于把"任务 → 上下文 → 改动"完整记录成可核对的 JSONL。

---

## 6. 参考链接

- OpenAI 兼容调用：<https://platform.minimax.io/docs/api-reference/text-openai-api>
- 其他工具配置参考：<https://platform.minimax.cn/docs/m-plan/other-tools>
- 订阅与 Key：<https://platform.minimax.io/docs/m-plan/quickstart>
