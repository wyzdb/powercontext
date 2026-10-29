# 一页技术说明

## 1. 问题与目标

AI 开发助手改代码时缺三样东西：**该守哪些规格**、**该改哪个符号**、**改完怎么验证**。
本作品把这三样从散落的文档和代码里取出来，组装成一份可追溯的任务上下文，并在任务中断后还能接着做。

## 2. 模块结构

```
                 ┌──────────────────────────────┐
  任务文本 ─────▶ │ ctx.retrieve  打分 + 引用展开  │
                 └──────────────┬───────────────┘
                                │ 读 documents / spec_refs
                 ┌──────────────▼───────────────┐
                 │  seekdb (mmx_ctx)            │
                 │  documents / spec_refs       │
                 └──────────────▲───────────────┘
                                │ 导入规格、代码、测试 + 解析引用
                 ┌──────────────┴───────────────┐
                 │ demo/taskboard（业务工程）     │
                 └──────────────────────────────┘

  上下文 JSON ──▶ ctx.patch ──▶ MiniMax ──▶ unified diff ──▶ git apply
       │
       └──▶ ctx.state ──▶ PowerContext（Memory，重启后可读）
```

| 文件 | 职责 |
| --- | --- |
| `ctx/db.py` | seekdb 建库建表、连接（pymysql，MySQL 协议） |
| `ctx/importer.py` | 扫描样例工程，解析「适用模块 / 关联测试 / 上游规格」与 `REQ-*` 条目 |
| `ctx/retrieve.py` | 任务切词 → 文档打分 → 主规格 → 引用展开 → 上下文 JSON |
| `ctx/patch.py` | 组装提示词、调 MiniMax、提取 diff 并落盘 |
| `ctx/state.py` | PowerContext Memory 的写/读，Scope 自动发现与缓存 |
| `ctx/cli.py` | `import / build / patch / state-save / state-load / stats` |

## 3. 上下文怎么选

1. **切词**：英文按词、中文按二元组（不引分词库，保证零额外依赖）。
2. **打分**：标题命中权重 3、正文命中权重 1，单篇封顶 5 次，避免长文堆分。
3. **主规格**：得分最高的规格；其「上游规格」作为兼容性约束一并带上。
4. **引用展开**：读 `spec_refs`，把主规格的「适用模块」映射成代码文件、「关联测试」映射成目标测试；约束规格的关联测试映射成回归测试。
5. **符号定位**：对每个代码文件，按「函数名 + docstring + 源码片段」的相关度挑出 1–3 个符号，给出起止行号。

这样即使 `app.py` 正文里没有"标签"二字，也能通过 SPEC-002 声明的 `适用模块` 精确落到 `list_tasks` / `filter_tasks`。

## 4. 三种技术怎么分工

| 技术 | 承担的作用 | 落点 |
| --- | --- | --- |
| **MiniMax M3.1-Flash** | 读上下文，生成符合规格的 unified diff | `ctx/patch.py`，记录在 `records/minimax/*.jsonl` |
| **seekdb** | 存规格/代码/测试全文与引用关系，供检索 | `mmx_ctx.documents` / `mmx_ctx.spec_refs` |
| **PowerContext** | 存任务阶段、已完成/待办、验证结果，重启后复用 | `ctx/state.py`，Scope `mmx-sdd-taskboard` |

## 5. 数据模型

| 表 | 关键字段 | 用途 |
| --- | --- | --- |
| `documents` | `doc_key`（唯一）、`kind`（spec/code/test）、`path`、`content`、`sha256`、`meta` | 全文与元数据；`sha256` 用于确认上下文引用的是哪一版 |
| `spec_refs` | `spec_key`、`target_path`、`relation`（module/test/regression/spec） | 规格与代码/测试之间的可追溯关系 |
| `task_state` | `task_id`、`stage`、`payload` | 预留（实际状态走 PowerContext） |

## 6. 关键取舍

- **不引向量检索**：样例只有 9 篇文档，词面匹配 + 显式引用足够，且结果可解释、可复现；规模上来后再换 embedding 不影响上层契约。
- **上下文模块是 CLI 而不是 MCP**：CLI 的输出就是 JSON，评审可以 `--out` 落盘逐字段核对；后续要包成 MCP 工具只是加一层壳。
- **状态存 Memory 而不是文件**：任务状态要跨进程、跨会话，PowerContext 的 artifact/revision 能给出可追溯的版本号。
