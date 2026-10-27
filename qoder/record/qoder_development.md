# Qoder development record

## Submission fields

- Qoder account UID: `<fill with the Qoder account UID used for the submission>`
- Qoder Sites URL: `<fill after publishing site/ with public visibility>`
- Repository: https://github.com/wyzdb/powercontext/tree/2026-competition-ecosystem/qoder
- Branch / commit: `2026-competition-ecosystem` / `<fill after the Qoder session>`

## How to complete this record in Qoder

This repository contains the runnable project and the Qoder Sites source. The
final submission must capture the actual Qoder session:

1. Open Qoder, import `wyzdb/powercontext` branch `2026-competition-ecosystem`.
2. Ask Qoder to review `qoder/app` and `qoder/site`, then make at least one
   real UI or backend improvement in the Qoder session.
3. Capture screenshots of the Qoder conversation showing requirement
   decomposition, generated code, debugging and the final diff.
4. Use Qoder Sites to publish `qoder/site/` with “anyone can access”.
5. Put the screenshots in `record/screenshots/`, and fill the UID/site URL and
   commit above.

## Suggested Qoder prompts

- “阅读 qoder/app/store.py 和 app/memory.py，解释 seekdb 与 PowerContext 的分工，并把研究笔记检索改成标题优先排序。”
- “在 qoder/app/static 中增加一个‘本周待办’区域，读取 note-003 的 TODO 并展示。”
- “运行 qoder/validation/run.py，修复任何失败，并给出 before/after 输出。”
- “把 qoder/site 发布为 Qoder Sites，可见范围设为任何人都可访问。”

## Artifact map

| Material | Path |
| --- | --- |
| 源码 | `qoder/app/` |
| 运行说明 | `qoder/README.md` |
| 验证脚本 | `qoder/validation/run.py` |
| 验证结果 | `qoder/record/validation_result.json` |
| 数据库查询记录 | `qoder/record/seekdb_queries.log` |
| 记忆读写记录 | `qoder/record/powercontext_memory.log` |
| Qoder Sites 源码 | `qoder/site/` |
| Qoder 截图 | `qoder/record/screenshots/`（待补充真实截图） |
