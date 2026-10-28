# Qoder 提示词脚本 · 8 轮开发

> 赛题：Qoder × OceanBase —— Build with Qoder
> 用途：把整个项目拆成 8 轮可直接粘贴的对话，每轮有明确验收标准、截图点、commit。
> 按顺序执行，**不要跳轮**。每轮结束必须 commit 一次，让 commit 时间线能和 Qoder 对话截图对上。

---

## 0. 怎么用这份脚本（三条纪律）

1. **一轮一 commit。** 每轮验收通过就提交，message 用本文档给的写法。评审核对「开发记录」时，看的就是对话时间 ↔ commit 时间能不能对上。
2. **报错不要自己偷偷修好。** 把完整报错粘回 Qoder，让它先分析原因再改。这个「报错 → 分析 → 修复」的往返，是评审判断"真用了 Qoder"最硬的证据。一次成功的对话反而可疑。
3. **每轮只要它做本轮的事。** 加一句"只改本轮涉及的文件"，能有效防止它顺手重构半个仓库、把上轮的验收搞崩。

---

## 1. 变量区（换项目只改这里）

| 变量 | 值 | 说明 |
|---|---|---|
| 项目代号 | `wengu` | 目录名 `qoder/wengu/` |
| 项目名 | 温故 | 站点标题 |
| 一句话 | 把一份讲义变成会记住你弱点的复习教练 | 网站首屏 |
| 领域 | 并行计算（MPI / OpenMP） | 换领域要改词表 |
| 数据 | `data/raw/` 6 篇 / 1.27 万字 / 23 节 | 见 `data/CORPUS.md` |
| 对话模型 | `deepseek-chat` | |
| Embedding | `text-embedding-v3`，**1024 维** | 维度写死，改了整个库要重建 |
| seekdb | Docker 服务端 `2881`，嵌入式 `pylibseekdb` 兜底 | |
| PowerContext | HTTP API `http://127.0.0.1:8000` | |

### 1.1 数据现状（第 1 轮开跑前已就绪）

`data/raw/` 是**项目原创编写的示例讲义**，6 篇 markdown，全部带 YAML front matter（`doc_id / title / doc_type / course / language / sections`）：

| 文件 | 主题 | 字数 | 小节 |
|---|---|---|---|
| `01-architecture.md` | 弗林分类、共享/分布式内存、伪共享、NUMA | 1717 | 4 |
| `02-performance.md` | 加速比、Amdahl、Gustafson、强/弱扩展 | 1615 | 4 |
| `03-mpi-basics.md` | 通信子、点对点匹配、死锁、非阻塞 | 2728 | 4 |
| `04-collectives.md` | 广播/散播/收集、归约、树形通信、误用 | 2129 | 4 |
| `05-openmp.md` | fork-join、数据作用域、竞争、调度 | 2789 | 4 |
| `06-design.md` | Foster 四步法、分解模式、计算强度 | 1696 | 3 |

合计 1.27 万字 / 23 节 / 约 29 块。**每个 `##` 小节就是天然的切片单元**，500 字上下，出处可以直接定位到「某文件第几节」。

语料来源与替换方式见 `data/CORPUS.md`；清单由 `scripts/build_manifest.py` 生成，该脚本同时做隐私自检（长数字串 / 邮箱 / 身份字段 / 本机路径）。

> 语料是示例规模，不是真实课程资料。真实使用时把任意 markdown 丢进 `data/raw/` 重跑 `build_manifest.py` 即可，代码不用改。

---

## 2. 通用前缀（每轮都粘这段在最前面）

```text
【项目】温故 —— 课程资料混合检索 + 薄弱点复习教练
【仓库】当前工作区。你的所有产物放在 qoder/wengu/ 下，不要动仓库里 qoder/ 之外的目录。
【技术约束】
- seekdb 是唯一数据存储：向量 + 全文 + 标量过滤，MySQL 协议，端口 2881，嵌入式模式作为兜底
- PowerContext 是唯一记忆存储：HTTP API，每个学习者一个 scope
- 对话用 deepseek-chat；embedding 用 text-embedding-v3（1024 维），维度从 .env 读
- 禁止引入第三种存储（不要 SQLite / Redis / 本地 JSON 当数据库）
- **禁止读取、导入或引用 `data/local/` 下的任何文件**（那是 gitignore 的私有目录，不得进入代码、数据库、日志、测试数据或截图）
- 密钥一律读 .env，代码里不许出现明文
【纪律】
- 只做本轮目标，不要顺手重构别的文件
- 每轮结束给我两样东西：改了哪些文件（逐条）+ 怎么验证（可直接执行的命令）
```

