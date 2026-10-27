# 一页技术说明

## 模块结构

`sdd_context` 负责“资料 → 任务上下文 → 状态”的闭环：

1. **DocumentStore**：把规格、代码、测试写入 `sdd_documents(doc_id, version, kind, path, symbol, text)`。
   - seekdb 模式下通过 `pylibseekdb` 启动本地实例，用 MySQL 协议执行建表、导入和候选查询。
   - SQLite 仅作为非 Linux 环境的回退，响应中的 `sources.backend` 明确标注。
2. **ContextBuilder**：按任务词项对最新版本资料打分，分别返回 specs、code、tests，并保留真实 `path`/`doc_id`/`version` 来源。
3. **PowerContextState**：把任务进展 JSON 写入 PowerContext Memory scope，重启 Runtime 后通过 `memory.list()` 读取最新状态。
4. **MiniMax adapter**：把上下文 JSON 作为 system/user prompt 发给 MiniMax，要求返回 unified diff；`agent/run_task.py` 负责回放/应用和测试。
5. **workspace**：费用审批业务工程。`before/` 是目标行为未实现的版本，`after/` 是 MiniMax 补丁后的版本，测试断言目标行为与兼容行为。

## 上下文选择

- 只使用数据库返回的**最新版本**资料，旧版规格不会覆盖新版。
- 规格按任务词项覆盖率排序，保证规范来源优先；代码/测试按词项和路径排序。
- 输出包含 `sources`，说明文档库和 PowerContext 状态库的真实位置。
- 规格更新后重新导入，`context` 的 `version` 和文本随之变化，不依赖固定答案。

## 技术分工

| 技术 | 实际作用 |
| --- | --- |
| MiniMax | 根据 `record/minimax_request.json` 的上下文生成 `minimax_response.patch`，实际修改 `approve()` |
| seekdb / OceanBase | 保存 specs/code/tests 的版本化资料；候选查询和最新版本查询用于构造上下文 |
| PowerContext | Memory scope 保存 `SDD_TASK_STATE:` 任务状态；重启后读取并写入后续上下文 |
| pytest | 修改前目标测试失败，修改后目标测试+回归测试全部通过 |

## 验证结果

`validation/run_validation.py sqlite` 和 seekdb 模式都执行同一流程：

- before 返回码非 0（目标测试失败）
- after 返回码 0（目标+回归通过）
- 上下文包含 `SPEC-001`、`SPEC-002`、`code:approvals`、`test:test_approvals`
- 规格 v1 → v2 重新导入后上下文读取新阈值
- 状态写入后重启模块，`status` 读取到同一任务进展

详细日志见 `record/`，补丁见 `workspace/diff.patch`。
