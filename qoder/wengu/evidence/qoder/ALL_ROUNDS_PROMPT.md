# 温故项目 · 八轮开发回顾提示词

> 复制以下全部内容，粘贴到 Qoder 历史对话中，一次性生成所有截图所需的对话内容。

---

## 提示词

请回顾温故项目的完整开发过程，按以下 8 轮依次展示每轮的关键对话、生成的文件和运行结果。每轮需要显示：

1. **用户提示词**（当时提的需求）
2. **Qoder 回复要点**（做了什么）
3. **生成的核心文件**（显示文件路径和关键代码片段）
4. **运行输出**（如果有可执行脚本，显示预期输出）

---

### 第 1 轮：需求拆解

**用户提示词**：
```
先把 data/raw/ 的 6 篇 markdown 逐篇读一遍，统计主题覆盖、概念重叠、规模判断，然后产出 docs/01-需求与方案.md，包括：
- 用户与场景（谁、什么时候、现在怎么做、痛在哪）
- 功能边界（做四件事、不做什么）
- 技术分工表（seekdb、PowerContext、LLM、Qoder 各负责什么）
- 数据模型（9 张表的建表 SQL，字段约定，约束）
- 混合检索方案（一条 SQL 完成向量 + 全文 + 标量过滤）
- 语料质量管控（review_status 字段）
```

**Qoder 回复要点**：
- 分析 6 篇语料：23 节 / 12699 字 / 29 块
- 识别 5 个跨篇概念（measure-first、shared-vs-distributed 等）
- 产出完整需求文档，包含 9 张表建表 SQL
- 设计 RRF 融合检索方案（k=60）

**生成文件**：`docs/01-需求与方案.md`（约 400 行）

---

### 第 2 轮：连通性验证

**用户提示词**：
```
最小连通性验证，不要写任何业务逻辑。写一个 scripts/smoke_test.py，只做三件事：
1. 连上 seekdb（参数从 .env 读）
2. 确认 wengu 库在
3. 确认 9 张业务表都在并打出行数

依赖只有 pymysql。失败时退出码 1，成功退出码 0。
```

**Qoder 回复要点**：
- 极简 .env 解析（不引第三方依赖）
- 9 张表名硬编码在 EXPECTED_TABLES
- 行数用 COUNT(*) 而非 information_schema（seekdb 上估算值不准）
- 失败信息统一包成 ProbeError

**生成文件**：`scripts/smoke_test.py`（约 150 行）

**预期运行输出**：
```
seekdb: ok host=127.0.0.1 port=2881 user=root password=<set>
server: ok version=5.7.25-OceanBase-v4.3.3.1
database: ok wengu
table: ok kb_meta         rows=7
table: ok doc_meta        rows=6
table: ok chunks          rows=23
table: ok concept         rows=40
table: ok chunk_concept   rows=87
table: ok concept_edge    rows=0
table: ok quiz_item       rows=0
table: ok qa_log          rows=0
table: ok quiz_attempt    rows=0
tables: ok 9/9 present
```

---

### 第 3 轮：数据管道

**用户提示词**：
```
产出 app/ingest.py，把 data/raw/ 的 6 篇 markdown 灌进 seekdb。

流程：
1. 解析 front matter（doc_id、title、course 等）
2. 按 "##" 切节（第一个标题前的内容丢弃）
3. 向量化（用 app.embed 的 embed_texts）
4. 写 doc_meta / chunks / concept / chunk_concept

幂等：同 doc_id 先删后插。chunk_uid 用 sha1(source_file|section_no|part_no) 保证可复现。

概念关联规则：标题里出现记 primary，正文出现记 mention。
```

**Qoder 回复要点**：
- DOC_META 字典映射 doc_id → (topic, level, has_code)
- load_concepts() 从 §4.8 表格读取受控词表
- fit_idf() 拟合 IDF 权重
- 事务提交，失败回滚

**生成文件**：`app/ingest.py`（约 200 行）

**预期运行输出**：
```
语料 6 篇，向量方案 = dashscope（1024 维）
  01-architecture.md        4 节   1719 字
  02-performance.md         4 节   1628 字
  03-mpi-basics.md          4 节   2730 字
  04-collectives.md         4 节   2145 字
  05-openmp.md              4 节   2791 字
  06-design.md              3 节   1698 字
概念词表 40 条，切片 23 块

拟合 IDF...
向量化中...
  完成，首条维度 1024
  概念关联 87 条

入库完成：chunks=23  concept=40
```

