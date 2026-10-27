# 提交到参赛私有仓库

提交要求：材料放在参赛仓库（从 `oceanbase/powercontext` 导入的私有仓库）的 `minimax/` 目录，
平台记录的分支为 `2026-competition-ecosystem`。本文档给出可直接执行的步骤。

## 1. 准备仓库

```bash
git clone https://github.com/<你的账号>/<私有仓库名>.git
cd <私有仓库名>
git checkout 2026-competition-ecosystem
```

若本地还没有该分支：

```bash
git fetch origin 2026-competition-ecosystem
git checkout -b 2026-competition-ecosystem origin/2026-competition-ecosystem
```

基线分支上只有 `dify/`、`gaode/`、`minimax/`、`qoder/`、`stepfun/` 五个占位目录，
本作品只改 `minimax/`。

## 2. 复制作品

把本目录内容复制到仓库的 `minimax/`（覆盖 `.gitkeep`）：

```powershell
# Windows：robocopy 的 0-7 都是成功，>=8 才是失败
robocopy "C:\path\to\minimax" "C:\path\to\<私有仓库>\minimax" /E `
    /XD .env .state __pycache__ .pytest_cache .tmp /XF .env
```

或直接运行打包脚本（会复制并做三项检查：无 `.env`、无 `.state`、业务代码仍是修改前状态）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\prepare_submission.ps1 -TargetRepo "C:\path\to\<私有仓库>"
```

```bash
# Linux / macOS（rsync 更直观）
rsync -a --exclude .env --exclude .state --exclude __pycache__ --exclude .pytest_cache \
      /path/to/minimax/ /path/to/<私有仓库>/minimax/
```

复制后确认：

- `minimax/.env` **不存在**（只保留 `.env.example`）；
- `minimax/.state/` 不存在（运行期生成，已在 `.gitignore`）；
- `minimax/business/src/orderflow/service.py` 里**没有** `created_after`（初始状态应为未实现）。

也可以使用 `scripts/prepare_submission.ps1`（见下）完成同样的复制与检查。

## 3. 本地验证后提交

```bash
cd <私有仓库>
git status --short
python -m pytest -q minimax/tests          # 上下文模块自测：19 passed
python minimax/scripts/sdd.py doctor        # 需要 seekdb 与 PowerContext 已启动
git add minimax
git commit -m "feat(minimax): SDD 上下文管理系统（seekdb + PowerContext + MiniMax）"
git push origin 2026-competition-ecosystem
git rev-parse HEAD                          # 平台需要填写的 commit hash
```

## 4. 平台提交信息

- 分支：`2026-competition-ecosystem`
- commit：上一步 `git rev-parse HEAD` 的完整 SHA
- 材料目录：`minimax/`

## 5. 常见问题

- **clone/push 报 TLS 证书错误**：切到 OpenSSL 后端后重试
  `git config --global http.sslBackend openssl`；仍失败时检查代理与凭据。
- **私有仓库权限**：平台需要能读取仓库，按赛题页说明在参赛信息里填写带 token 的仓库地址。
- **提交后仍改代码**：平台以固定提交（commit hash）为准，改动后需要重新提交新 hash。
- **体积**：`records/` 与 `artifacts/` 是纯文本，总量在数 MB 以内；不要提交 `.state/`、
  `__pycache__`、`.pytest_cache`。
