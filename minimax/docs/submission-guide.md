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
4. `minimax/docs/run-log.md`：2026-10-27 历史真实运行记录索引。
5. `minimax/docs/native-validation-2026-10-29.md`：本轮修改与实际验证范围。

## 不启动 Linux 的本轮验证

从仓库根目录进入 `minimax`，使用已安装 pytest 的 Python：

```powershell
cd minimax
python scripts/verify_submission.py
```

预期：修改前目标 4 failed（功能断言）、修改前回归 17 passed、修改后全量 21 passed、模块 23 passed；脚本自身退出码为 0。前后测试没有改动。结果写入 `records/native-validation-2026-10-29/`。

此命令不会调用模型或数据库，不能替代完整端到端验收。

## 具备真实服务后的端到端验证

以下是供评审/后续独立环境执行的步骤，本轮没有启动这些服务或恢复依赖。

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

六个必做项全部满足才有 20 分；本轮原生测试与历史记录一致性检查不等同于正式通过。提交后保存平台记录 ID、实际仓库、分支、完整 SHA 和日志，本轮未自动提测。

官方题面：https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/qlqnoryzrs7gtqbw

比赛入口：https://open.oceanbase.com/train/detail/21