---

## 3. 八轮脚本

### 第 1 轮 · 勘察 + 需求拆解（只出文档，不写代码）

**目的**：产出一份能直接照着建表的方案文档，同时拿到最有说服力的一张"需求拆解"截图。
**耗时**：0.5 天　**信用点**：~5%

```text
【背景】
data/raw/ 下是 6 篇并行计算讲义（markdown，带 YAML front matter），合计约 1.27 万字、23 个 `##` 小节：体系结构、性能度量、MPI 点对点、MPI 集合通信、OpenMP、算法设计。data/manifest.json 是清单，data/CORPUS.md 记了来源。
先把这些文件逐篇读一遍，统计：主题覆盖、概念重叠（哪几篇在讲同一件事，比如「伪共享」在体系结构和 OpenMP 两篇都出现）、每个小节适合出什么类型的题、哪些概念之间存在前置依赖（学 A 之前得先懂 B）。

【目标】
只写文档，一行代码都不要写。产出 docs/01-需求与方案.md，必须包含 6 节：
1. 用户与场景 —— 谁、在什么时候、现在怎么做、痛在哪。要具体到「考前 3 天翻 12 份报告找某个实验的矩阵规模参数」这种颗粒度，不要写"提高效率"
2. 功能边界 —— 做哪 4 件事，明确列出不做什么，并说明为什么不做
3. 技术分工表 —— 三列表格：组件 / 存什么查什么 / 不做什么。seekdb 和 PowerContext 的分工必须互斥且互补
4. 数据模型 —— seekdb 建表语句草案（字段 + 类型 + 索引 + 向量维度）、PowerContext 的 scope 粒度与记忆条目 JSON 结构
5. 主流程时序 —— 导入 → 提问 → 出题 → 判分 → 写回弱点 → 下次会话，用文字箭头画出数据在哪一步流经哪个组件
6. 风险清单 —— 至少 5 条，每条给一个具体规避动作，不要"注意性能"这种空话

【约束】
- 表结构必须能支撑「向量 + 全文 + 标量过滤」在一条 SQL 里完成混合检索，写清用哪些列
- 记忆必须是显式写入（我们主动调 API 写），不依赖模型自动抽取
- 每个功能都要能对应到一张表或一个 API 端点，对不上的功能就砍掉

【验收】
- 我拿着第 4 节的数据模型能直接建表，不需要再问任何问题
- 第 3 节的表里没有"既存文档又存记忆"的模糊地带
```

**验收**：`docs/01-需求与方案.md` 存在，6 节齐全，数据模型有可执行 SQL。
**截图**：`evidence/qoder/01-需求拆解.png`（第一轮对话 + 文档生成结果同框最好）
**commit**：`docs(wengu): 需求与方案、数据模型、技术分工`

---

### 第 2 轮 · 连通性 spike（跑通即停，不写业务）

**目的**：先证明 seekdb 和 PowerContext 都能连上，把环境风险清零。这一步做不成，后面全是空转。
**耗时**：0.5 天　**信用点**：~8%

```text
【目标】
最小连通性验证，不要写任何业务逻辑。产出三样：
1. deploy/docker-compose.yml —— 只含 seekdb 一个服务：2881、2886 端口，数据卷挂 ./data/seekdb，镜像 oceanbase/seekdb:latest，带 healthcheck
2. scripts/smoke_test.py ——
   a) pymysql 连 seekdb，建 tmp_probe 表，插一行，查回来，打印 `seekdb: ok rows=1 (mode=docker)`
   b) requests 调 PowerContext：写一条记忆、按 id 读回来，打印 `powercontext: ok id=<memory_id>`
   c) 任何一步失败，打印失败原因（含实际用的 host/port）并以退出码 1 结束
   d) seekdb 连不上时自动降级试嵌入式 pylibseekdb，成功则打印 mode=embedded
3. .env.example —— SEEKDB_HOST/PORT/USER/PASSWORD、PC_BASE_URL/PC_TOKEN、LLM_API_KEY/LLM_BASE_URL、EMBED_API_KEY/EMBED_DIM=1024