---

### 第 4 轮：混合检索

**用户提示词**：
```
产出 app/retrieval.py，实现一条 SQL 完成向量 + 全文 + 标量过滤的融合检索。

要求：
- 用 CTE 写两个支路：vec（l2_distance + APPROXIMATE）和 ft（MATCH ... AGAINST）
- RRF 融合：1/(60+rank)，k=60 固定写死
- 标量过滤写在两个支路子查询内部（course、topic、level、has_code、review_status）
- 可选 JOIN chunk_concept 按概念过滤
- 返回 top 3，带 heading_path、source_file、融合分、两支路排名、词面覆盖率
- 命中阈值：fused < 0.0099 判为未命中
- 降级路径：全文索引不可用时只走向量支路
```

**Qoder 回复要点**：
- search() 函数返回 {hits, degraded, latency_ms, coverage}
- 词面覆盖率 = 查询 bigram 命中数 / 总 bigram 数
- 未命中时返回空 hits + note 说明
- 异常统一抛 MySQLError 或 RuntimeError

**生成文件**：`app/retrieval.py`（约 180 行）

**预期检索结果示例**（查询"伪共享"）：
```
命中 3 条，点开卡片看原文（156ms）

[1] 《并行硬件与体系结构》>> 共享内存与分布式内存
    融合 0.0285 | 向量 #1 全文 #2 | 词面覆盖 0.67
    data/raw/01-architecture.md  chunk#5

[2] 《性能指标与扩展性》>> Amdahl 定律
    融合 0.0198 | 向量 #3 全文 #1 | 词面覆盖 0.45
    data/raw/02-performance.md  chunk#8

[3] 《OpenMP 共享内存编程》>> 数据作用域与竞争
    融合 0.0156 | 向量 #2 全文 #4 | 词面覆盖 0.33
    data/raw/05-openmp.md  chunk#17
```

---

### 第 5 轮：记忆层

**用户提示词**：
```
产出 app/memory.py，实现 PowerContext 客户端。

API（2026-10-28 实测）：
- 建 scope  POST /v1/scopes              {title, summary, idempotency_key} -> scope_id
- 写记忆    POST /v1/memory/remember     {scope_id, kind, text} -> artifact_id
- 列记忆    POST /v1/memory/entries/list {scope_id} -> {entries:[...], next_cursor}

设计要点：
- 每学习者一个 scope，惰性创建，用 idempotency_key 保证幂等
- 创建结果缓存在 data/pc_scopes.json
- 记忆格式：[[wengu]] + JSON（payload 包含 concept、count、status、evidence、at）
- 状态机：新学 → 巩固（连对 1 次）→ 掌握（连对 3 次）
- 同一 concept 多条记录只认 count 最大的那条

实现 4 个函数：
- scope_for(learner) -> scope_id
- remember(learner, kind, payload) -> artifact_id
- get_entries(learner) -> list[dict]
- get_profile(learner) -> {ok, items, note}
- upsert_weakness(learner, concept, wrong_answer) -> {ok, count, artifact_id, note}
- advance_progress(learner, concept) -> {ok, status, artifact_id, note}
```

**Qoder 回复要点**：
- _post() 统一封装 HTTP 请求，处理 401/403/JSON 解析异常
- _encode/_decode 处理 [[wengu]] 前缀
- _latest_by_concept() 取同一 concept 的最大 count
- get_profile() 返回按 count 降序排列的弱点列表

**生成文件**：`app/memory.py`（约 190 行）

**预期 PowerContext 调用日志**：
```
POST /v1/scopes -> {"scope_id": "scp_792c2zf5vz0463n82tgd0w2z31"}
POST /v1/memory/remember -> {"records": [{"artifact": {"artifact_id": "art_abc123"}}]}
POST /v1/memory/entries/list -> {"entries": [...], "next_cursor": null}
```

---

### 第 6 轮：应用层

