# 温故 · 证据索引

> 所有证据文件的交叉引用，便于评审核对

## 一、Qoder 开发记录

| 轮次 | 文件 | 对应验收 | commit |
|------|------|---------|--------|
| 第 1 轮 · 需求拆解 | [`evidence/qoder/01-需求拆解.md`](evidence/qoder/01-需求拆解.md) | 需求文档、数据模型 | `docs(wengu): 需求与方案、数据模型、技术分工` |
| 第 2 轮 · 连通性验证 | [`evidence/qoder/02-连通性验证.md`](evidence/qoder/02-连通性验证.md) | seekdb/PC 连通 | `feat(wengu): seekdb/powercontext 连通性与降级兜底` |
| 第 3 轮 · 数据管道 | [`evidence/qoder/03-数据管道.md`](evidence/qoder/03-数据管道.md) | 入库统计、切片质量 | `feat(wengu): 切片 - 向量化 - 入库管道，支持增量与维度校验` |
| 第 4 轮 · 混合检索 | [`evidence/qoder/04-混合检索.md`](evidence/qoder/04-混合检索.md) | 检索准确性、EXPLAIN | `feat(wengu): 一条 SQL 的混合检索与出处溯源` |
| 第 5 轮 · 记忆层 | [`evidence/qoder/05-记忆层.md`](evidence/qoder/05-记忆层.md) | 跨会话记忆、降级 | `feat(wengu): 基于 PowerContext 的弱点记忆与去重写入` |
| 第 6 轮 · 应用层 | [`evidence/qoder/06-应用层.md`](evidence/qoder/06-应用层.md) | Web UI、三问三答 | `feat(wengu): FastAPI + 单页前端，带出处的问答与出题` |
| 第 7 轮 · 复习闭环 | [`evidence/qoder/07-复习闭环.md`](evidence/qoder/07-复习闭环.md) | 状态机、写回逻辑 | `feat(wengu): 弱点驱动的出题 - 判分 - 写回闭环` |
| 第 8 轮 · 交付打包 | [`evidence/qoder/08-交付打包.md`](evidence/qoder/08-交付打包.md) | 一键启动、异常矩阵 | `chore(wengu): 异常矩阵、测试、一键启动与验证样例` |

**截图建议**：每轮对应一个截图文件 `evidence/qoder/01-08-*.png`

---

## 二、技术结合证据

### seekdb 证据

| 证据类型 | 文件位置 | 说明 |
|---------|---------|------|
| 建表 SQL | [`docs/01-需求与方案.md`](docs/01-需求与方案.md) §4.2 | 9 张表完整 DDL |
| 混合检索 SQL | [`app/retrieval.py`](app/retrieval.py) | 80 行核心 SQL |
| EXPLAIN 结果 | 待补充 | `evidence/sql/hybrid_explain.txt` |
| 查询日志 | `qa_log` 表 | 每次查询写入一行 |
| 入库统计 | [`evidence/qoder/03-数据管道.md`](evidence/qoder/03-数据管道.md) | chunks=23, concept=40 |

### PowerContext 证据

| 证据类型 | 文件位置 | 说明 |
|---------|---------|------|
| API 端点 | [`app/memory.py`](app/memory.py) | 4 个核心函数 |
| 跨会话验证 | [`evidence/qoder/05-记忆层.md`](evidence/qoder/05-记忆层.md) | 进程 A 写→进程 B 读 |
| 降级处理 | [`evidence/qoder/08-交付打包.md`](evidence/qoder/08-交付打包.md) | PC 不可用时返回 unavailable |
| 记忆闭环 | [`evidence/qoder/07-复习闭环.md`](evidence/qoder/07-复习闭环.md) | 答错→写入→下次出题 |

### 分工原则

> **seekdb 记得「资料说了什么」，PowerContext 记得「你哪里不会」**

详见 [`docs/01-需求与方案.md`](docs/01-需求与方案.md) 第 3 节

---

## 三、验证样例证据

| 样例 | 输入 | 预期结果 | 实测结果 | 证据文件 |
|------|------|---------|---------|---------|
| V1 · 混合检索命中 | 「非阻塞通信会造成死锁吗」 | Top1 出处：《MPI 点对点通信》>> 死锁的四种典型成因 | ✅ 通过 | [`docs/02-运行说明与验证样例.md`](docs/02-运行说明与验证样例.md) |
| V2 · 拒绝编造 | 「红烧肉怎么做好吃」 | 资料中未提及，0 条引用 | ✅ 通过 | 同上 |
| V3 · 出题与判分 | 概念「伪共享」 | 生成简答题，判分有理由 | ✅ 通过 | 同上 |
| V4 · 跨会话记忆 | 答错 3 次后重启 | profile 里 count=3, status=新学 | ✅ 通过 | 同上 |

---

## 四、运行说明证据

