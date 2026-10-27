# 通过 Dify 控制台 API 构建与验证应用

界面里点节点容易漏配，而且保存失败时没有任何提示（我们踩过：服务端 `code length = 0`）。
所以这套脚本直接调 Dify 控制台 API，把整张图写进去、发布、跑验证。

| 文件 | 作用 |
|---|---|
| `graph_pushed.json` | 最终写入的 14 节点图（节点/边/变量），可作为结构参考 |
| `patch_push.py` | 读 `graph_pushed.json`，做兼容性修补后写回草稿（需先登录拿到 token） |
| `run_draft.py` | 跑一次草稿工作流，打印每个节点状态与最终回复 |
| `e2e.py` | 完整一轮：开局 → 出牌 → 通关 → 下一关，并导出 DSL |
| `check_memory.py` | 查 PowerContext 里某个玩家存档的案卷 |

## 用法

```bash
# 0) 先登录拿 token（有效期 60 分钟），存到临时文件
python3 - <<'PY'
import json, os, urllib.request
body = json.dumps({"email": "you@example.com", "password": "***",
                   "language": "zh-Hans", "remember_me": True}).encode()
req = urllib.request.Request("http://localhost:8080/console/api/login", data=body, method="POST")
req.add_header("Content-Type", "application/json")
tok = json.loads(urllib.request.urlopen(req).read())["data"]["access_token"]
open(os.path.join(os.environ["TEMP"], "dify_token.txt"), "w").write(tok)
PY

# 1) 写入/修补图（会自己 GET 最新 hash，避免 draft_workflow_not_sync）
python3 patch_push.py

# 2) 跑一轮
python3 run_draft.py "开始"

# 3) 完整验证 + 导出 DSL
python3 e2e.py replay1

# 4) 查记忆
python3 check_memory.py ddz-replay1
```

## 脚本里固化了的三个兼容点

1. `assigner` 的 `operation` 枚举是 **`over-write`**（带连字符）
2. `if-else` 的两个分支句柄是 **`true` / `false`**，不是 `source`
3. `template-transform` 的输出变量名是 **`output`**，不是 `text`

这三处写错时，界面不会提示，只有运行时才报错。
