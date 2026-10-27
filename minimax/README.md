# 规有所依 — SDD 工程上下文模块

这是一个面向小型业务工程的 SDD（Spec-Driven Development）上下文模块：

- **seekdb / OceanBase**：保存并查询规格、代码、测试的版本化资料。
- **PowerContext**：保存任务进展和验证结果，模块重启后读取使用。
- **MiniMax**：根据选中的上下文生成实际代码修改补丁。
- **业务工程**：`workspace/` 下的费用审批模块，带目标测试和回归测试。

## 目录

```
sdd_context/          上下文模块（存储、选择、PowerContext 状态、CLI）
agent/                MiniMax 客户端和任务执行入口
workspace/            可运行业务工程、before/after 快照、测试、diff
data/                 导入 seekdb 的规格、代码、测试资料
validation/           验证样例和自动验收脚本
record/               MiniMax、seekdb、PowerContext、测试日志
```

## 环境

- Python 3.11+
- Linux（seekdb 模式需要 `pylibseekdb`；Windows/macOS 可使用 SQLite 回退）
- PowerContext 仓库的 `src/` 在 `PYTHONPATH` 中

```bash
cd minimax
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH="$(cd .. && pwd)/src"
```

`requirements.txt` 使用 `pylibseekdb==1.3.0.post5`；如果评测环境锁定其他 1.3.x 小版本，替换为环境提供的版本即可。没有 seekdb 绑定时模块自动回退到 SQLite，并在上下文响应的 `sources.backend` 中标注。

## 初始化与调用

在 `minimax/` 目录执行：

```bash
# 导入 data/ 下的 specs、code、tests（写入 seekdb 或 SQLite）
python -m sdd_context.cli init --backend seekdb

# 为任务生成上下文；输出包含必要规格、代码、测试和真实来源
python -m sdd_context.cli context \
  --task-id expense-manager-threshold \
  --task "Expense requests above 500 must require manager approval while existing validation behaviour stays unchanged."

# 保存任务进展
python -m sdd_context.cli state \
  --task-id expense-manager-threshold \
  --task "Expense requests above 500 must require manager approval..." \
  --completed "imported" "context selected" \
  --pending "apply patch" "run tests" \
  --validation '[{"phase":"before","returncode":1}]'

# 模块重启后读取状态
python -m sdd_context.cli status --task-id expense-manager-threshold
```

规格更新：修改 `data/specs/SPEC-001.md` 的 `Version` 和数值，再执行 `init`；`context` 会返回新版本，不会返回固定旧答案。也可以运行：

```bash
python -m sdd_context.cli update-spec --threshold 300
python -m sdd_context.cli context --task-id expense-manager-threshold --task "..."
```

## 运行 MiniMax 代码修改

```bash
export MINIMAX_API_KEY="..."
export MINIMAX_MODEL="MiniMax-Text-01"
python agent/run_task.py
```

没有 API key 时，使用已验证的记录回放：

```bash
python agent/run_task.py --offline
```

## 一键验证

```bash
python validation/run_validation.py seekdb
# 或
python validation/run_validation.py sqlite
```

脚本会：

1. 用 before 快照运行目标测试，确认失败；
2. 应用 MiniMax 补丁对应的 after 快照，确认目标测试和回归测试通过；
3. 导入资料、生成上下文，检查 `SPEC-001`、`SPEC-002`、代码和测试来源；
4. 更新规格到 v2/300，重新导入并确认上下文使用新内容；
5. 保存任务状态，重启模块后读取并再次生成上下文。

结果写入 `record/validation_result.json`，测试日志写入 `record/pytest_before.log` 和 `record/pytest_after.log`。

## 验证样例

`validation/task.json` 定义了要改什么和哪些行为必须保持：

- 目标：`approve(750, "travel", "alice")` 返回 `pending_manager` 且 `requires_manager=true`。
- 目标：`approve(500, ...)` 仍然自动通过。
- 回归：非正金额、空类别、空申请人仍抛 `ValueError`；审计字段不丢失。

重置：`git checkout -- data/specs`，删除 `.sdd/`、`workspace/expense_approval/approvals.py` 后重新运行 before/after 步骤即可。

## 已知限制

- seekdb 绑定只提供 Linux 构建；其他平台使用 SQLite 回退，`sources.backend` 会显示实际后端。
- 回放模式使用 `record/minimax_response.patch`，不重新调用模型；需要重新生成时设置 `MINIMAX_API_KEY`。
- 这是任务上下文和代码修改的最小可运行样例，不包含完整 Agent 会话恢复。