【约束】
- 不建业务表、不写检索、不碰前端
- 先查 seekdb 和 PowerContext 的官方文档确认驱动和端点，不要猜 API 路径；不确定的地方在注释里标 TODO 并告诉我

【验收】
docker compose -f deploy/docker-compose.yml up -d
python scripts/smoke_test.py
→ 输出两行 ok，退出码 0
→ 故意填错 PC_BASE_URL 再跑一次，必须打印清晰错误而不是崩栈
```

**验收**：两行 `ok`；改错配置能看到人话错误。
**截图**：`evidence/qoder/02-连通性.png`（含 docker ps + smoke_test 输出）
**commit**：`feat(wengu): seekdb/powercontext 连通性与降级兜底`

> 这一步大概率会踩：镜像拉取慢、2881 被占、PowerContext 端点路径不对。**踩到就把报错原文贴回去**，这是第一段真实调试记录。

---

### 第 3 轮 · 数据管道（切片 + 向量化 + 入库）

**目的**：把资料变成可检索的库。这一轮的质量直接决定后面检索准不准。
**耗时**：1 天　**信用点**：~15%

```text
【目标】
产出 scripts/ingest.py + app/schema.py：
1. 读 data/raw/ 下全部 md：先解析 YAML front matter 取 doc_id/title/doc_type/course/language，再按 `##` 小节切片（每节 400–700 字，正好是目标粒度；超过 800 字的节在段落边界再切一刀，重叠 80 字）。每块保留元数据：doc_id、title、source_file、section（小节标题）、course、doc_type（讲义）、seq、char_len
2. 每块额外抽三个标量字段，供混合检索时做条件过滤：`topic`（如 mpi / openmp / performance）、`level`（入门 / 进阶）、`has_code`（是否含代码片段）
2. 批量调 embedding（batch=16，失败重试 3 次指数退避，记录失败块到 data/failed_chunks.jsonl 不中断整体）
3. 建表 chunks：id、course、doc_type、source_file、heading_path、page、content、emb VECTOR(1024)，并建全文索引和向量索引。全文索引按 seekdb 官方语法（WITH PARSER 那段以 docs.seekdb.ai 为准），建完必须能跑通一条 MATCH ... AGAINST 验证
4. 幂等：--rebuild 清表重建；默认按 source_file 的 mtime 做增量，跳过未变更文件
5. 结束打印一行统计：`docs=12 chunks=847 tokens=... dim=1024 rows=847`，同时写 data/ingest_report.json
6. 额外产出 data/chunks_preview.jsonl（前 20 条，content 截前 80 字），我要肉眼检查切片有没有把表格/公式切碎

【约束】
- 写表前校验 embedding 实际维度与表定义一致，不一致直接报错退出，不允许静默截断
- 只导入 data/raw/；`data/local/` 是私有目录，脚本里不许出现这个路径
- 中文全文检索要能正确分词，切完用「伪共享」这个词试一次，命中数 > 0 才算过

【验收】
python scripts/ingest.py --rebuild
→ 打印统计行；rows 与 chunks 数一致
python scripts/ingest.py
→ 第二次跑是增量的，chunks 数不变、耗时 < 10s
```

**验收**：`rows == chunks`；增量重跑不重复；中文全文能命中。
**截图**：`evidence/qoder/03-数据管道.png` + `evidence/data/ingest_report.json`
**commit**：`feat(wengu): 切片-向量化-入库管道，支持增量与维度校验`

---

### 第 4 轮 · 检索核心（先 CLI，不做界面）

**目的**：让混合检索真的跑起来，并且能证明"是数据库在干活"。这是技术结合最主要的得分点。
**耗时**：1 天　**信用点**：~15%

```text
【目标】
产出 app/retrieval.py + scripts/query.py：
1. hybrid_search(query, course=None, doc_type=None, k=5)：用一条 SQL 同时完成向量距离 + MATCH AGAINST 全文匹配 + 标量过滤，用 RRF 或加权融合在 SQL 里排序，返回 chunk 内容 + source_file + heading_path + 向量分 + 全文分 + 融合分
2. 命中为空时降级为纯向量检索，结果里标记 degraded=true，并打印"已降级"
3. scripts/query.py "问题" --course parallel-programming --k 5 → 打印对齐的表格：排名 / 融合分 / 出处 / 80 字摘要
4. 每次查询往 qa_log 表写一行：query、top_ids、latency_ms、degraded，用于事后统计
5. 把这条 SQL 的 EXPLAIN 结果写入 evidence/sql/hybrid_explain.txt

