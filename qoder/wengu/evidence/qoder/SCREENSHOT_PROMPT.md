请回顾我们之前的对话，为每轮开发生成截图所需的内容。

对每一轮（共 8 轮），请显示：
1. 我当时提的提示词（简要）
2. 你生成的核心文件（显示文件路径和关键代码，每轮 2-3 个文件）
3. 运行输出（如果有可执行脚本，显示预期输出）

8 轮分别是：
- 第 1 轮：需求拆解 → docs/01-需求与方案.md
- 第 2 轮：连通性验证 → scripts/smoke_test.py
- 第 3 轮：数据管道 → app/ingest.py
- 第 4 轮：混合检索 → app/retrieval.py
- 第 5 轮：记忆层 → app/memory.py
- 第 6 轮：应用层 → app/main.py + web/index.html
- 第 7 轮：复习闭环 → 修改 main.py 和 index.html，实现状态机
- 第 8 轮：交付打包 → scripts/init_demo.sh + evidence 文档

每轮内容要足够详细，让我能直接截图用于比赛提交。
