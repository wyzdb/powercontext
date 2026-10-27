# 运行日志与代码版本

## 1. 环境

| 项 | 值 |
| --- | --- |
| 运行时间 | 2026-10-27（Asia/Shanghai） |
| 操作系统 | Windows 11，PowerShell 7 |
| Python | 3.12.10 |
| PowerContext | 1.4.1（Server + Python Client） |
| seekdb | v1.4.0.0（容器镜像 `quay.io/oceanbase/seekdb:latest`，digest `sha256:4db4961869d554313520d6081fca29265ba6da6db7313311bd8acbed771a956b`） |
| MiniMax | `MiniMax-M3`，`https://api.minimax.chat/v1/chat/completions`，`thinking: disabled` |
| 其他 | PyMySQL 1.2.0、pytest 9.1.1 |

## 2. 命令与退出码

| 步骤 | 命令 | 退出码 | 结果 |
| --- | --- | --- | --- |
| 自检 | `python scripts/sdd.py doctor` | 0 | seekdb / PowerContext / MiniMax 均 ok |
| 建库 | `python scripts/sdd.py db-init --reset` | 0 | 10 张表就绪 |
| 导入 | `python scripts/sdd.py ingest` | 0 | 6 规格 / 17 条款 / 30 符号 / 20 测试 / 1678 词项 |
| 修改前目标测试 | `python -m pytest tests/test_created_after_api.py -q` | 1 | `4 failed`（功能未实现） |
| 修改前回归测试 | `python -m pytest tests/test_service_listing.py tests/test_api_listing.py -q` | 0 | `17 passed` |
| 上下文 | `python scripts/sdd.py build --task-id task-order-created-after` | 0 | 11 条款 / 14 符号 / 4 待改 / 4 目标 / 16 回归 |
| 修改 | `python scripts/sdd.py run --task-id task-order-created-after` | 0 | `outcome=success`，2 个文件 +21 行 |
| 修改后目标测试 | 见 `records/tests/20261027T132238-target.log` | 0 | `4 passed` |
| 修改后回归测试 | 见 `records/tests/20261027T132244-regression.log` | 0 | `17 passed` |
| 全量测试 | `python -m pytest tests -q` | 0 | `21 passed` |
| 状态复用 | `python scripts/sdd.py status --task-id task-order-created-after` | 0 | `completed`，2 条验证结果 |
| 规格更新 | `python scripts/sdd.py spec-demo apply` | 0 | 条款版本 v2，新增 `SPEC-ORD-004/R5` |
| 规格还原 | `python scripts/sdd.py spec-demo restore` | 0 | 回到 17 条条款 |

## 3. 代码版本

正式采纳的一次修改：`run-20261027T132226460027-6a9b05`
（`records/minimax/run-20261027T132226460027-6a9b05.json`）。

| 文件 | 增/删行 | 修改前 sha256（前 16 位） | 修改后 sha256（前 16 位） |
| --- | --- | --- | --- |
| `src/orderflow/api.py` | +5 / -0 | `98bf3db08ee370a8` | `2e289b947f381095` |
| `src/orderflow/service.py` | +16 / -0 | `326f3e4f4512b00e` | `fa39a57c844d1573` |

`artifacts/change.diff`：2801 字节（LF 换行），sha256 前 16 位 `45b4f2054a90b290`（可直接对仓库内文件校验）。
修改前快照在 `artifacts/before/`，修改后快照在 `artifacts/after/`，
两者可用 `python scripts/sdd.py reset-sample` 与 `artifacts/change.diff` 复核。

## 4. 测试日志索引（`records/tests/`）

| 文件 | 阶段 | 结果 |
| --- | --- | --- |
| `20261027T132221-target-before.log` | 样例的修改前目标测试 | 4 failed |
| `20261027T132238-target.log` | 修改后目标测试 | 4 passed |
| `20261027T132244-regression.log` | 修改后回归测试 | 17 passed |
| `20261027T132252-full-suite.log` | 全量测试 | 21 passed |
| `20261027T131850-*`、`131856`、`132011`、`132017`、`132115`、`132120` | 迭代过程的失败/通过记录 | 保留，见下节 |

## 5. 开发迭代记录（真实调用）

| 时间（UTC） | 现象 | 处理 |
| --- | --- | --- |
| 13:12 | `MiniMax-M3` 把 8192 completion tokens 全部用于推理，`content` 为空 | 客户端增加 `thinking: {"type": "disabled"}`，仅对 `M3*` 生效 |
| 13:17 | 补丁行号整体偏移 3 行，严格应用失败 | `patcher` 增加 ±80 行上下文定位（fuzz），仍要求上下文行匹配 |
| 13:18 | 模型把 `import` 插到 `from __future__` 之前，语法错误 | 系统提示增加「保持文件头顺序、追加 import」硬性约束 |
| 13:19 | 模型假设 `order.created_at` 是 `datetime`，运行期 `AttributeError` | 规格 `SPEC-ORD-004/R2` 补充数据契约：`created_at` 是 ISO 字符串 |
| 13:22 | 全部通过 | 采纳 `run-20261027T132226460027-6a9b05` |

这些失败调用保留在 `records/minimax/*.json` 与 `records/tests/` 中，
与最终补丁一起构成可核对的「MiniMax 实际参与」证据。

## 6. 数据规模与耗时

| 指标 | 值 |
| --- | --- |
| 上下文构建 | 15 次 SQL，单次 2–5 ms |
| 索引导入 | 6 规格 / 17 条款 / 30 符号 / 20 测试 / 1678 词项，< 1 s |
| MiniMax 调用 | prompt 4544 tokens，completion 756 tokens，6135 ms |
| 测试 | 目标 0.5 s，回归 1.2 s，全量 7.6 s |