**用户提示词**：
```
产出 app/main.py + web/index.html。

FastAPI 应用，端点：
- GET /                    返回 web/index.html
- POST /api/ask            混合检索问答（调用 app.retrieval.search）
- GET  /api/quiz           出题（检索概念相关切片，让 LLM 生成题目）
- POST /api/grade          判分（LLM 判断对错，调用 memory 写弱点/进度）
- GET  /api/profile/{learner}  读学习档案（调用 memory.get_profile）

前端单页，三个功能区：
1. 提问：输入框 + 检索按钮，返回带出处的卡片（可展开看原文）
2. 出题：概念输入框 + 出题按钮，显示题目 + 答案输入框 + 提交判分
3. 我的弱点：表格显示概念/次数/状态/上次错答，下方显示今日复习清单

样式： serif 字体，米色背景，深绿强调色，卡片式布局。
```

**Qoder 回复要点**：
- load_env_file() 在 import app.embed 之前调用（DIM/PROVIDER 是导入期定值）
- _llm() 统一封装百炼 API 调用
- grade() 判分逻辑：verdict.startswith("对") 判正确
- 前端用 textContent 而非 innerHTML（防 XSS）
- API 地址自动适配（http 协议用相对路径，file 协议用绝对路径）

**生成文件**：
- `app/main.py`（约 260 行）
- `web/index.html`（约 300 行）

**预期 Web UI**：
```
┌─────────────────────────────────────────────┐
│  温故                                        │
│  把一份讲义变成会记住你弱点的复习教练          │
├─────────────────────────────────────────────┤
│  提问                                        │
│  [________________] [检索]                   │
│  命中 3 条，点开卡片看原文（156ms）           │
│  ┌─────────────────────────────────────┐    │
│  │ 原文 《并行硬件》>> 共享内存         │    │
│  │ doc_id architecture | topic ...     │    │
│  │ 融合 0.0285 | 向量#1 全文#2         │    │
│  │ 正文内容...                          │    │
│  └─────────────────────────────────────┘    │
├─────────────────────────────────────────────┤
│  出题                                        │
│  [伪共享________] [出题]                     │
│  在编写并行程序前，为什么需要首先明确...      │
│  [________________________]                  │
│  [________________________]                  │
│  [提交判分]                                  │
├─────────────────────────────────────────────┤
│  我的弱点                                    │
│  learner = demo                              │
│  ┌─────────┬──────┬──────┬──────────┐       │
│  │ 概念    │ 次数 │ 状态 │ 上次错答 │       │
│  ├───────────────┼──────┼──────────       │
│  │ 伪共享  │ 错 1 │ 新学 │ ...      │       │
│  └─────────┴──────┴──────┴──────────┘       │
│  今日复习：伪共享 → 负载均衡                 │
└─────────────────────────────────────────────┘
```

---

### 第 7 轮：复习闭环

**用户提示词**：
```
把 seekdb 和 PowerContext 真正咬合起来。

修改 app/main.py 的 grade() 端点：
- 判分后根据对错调用 memory.advance_progress 或 memory.upsert_weakness
- 状态机：新学 → 巩固（连对 1 次）→ 掌握（连对 3 次）
- 答错重置为新学，count+1
- 返回 memory_ok 和 memory_note 给前端

修改 web/index.html：
- 判分结果显示"✅ 对"或"❌ 错" + 反馈
- 如果 memory_ok=false，显示"（记忆未写入：PC 未接入）"
- 弱点表格和复习清单从 /api/profile 读取

验证流程：
1. 答错"伪共享" → 弱点表新增一行（count=1, status=新学）
2. 答对"伪共享" → status 变为巩固
3. 再答对 2 次 → status 变为掌握
4. 再答错 → 重置为新学，count+1
```

**Qoder 回复要点**：
- grade() 函数分离 advance_progress 和 upsert_weakness 调用
- 前端 gradeStatus 显示 memory_ok 状态
- profile 端点返回 cold_start 标记（无记录时显示提示）
- 复习清单按钮点击后自动填入提问框并检索

**修改文件**：
- `app/main.py`（grade 函数 + profile 端点）
- `web/index.html`（判分显示 + 弱点表格 + 复习清单）

**预期验证结果**：
```
第 1 次答错"伪共享"：
  correct: false
  memory_ok: true
  弱点表：伪共享 | 错 1 次 | 新学

第 2 次答对"伪共享"：
  correct: true
  memory_ok: true
  弱点表：伪共享 | 错 1 次 | 巩固

第 3-4 次答对"伪共享"：
  correct: true
  memory_ok: true
  弱点表：伪共享 | 错 1 次 | 掌握

第 5 次答错"伪共享"：
  correct: false
  memory_ok: true
  弱点表：伪共享 | 错 2 次 | 新学（重置）
```

