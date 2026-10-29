# MiniMax SDD 提测指导

## 填写哪个仓库和版本

| 字段 | 内容 |
| --- | --- |
| 项目/题目 | MiniMax × OceanBase / 规有所依——面向软件持续演进的 SDD 上下文管理系统 |
| 仓库 | `https://github.com/wyzdb/powercontext` |
| 交付分支 | `minimax-sdd-delivery-2026-10-29` |
| commit | 从此分支最新提交页复制完整 40 位 SHA，须与交付回执相同 |
| 材料目录 | `minimax/` |
| 开发基线 | 官方 `2026-competition-ecosystem`，保留原始 Git 历史 |

不要提交 PDF 分支、PowerContext 普通代码题分支、seekdb 仓库或仅一个 ZIP。GitHub 提交不会自动产生比赛成绩。若平台要求私有仓库授权，按官方 GitHub 指南配置，真实凭据只放私密配置，不放源码/截图/Markdown。

## 先读什么

1. `minimax/README.md`：完整运行入口及外部服务配置。
2. `minimax/docs/verification-sample.md`：任务、规格、必须保留的旧行为与重置步骤。
3. `minimax/docs/one-page.md`：一页技术分工。
4. `minimax/docs/live-e2e-2026-10-29.md`：**本轮真实服务端到端验证**（三项技术的真实参与证据）。
5. `minimax/docs/run-log.md`：2026-10-27 历史记录 + 2026-10-29 真实端到端运行的命令与退出码。
6. `minimax/docs/native-validation-2026-10-29.md`：当轮离线一致性校验与边界（保留为过程记录）。

## 本轮已完成真实服务端到端验证

2026-10-29 已真实拉起 seekdb `v1.4.0.0` 容器、PowerContext `1.4.1` 服务端，并调用
MiniMax 官方接口 `https://api.minimaxi.com/v1` 完成一次代码修改，命令、退出码与证据见
`docs/live-e2e-2026-10-29.md`：

| 环节 | 结果 |
| --- | --- |
| 修改前目标测试 | 4 failed（`AssertionError`，功能未实现） |
| MiniMax 调用 | `MiniMax-M3`，请求 ID `073232ae526ecd34c40d866df3801cd7`，补丁 2 个文件 |
| 数据库 | seekdb 容器内建库建表，本任务查询记录 212 条进入上下文 |
| 修改后测试 | 目标 4 passed、回归 17 passed、全量 21 passed |
| 状态复用 | 新进程读回 `completed` 与 2 条验证结果并注入新上下文 |
| 规格更新 | `spec-demo apply` 后上下文出现 v2 与新增条款 `SPEC-ORD-004/R5` |

离线复核（不发起服务调用，只校验记录与源码）：

```powershell
cd minimax
python scripts/verify_submission.py
```

预期：修改前目标 4 failed（功能断言）、修改前回归 17 passed、修改后全量 21 passed、模块 24 passed；脚本自身退出码为 0。前后测试没有改动。结果写入 `records/native-validation-2026-10-29-live/`，
其中 `live_model_called`、`live_database_queried`、`live_powercontext_restart` 三个标记由记录算出。

此命令不会调用模型或数据库，不能替代完整端到端验收；完整端到端验收已由上面的本轮运行覆盖。

## 具备真实服务后的端到端验证（评审可复现）

以下步骤在有真实服务的环境可直接复现，本轮已按此执行过一遍。

1. 按 `requirements.txt` 准备依赖；提供可连接的 seekdb/OceanBase MySQL 实例和 PowerContext 1.4.1 服务。也可连接已有远程服务，无需在当前电脑启动 Linux。
2. 在不提交 Git 的 `.env` 中配置实例地址、端口、用户、密码和 PowerContext 地址。MiniMax 使用你账户可用的**官方接口**、模型和密钥；历史记录中的地址/模型只表示当时使用的配置，不代表本轮已验证可用性。
3. 检查地址正确后运行以下命令，数据库应为专门的样例库：

```powershell
python scripts/sdd.py doctor
python scripts/sdd.py db-init
python scripts/sdd.py ingest
python scripts/run_sample.py
```

样例会重置本项目业务代码、生成模型补丁、运行相同目标/回归测试并写状态。`db-init --reset` 和 `reset-sample --clear-state` 会清理样例数据，勿指向生产库。运行样例后将新记录与实际源码版本一起保存，不覆盖历史记录伪装成新调用。

4. 核对模型请求/上下文/补丁确实对应；数据库查询的实际结果用于上下文。新进程执行 `status` 和 `build --json`，确认 PowerContext 中已保存状态被读取并使用。
5. 运行 `spec-demo apply`，重新 `ingest`、`build`，确认规格 v2 和 R5 出现在上下文，再执行 `spec-demo restore` 与重新导入。不能只检查连接成功。

六个必做项全部满足才有 20 分；本轮已完成上述端到端运行并留下可核对记录，但正式得分以评审在干净环境的实际执行为准。提交后保存平台记录 ID、实际仓库、分支、完整 SHA 和日志，本轮未自动提测。

官方题面：https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/qlqnoryzrs7gtqbw

比赛入口：https://open.oceanbase.com/train/detail/21