【约束】
- 融合必须在一条 SQL 里完成，不要把候选集拉回 Python 再排序 —— 选 seekdb 的理由就是这个
- SQL 文本和参数分离，防注入；query 做长度上限（比如 500 字）并说明理由
- 不要把 embedding 结果打印到日志（太长），只打维度

【验收】
python scripts/query.py "非阻塞通信会造成死锁吗" --k 3
→ 3 条结果，Top1 的 heading_path 落在教材第 3 章范围内，单次耗时 < 500ms
python scripts/query.py "量子退火" --k 3
→ 明确输出"未命中，已降级为空结果"，而不是硬编一段答案
```

**验收**：Top1 出处正确；无关问题能诚实返回空；EXPLAIN 能看出走了索引。
**截图**：`evidence/qoder/04-混合检索.png`（对话 + 表格输出 + EXPLAIN 三合一）
**commit**：`feat(wengu): 一条 SQL 的混合检索与出处溯源`

---

### 第 5 轮 · 记忆层（跨会话必须能证明）

**目的**：PowerContext 的得分点全在"跨会话"三个字上。这一轮的验收脚本要能排除"假记忆"（比如偷偷存了个本地 JSON）。
**耗时**：0.5 天　**信用点**：~10%

```text
【目标】
产出 app/memory.py + scripts/memory_demo.py：
1. scope 粒度 learner:<id>，一个学习者一个 scope
2. 记忆条目结构：{type: weakness|preference|progress, concept, evidence, count, status: 新学|巩固|掌握, last_seen}
3. 封装四个函数：get_profile(learner) / upsert_weakness(learner, concept, wrong_answer) / advance_progress(learner, concept) / get_review_plan(learner, days)
4. 写入走显式 API；写入前先读同 concept 去重，命中则 count+1 而不是新增一条
5. scripts/memory_demo.py 演示跨会话，必须是两个独立进程：
   进程 A：给 learner=demo 写 3 条弱点，打印写入的 id，退出
   进程 B：全新启动，读回并打印 `recalled 3 weaknesses: <concept>(x2) ...`，证明是从 PowerContext 读的

【约束】
- 不许把记忆缓存到本地文件或内存里冒充（我要的是真读 PowerContext）
- 网络失败要重试 + 幂等：同一条重复提交不产生两条记录
- PC 不可用时，接口要返回明确降级提示，不要假装记忆成功

【验收】
python scripts/memory_demo.py
→ 两次独立进程，第二步能读到第一步写的 3 条，count 正确
把 PC 服务停掉再跑 → 明确报"记忆服务不可用"，不是崩栈
```

**验收**：跨进程可读回；重复写入不翻倍；服务挂掉时诚实降级。
**截图**：`evidence/qoder/05-记忆跨会话.png` + `evidence/pc/recall.json`
**commit**：`feat(wengu): 基于 PowerContext 的弱点记忆与去重写入`

---

### 第 6 轮 · 应用层（能点开、能演示）

**目的**：从 CLI 变成评审能点的东西。前端不许上构建工具，评审机器上 `uvicorn` 一条命令就要能起。
**耗时**：1 天　**信用点**：~15%

```text
【目标】
产出 app/main.py（FastAPI）+ web/index.html（单页，纯 HTML+fetch，无 npm、无构建）：
1. POST /api/ask {learner, query} → 混合检索 + 带引用的回答，正文里用 [1][2] 标号对应返回的 chunks；资料里没有就直说"资料中未提及"，不许编
2. GET /api/profile/{learner} → 弱点列表、各概念状态、推荐复习顺序
3. POST /api/quiz {learner, concept?} → 出 3 道题（2 选择 + 1 简答），每题带依据 chunk 的出处
4. POST /api/grade {learner, answers} → 判分 + 讲解，错题写回弱点（这一轮先接 memory.py，策略第 7 轮再优化）
5. 前端三个区：提问 / 出题 / 我的弱点。提问区把引用做成可展开的卡片，显示 source_file + heading_path

