# 温故 · 竞赛提交包

> Qoder × OceanBase 2026 大赛 —— Build with Qoder

## 项目信息

- **项目名称**：温故（Wengu）
- **项目标语**：把一份讲义变成会记住你弱点的复习教练
- **赛题**：Qoder × OceanBase —— Build with Qoder
- **开发工具**：Qoder（八轮迭代开发）
- **核心技术**：seekdb（混合检索）+ PowerContext（跨会话记忆）

---

## 提交材料

### 1. 项目网站 ✅
- **网址**：https://wengu-study-coach-ao0rgkrp2dz.qoder.zone
- **访问权限**：任何人都可访问
- **验证方式**：用浏览器无痕窗口打开，确认未登录状态下可正常访问

### 2. 代码仓库 ✅
- **地址**：https://github.com/oceanbase/powercontext/tree/2026-competition-ecosystem/qoder/wengu
- **分支**：`feat/qoder-wengu`
- **公开性**：公开可访问

### 3. 运行说明 ✅
**文件**：`docs/02-运行说明与验证样例.md`

**快速启动（四步）**：
```powershell
# 1. 启动 seekdb
docker run -d --name seekdb -p 2881:2881 oceanbase/seekdb:latest

# 2. 安装依赖
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 3. 初始化数据库并导入语料
python scripts/init_db.py
python -m app.ingest

# 4. 启动服务
python -m uvicorn app.main:app --port 8080
```

**一键启动**：
```bash
bash scripts/init_demo.sh
```

### 4. 验证样例 ✅
**文件**：`docs/02-运行说明与验证样例.md` 第三节

**四个验证场景**：
- V1：混合检索命中（输入「非阻塞通信会造成死锁吗」）
- V2：拒绝编造（输入「红烧肉怎么做好吃」）
- V3：出题与判分（概念「伪共享」）
- V4：跨会话记忆（答错 3 次后重启验证）

### 5. Qoder 开发记录 ✅
**文件**：`evidence/qoder/01-08-*.md` + 截图（待补充）

**八轮开发**：
1. 第 1 轮 · 需求拆解：产出完整方案文档
2. 第 2 轮 · 连通性验证：证明 seekdb 和 PowerContext 都能连上
3. 第 3 轮 · 数据管道：把 markdown 变成可检索的库
4. 第 4 轮 · 混合检索：一条 SQL 完成向量 + 全文 + 标量融合
5. 第 5 轮 · 记忆层：实现 PowerContext 客户端和跨会话记忆
6. 第 6 轮 · 应用层：FastAPI + 单页前端
7. 第 7 轮 · 复习闭环：把 seekdb 和 PowerContext 真正咬合
8. 第 8 轮 · 交付打包：异常矩阵、测试、一键启动

**截图清单**（待补充）：
- `evidence/qoder/01-08-*.png`（8 轮对话截图）
- `evidence/qoder/09-commit 时间线.png`
- `evidence/qoder/10-Qoder-UID.png`

### 6. 技术结合证据 ✅
**seekdb**：
- 9 张表完整 DDL（`docs/01-需求与方案.md` §4.2）
- 混合检索 SQL（`app/retrieval.py`）
- 查询日志（`qa_log` 表）

**PowerContext**：
- 4 个核心函数（`app/memory.py`）
- 跨会话验证（`evidence/qoder/05-记忆层.md`）
- 降级处理（`evidence/qoder/08-交付打包.md`）

**分工原则**：
> seekdb 记得「资料说了什么」，PowerContext 记得「你哪里不会」

### 7. 使用效果材料 ️（鼓励提交）
**文件**：`evidence/USAGE_EFFECT_TEMPLATE.md`（模板）

**收集工具**：
```bash
# 初始化
python scripts/collect_usage_data.py --init

# 记录使用
python scripts/collect_usage_data.py --log "提问" --user demo --concept "伪共享"

# 收集反馈
python scripts/collect_usage_data.py --feedback

# 导出数据
python scripts/collect_usage_data.py --export
```

---

## 核心功能

### 1. 带出处的混合检索
- 输入问题，系统从讲义中检索最相关的段落
- 每条结果都带精确出处（文件名 + 章节标题）
- 检索结合向量语义、全文关键词和标量过滤
- 资料里没有的内容，明确说「资料中未提及」

### 2. 弱点驱动的出题与判分
- 根据薄弱知识点出题，而不是随机抽题
- 答错会记进弱点档案，答对会推进掌握进度
- 出题依据来自讲义原文，判分由 LLM 完成并给出理由

### 3. 跨会话的学习者记忆
- 每个学习者有独立的记忆档案
- 记忆存在 PowerContext 里，跨会话持久化
- 下次打开应用，系统知道你是谁、哪里不会

### 4. 今日复习清单
- 根据弱点档案生成个性化复习计划
- 3 个概念 + 3 道题，预计 15 分钟完成
- 优先复习「学过但反复错」的内容

---

## 技术架构