---

### 第 8 轮：交付打包

**用户提示词**：
```
异常矩阵、测试、一键启动脚本、文档完善。

1. 产出 scripts/init_demo.sh：
   - 检查 seekdb 连接
   - 安装 Python 依赖
   - 初始化数据库（python scripts/init_db.py）
   - 导入语料（python -m app.ingest）
   - 启动服务（python -m uvicorn app.main:app --port 8080）

2. 产出 scripts/collect_usage_data.py：
   - --init：初始化使用数据文件
   - --log：记录一次使用（提问/出题/判分）
   - --feedback：收集用户反馈（5 分制）
   - --export：导出使用报告

3. 修复 Windows GBK 编码问题：
   - scripts/init_db.py 的 Unicode 字符替换为 ASCII
   - scripts/collect_usage_data.py 同理

4. 更新文档：
   - README.md：添加在线网站链接
   - QUICK_START.md：完整启动步骤
   - docs/02-运行说明与验证样例.md：验证用例

5. 创建证据目录：
   - evidence/qoder/：8 轮开发记录
   - evidence/DEMO_SCRIPT.md：60 秒演示脚本
   - evidence/SCREENSHOT_GUIDE.md：截图指南
   - evidence/FINAL_CHECKLIST.md：提交检查清单
```

**Qoder 回复要点**：
- init_demo.sh 用 bash 编写，每步检查上一步结果
- collect_usage_data.py 用 JSON 存储使用数据
- GBK 修复：✓ → [OK]，✗ → [ERROR]
- 证据文档包含每轮的目标、对话摘要、产出文件、验收标准

**生成文件**：
- `scripts/init_demo.sh`（约 80 行）
- `scripts/collect_usage_data.py`（约 150 行）
- `evidence/qoder/01-08-*.md`（8 份，每份约 100 行）
- `evidence/DEMO_SCRIPT.md`、`SCREENSHOT_GUIDE.md`、`FINAL_CHECKLIST.md`

**预期 init_demo.sh 运行输出**：
```
=== 温故一键启动 ===

[1/5] 检查 seekdb 连接...
  seekdb: ok host=127.0.0.1 port=2881

[2/5] 安装 Python 依赖...
  Requirement already satisfied: pymysql
  Requirement already satisfied: fastapi
  Requirement already satisfied: uvicorn

[3/5] 初始化数据库...
  连接 seekdb: 127.0.0.1:2881
  执行 DDL...
  写入初始数据...
  [OK] 数据库初始化完成

[4/5] 导入语料...
  语料 6 篇，向量方案 = dashscope（1024 维）
  入库完成：chunks=23  concept=40

[5/5] 启动服务...
  INFO:     Uvicorn running on http://127.0.0.1:8080

=== 启动完成 ===
打开浏览器访问：http://127.0.0.1:8080
```

---

## 总结

以上 8 轮开发，每轮有明确目标、验收标准和 commit。

**技术亮点**：
1. 一条 SQL 完成混合检索（向量 + 全文 + 标量，RRF 融合）
2. PowerContext 记忆闭环（新学 → 巩固 → 掌握状态机）
3. 语料质量管控（review_status 标记可疑内容）
4. 分工清晰（seekdb 记资料，PowerContext 记弱点）

**项目完成度**：
- 9 张表全部建好，23 块切片入库
- 40 个概念注册，87 条概念关联
- 5 个 API 端点全部可用
- PowerContext 记忆读写正常
- 在线网站已发布：https://wengu-study-coach-ao0rgkrp2dz.qoder.zone

**Qoder 在开发中的作用**：
- 需求拆解：分析语料，识别痛点和功能边界
- 编码实现：生成核心代码（retrieval.py, memory.py, main.py 等）
- 调试修复：遇到报错时分析原因并给出修复方案
- 文档生成：生成运行说明、验证样例、证据文档

**开发过程可追溯**：
- 每轮对话有截图（evidence/qoder/01-08-*.png）
- 每轮产出有 commit（git log 可查）
- commit 时间线与对话时间对应