【约束】
- 回答必须带出处，无出处的结论不许输出
- 统一错误结构 {code, message}，不要把 stack trace 返回给前端
- 冷启动一条命令：uvicorn app.main:app --port 8080，不许有额外初始化步骤

【验收】
起服务 → 浏览器提三个问题：一个能答、一个跨章节、一个资料里没有
→ 前两个带正确引用，第三个明确说不了解
```

**验收**：三问三答符合预期；引用可点开看到原文位置。
**截图**：`evidence/qoder/06-应用层.png` + 界面三张（提问/出题/弱点）
**commit**：`feat(wengu): FastAPI + 单页前端，带出处的问答与出题`

---

### 第 7 轮 · 复习闭环（产品差异化就在这）

**目的**：把 seekdb（找依据）和 PowerContext（记弱点）真正咬合起来——出什么题由记忆决定，题的依据由检索提供。这一轮做完，"技术结合"才不是各干各的。
**耗时**：1 天　**信用点**：~15%

```text
【目标】
1. 选题策略：从 weakness 里按 (count × 时间衰减) 排序，优先出「学过但反复错」的概念；新学习者没有弱点时，先让他选课程，从高频概念里出诊断题
2. 出题必须检索该 concept 的资料片段作为依据，题目要能溯源到 source_file + heading_path
3. 判分：选择题直接比对；简答题用 LLM 打分并给理由（要点覆盖度 / 是否有明显错误）
4. 判分后写回：错 → upsert_weakness(count+1, status 回退到"新学")；对 → advance_progress 前进一档
5. GET /api/today/{learner} → 今日复习清单：3 个概念 + 每个 1 道题 + 预计 15 分钟
6. 前端加"今日复习"入口，答完显示"这个概念你已经错 3 次了"这类反馈

【约束】
- 出题不许脱离资料自由发挥，每题必须能点开到依据段落
- 状态机只有三档，不要自己加档位

【验收】
对 learner=demo 连续答错同一概念 3 次 → profile 里该概念 count=3、status 回到"新学"
换 learner=newbie → 不出题，先要求选课程
连续答对同一概念 3 次 → status 到"掌握"，从今日清单里消失
```

**验收**：错误累积、状态回退、掌握后移出清单，三条都成立。
**截图**：`evidence/qoder/07-复习闭环.png` + 前后 profile 对比图
**commit**：`feat(wengu): 弱点驱动的出题-判分-写回闭环`

---

### 第 8 轮 · 调试加固 + 交付打包

**目的**：把"能跑"变成"评审能复现"，同时补上最后一批调试证据。
**耗时**：1 天　**信用点**：~12%

```text
【目标】
1. 异常矩阵：空 query、超长 query（5000 字）、embedding 超时、seekdb 断开、PC 401、判分返回非法 JSON —— 六种情况逐个给出明确返回，不许 500 裸奔
2. pytest 至少 12 条，覆盖四块：切片（边界/重叠/元数据）、检索（命中/空/降级）、记忆（去重/跨会话/服务不可用）、判分（对/错/无法解析）
3. docker-compose.yml 一键起 seekdb；scripts/init_demo.sh 一条命令完成建表 + 导入样例 + 起服务
4. README.md 写成「从零到跑通」8 步，每步一条可复制命令 + 预期输出；另附常见问题 5 条
5. docs/02-验证样例.md：V1 冷启动 / V2 检索准确性 / V3 跨会话记忆 / V4 混合检索+过滤，每条含初始数据、输入、步骤、预期结果、证据文件路径
6. evidence/INDEX.md 索引所有证据文件，标明每个文件对应哪条验收
7. 生成站点素材清单：6 张功能截图的位置与说明、60 秒演示脚本大纲（分镜 + 旁白）

【约束】
- README 的每条命令我都要能直接复制执行，不许出现"按实际情况修改"
- secrets 全部走 .env.example 占位
- 不许为了让测试变绿而降低断言强度