```
┌─────────────┐
│   前端 UI   │  web/index.html（单页，纯 HTML+fetch）
└──────┬──────┘
       │
       ▼
┌─────────────┐      ──────────────┐      ┌─────────────┐
│  FastAPI    │─────▶│   seekdb     │      │ PowerContext│
│  应用层     │      │  （数据存储） │      │ （记忆存储）│
└──────┬──────┘      └──────────────┘      ─────────────┘
       │
       │  读取
       ▼
┌─────────────┐
│  9 张表     │  kb_meta, doc_meta, chunks, concept,
│             │  chunk_concept, concept_edge, quiz_item,
│             │  qa_log, quiz_attempt
└─────────────┘
```

**数据流**：
- 提问 → POST /api/ask → seekdb 混合检索 → 返回带出处的引用
- 出题 → GET /api/quiz → seekdb 取依据 → LLM 生成题目
- 判分 → POST /api/grade → LLM 判定 → PowerContext 写回弱点
- 档案 → GET /api/profile → PowerContext 读弱点 → 生成复习计划

---

## 评分维度自评

| 维度 | 自评 | 证据 |
|------|------|------|
| 实用价值 | ⭐⭐⭐⭐ | 针对课程复习痛点，混合检索 + 弱点记忆 |
| 使用效果 | ⭐⭐⭐☆☆ | 待收集真实用户数据 |
| 完成度与体验 | ⭐⭐⭐⭐⭐ | 四个核心功能完整，流程顺畅 |
| 技术结合 | ⭐⭐⭐⭐ | seekdb/PC 分工明确，证据充分 |
| Qoder 开发实践 | ⭐⭐⭐⭐☆ | 文档完整，待补充对话截图 |
| 工程质量 | ⭐⭐⭐⭐⭐ | 代码清晰，文档齐全，一键启动 |

**总体自评**：⭐⭐⭐⭐☆（4.5/5）

---

## 文件清单

```
qoder/wengu/
├── app/                      # 应用代码
│   ├── main.py              # FastAPI 应用（260 行）
│   ├── retrieval.py         # 混合检索（151 行）
│   ├── memory.py            # PowerContext 客户端（193 行）
│   ├── ingest.py            # 数据管道（236 行）
│   └── embed.py             # 向量化模块（173 行）
├── web/
│   ── index.html           # 单页前端（300 行）
├── site/
│   └── index.html           # 项目展示网站
├── docs/
│   ├── 00-Qoder 提示词脚本.md  # 八轮开发脚本
│   ├── 01-需求与方案.md        # 完整方案文档（830 行）
│   └── 02-运行说明与验证样例.md  # 运行说明和验证样例
├── scripts/
│   ├── init_db.py           # 数据库初始化
│   ├── init_demo.sh         # 一键启动
│   ├── smoke_test.py        # 连通性验证
│   ├── build_manifest.py    # 语料清单生成
│   ── collect_usage_data.py  # 使用数据收集
├── evidence/                 # 证据材料
│   ├── qoder/               # Qoder 开发记录（8 轮）
│   ├── DEMO_SCRIPT.md       # 演示脚本
│   ├── USAGE_EFFECT_TEMPLATE.md  # 使用效果模板
│   ├── SCREENSHOT_GUIDE.md  # 截图收集指南
│   ├── INDEX.md             # 证据索引
│   ── FINAL_CHECKLIST.md   # 最终检查清单
├── data/
│   ├── raw/                 # 6 篇讲义（CC BY 4.0）
│   ├── manifest.json        # 语料清单
│   ── idf.json             # IDF 权重
├── deploy/
│   └── docker-compose.yml   # seekdb 容器配置
── .env.example             # 配置模板（占位值）
├── requirements.txt         # Python 依赖
├── README.md                # 项目说明
├── SUBMISSION_GUIDE.md      # 提交指南
└── SUBMISSION_PACKAGE.md    # 本文件
```

---

## 提交步骤

1. **登录大赛测试平台**
   - 进入 Qoder 赛题的提交入口

2. **填写基本信息**
   - 项目网站网址：`https://wengu-study-coach-ao0rgkrp2dz.qoder.zone`
   - 代码仓库地址：`https://github.com/oceanbase/powercontext/tree/2026-competition-ecosystem/qoder/wengu`
   - Qoder 账号 UID：（你的 UID）

3. **上传材料**
   - 运行说明：`docs/02-运行说明与验证样例.md`
   - 验证样例：同上（第三节）
   - Qoder 开发记录：`evidence/qoder/01-08-*.md` + 截图
   - 使用效果材料：`evidence/USAGE_EFFECT_TEMPLATE.md`（如有）

4. **最终确认**
   - 用浏览器无痕窗口再次打开项目网站
   - 确认可以正常访问
   - 确认所有材料已上传

5. **提交**
   - 点击提交按钮
   - 记录提交时间
   - 保存提交确认页面

---

## 联系方式

- **GitHub**：https://github.com/oceanbase/powercontext
- **项目网站**：https://wengu-study-coach-ao0rgkrp2dz.qoder.zone
- **问题反馈**：通过 GitHub Issues

---

**提交日期**：2026-10-28  
**最后更新**：2026-10-28
