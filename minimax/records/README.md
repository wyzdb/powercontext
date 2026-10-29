# 运行产物

该目录保存 MiniMax 调用与任务运行的记录，是提交材料里"技术使用记录"的原始凭证。

| 路径 | 内容 |
| --- | --- |
| `minimax/calls-YYYYMMDD.jsonl` | 每次 MiniMax 调用的请求、响应、token 用量、时延 |
| `minimax/` 下的其他 JSONL | 后续按任务（如 `patch-*.jsonl`）细分 |

`*.jsonl` 默认不进版本库（见 `.gitignore`）；提交评审时需要固化样例记录，可用
`git add -f records/minimax/<file>.jsonl` 单独纳入。