【验收】
rm -rf data/seekdb && bash scripts/init_demo.sh   # 从零
pytest -q                                          # 全绿
→ 再用验证样例 V1-V4 各跑一遍，结果与文档一致
```

**验收**：干净环境一条命令起、`pytest` 全绿、V1-V4 与文档一致。
**截图**：`evidence/qoder/08-交付打包.png`
**commit**：`chore(wengu): 异常矩阵、测试、一键启动与验证样例`

---

## 4. 截图 / commit 对照表

| 轮次 | 截图文件 | commit message |
|---|---|---|
| 1 | `01-需求拆解.png` | `docs(wengu): 需求与方案、数据模型、技术分工` |
| 2 | `02-连通性.png` | `feat(wengu): seekdb/powercontext 连通性与降级兜底` |
| 3 | `03-数据管道.png` | `feat(wengu): 切片-向量化-入库管道，支持增量与维度校验` |
| 4 | `04-混合检索.png` | `feat(wengu): 一条 SQL 的混合检索与出处溯源` |
| 5 | `05-记忆跨会话.png` | `feat(wengu): 基于 PowerContext 的弱点记忆与去重写入` |
| 6 | `06-应用层.png` | `feat(wengu): FastAPI + 单页前端，带出处的问答与出题` |
| 7 | `07-复习闭环.png` | `feat(wengu): 弱点驱动的出题-判分-写回闭环` |
| 8 | `08-交付打包.png` | `chore(wengu): 异常矩阵、测试、一键启动与验证样例` |

---

## 5. 信用点预算

| 轮次 | 占比 | 说明 |
|---|---|---|
| 1 需求 | 5% | 只让它写字，便宜 |
| 2 连通 | 8% | 环境问题来回多，留够 |
| 3 管道 | 15% | 切片规则会反复调，最费 |
| 4 检索 | 15% | SQL 融合逻辑要迭代 |
| 5 记忆 | 10% | 结构定了就快 |
| 6 应用 | 15% | 前后端一起改，注意别让它整文件重写 |
| 7 闭环 | 15% | 策略调参最费 |
| 8 交付 | 12% | |
| 余量 | 5% | 答辩前救火 |

省点数的三个习惯：① 每轮开头贴通用前缀，别让它重新理解项目；② 改局部用"只改这个函数"而不是"重写这个文件"；③ 报错先让它**分析**再让它**改**，分两步比一步到位便宜。

---

## 6. 反模式（这样问会浪费轮次）

| 别这样问 | 为什么 | 改成 |
|---|---|---|
| "帮我做一个复习系统" | 没有边界，它会给你一个玩具 | 用第 1 轮的六节结构逼它收敛 |
| "整个项目重写一遍" | 上轮验收全崩，截图对不上 commit | "只改 `hybrid_search` 的排序部分" |
| "报错了，修一下" | 没有报错原文，它在猜 | 贴完整 traceback + 复现命令 + 你已排查的两点 |
| "顺便把界面也美化一下" | 一轮混两件事，验收标准失效 | 单开一轮 |
| 让它自己决定表结构 | 后面三次迁移都是它的锅 | 第 1 轮就把 DDL 钉死 |

---

## 7. 大概率会真遇到的报错（遇到别慌，贴回去）

| 现象 | 常见原因 | 该让它先查什么 |
|---|---|---|
| `ERROR 1210: Incorrect arguments` 建向量表失败 | 维度写错或向量列类型不对 | 表定义 vs `.env` 的 EMBED_DIM |
| 全文检索查不到中文 | 分词器没装 / 索引没带 parser | `SHOW CREATE TABLE` 看索引定义 |
| `MATCH ... AGAINST` 语法报错 | seekdb 版本语法差异 | 官方文档对应版本章节 |
| embedding 返回 1024 但表是 1536 | 换过模型没重建表 | 报错信息里的维度 + 建表语句 |
| PowerContext 401 | token 没带或过期 | 请求头 + 服务端日志 |
| 两次跑 ingest 数据翻倍 | 幂等没做对 | 主键/唯一键 + mtime 判断逻辑 |
| 检索 Top1 出处不对 | 切片把章节标题切丢了 | `chunks_preview.jsonl` 里那条的 heading_path |

---

## 8. 与提交材料的对应关系

| 提交材料 | 由哪几轮产出 |
|---|---|
| 运行说明 | 第 8 轮 README + `init_demo.sh` |
| 验证样例 | 第 8 轮 `docs/02-验证样例.md`，素材来自 3/4/5/7 轮 |
| Qoder 开发记录 | 8 轮截图 + 8 个 commit + Qoder UID |
| 技术结合证据 | 第 4 轮 EXPLAIN、第 5 轮 recall.json、第 7 轮 profile 前后对比 |
| 项目网站 | 第 6/7 轮截图 + 第 8 轮素材清单，在 Qoder Sites 发布 |