| 步骤 | 命令 | 预期输出 | 证据文件 |
|------|------|---------|---------|
| 1. 启动 seekdb | `docker run -d --name seekdb -p 2881:2881 oceanbase/seekdb:latest` | 容器运行 | [`docs/02-运行说明与验证样例.md`](docs/02-运行说明与验证样例.md) |
| 2. 安装依赖 | `pip install -r requirements.txt` | 安装成功 | 同上 |
| 3. 初始化数据库 | `python scripts/init_db.py` | 数据库初始化完成 | [`evidence/qoder/08-交付打包.md`](evidence/qoder/08-交付打包.md) |
| 4. 导入语料 | `python -m app.ingest` | chunks=23, concept=40 | [`evidence/qoder/03-数据管道.md`](evidence/qoder/03-数据管道.md) |
| 5. 启动服务 | `python -m uvicorn app.main:app --port 8080` | 服务启动 | [`evidence/qoder/06-应用层.md`](evidence/qoder/06-应用层.md) |

**一键脚本**：[`scripts/init_demo.sh`](scripts/init_demo.sh)

---

## 五、项目网站证据

| 项目 | 内容 | 状态 |
|------|------|------|
| 网站地址 | https://wengu-study-coach-ao0rgkrp2dz.qoder.zone | ✅ 已发布 |
| 访问权限 | 任何人都可访问 | ✅ 已设置 |
| 页面内容 | 项目简介、功能、技术栈、运行说明、验证样例 | ✅ 完整 |

---

## 六、代码仓库证据

| 项目 | 内容 | 状态 |
|------|------|------|
| 仓库地址 | https://github.com/oceanbase/powercontext/tree/2026-competition-ecosystem/qoder/wengu | ✅ 公开 |
| 分支 | `feat/qoder-wengu` | ✅ 已推送 |
| Commit 数 | 7 个 | ✅ 完整 |
| 配置文件 | `.env.example` 使用占位值 | ✅ 无密钥 |

---

## 七、待补充材料

### 必须补充
- [ ] **Qoder 对话截图**：8 轮开发的实际对话截图（`evidence/qoder/01-08-*.png`）
- [ ] **Qoder UID**：用于核对站点归属（`evidence/qoder/10-Qoder-UID.png`）
- [ ] **commit 时间线截图**：`git log --oneline --graph` 输出

### 建议补充
- [ ] **使用效果数据**：邀请同学试用的使用数据和反馈（[`evidence/USAGE_EFFECT_TEMPLATE.md`](evidence/USAGE_EFFECT_TEMPLATE.md)）
- [ ] **演示视频**：60 秒核心功能演示（`evidence/demo.mp4`）
- [ ] **界面截图**：8 张核心功能截图（`evidence/screenshots/01-08-*.png`）

---

## 八、提交材料对照表

| 提交材料 | 要求 | 文件位置 | 状态 |
|---------|------|---------|------|
| 项目网站网址 | Qoder Sites 发布，任何人都可访问 | https://wengu-study-coach-ao0rgkrp2dz.qoder.zone | ✅ |
| 代码仓库 | 完整项目源码，公开或向评审开放 | https://github.com/oceanbase/powercontext/tree/2026-competition-ecosystem/qoder/wengu | ✅ |
| 运行说明 | 运行环境、依赖版本、部署与接入方式、完整步骤 | [`docs/02-运行说明与验证样例.md`](docs/02-运行说明与验证样例.md) | ✅ |
| 验证样例 | 至少一组可按步骤执行的样例 | [`docs/02-运行说明与验证样例.md`](docs/02-运行说明与验证样例.md) 第三节 | ✅ |
| Qoder 开发记录 | 关键开发环节的对话截图或录屏，附 Qoder UID | [`evidence/qoder/01-08-*.md`](evidence/qoder/) + 待补充截图 | ️ 待补充截图 |
| 使用效果材料（鼓励） | 使用人数、次数、提效对比、用户反馈 | [`evidence/USAGE_EFFECT_TEMPLATE.md`](evidence/USAGE_EFFECT_TEMPLATE.md) | ⚠️ 待收集 |

---

## 九、评分维度对照

| 维度 | 权重 | 关注内容 | 证据位置 | 状态 |
|------|------|---------|---------|------|
| 实用价值 | - | 针对真实痛点，解决方式有效 | [`docs/01-需求与方案.md`](docs/01-需求与方案.md) §1 | ✅ |
| 使用效果 | - | 真实用户，提效对比，可核对数据 | [`evidence/USAGE_EFFECT_TEMPLATE.md`](evidence/USAGE_EFFECT_TEMPLATE.md) | ⚠️ 待收集 |
| 完成度与体验 | - | 流程完整顺畅，功能实现 | [`docs/02-运行说明与验证样例.md`](docs/02-运行说明与验证样例.md) | ✅ |
| 技术结合 | - | seekdb/PC 实际发挥作用 | [`docs/01-需求与方案.md`](docs/01-需求与方案.md) §3 | ✅ |
| Qoder 开发实践 | - | 开发记录展示 Qoder 作用 | [`evidence/qoder/01-08-*.md`](evidence/qoder/) | ⚠️ 待补充截图 |
| 工程质量 | - | 代码清晰，依赖齐全，可复现 | [`scripts/init_demo.sh`](scripts/init_demo.sh) | ✅ |
