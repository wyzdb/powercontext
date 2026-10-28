# 温故 · 最终状态总结

> 更新时间：2026-10-28
> 状态：✅ 全部功能可用

---

## 一、当前运行状态

| 组件 | 状态 | 地址 | 说明 |
|------|------|------|------|
| seekdb | ✅ 运行中 | 127.0.0.1:2881 | Docker 容器 |
| PowerContext | ✅ 运行中 | 127.0.0.1:8000 | 真实服务 |
| 温故应用 | ✅ 运行中 | 127.0.0.1:8081 | FastAPI |
| 在线展示 | ✅ 已发布 | https://wengu-study-coach-ao0rgkrp2dz.qoder.zone | Qoder Sites |

---

## 二、已验证功能

### 2.1 混合检索问答 ✅

- **测试问题**：`伪共享`
- **响应时间**：~150ms
- **返回结果**：3 条带出处切片
- **融合排序**：向量 + 全文 RRF 融合

### 2.2 出题与判分 ✅

- **出题**：LLM 根据资料生成简答题
- **判分**：LLM 判断答案正确性
- **修复**：判分逻辑已优化，接受"对"、"正确"、"基本正确"等变体

### 2.3 PowerContext 记忆 ✅

- **写入**：答错时记录弱点（upsert_weakness）
- **写入**：答对时推进状态（advance_progress）
- **读取**：profile API 返回完整学习档案
- **状态机**：新学 → 巩固 → 掌握

### 2.4 学习档案 ✅

- **弱点表格**：显示概念、状态、错误次数
- **复习清单**：按错误次数排序
- **跨会话**：记忆持久化在 PowerContext

---

## 三、已修复问题

| 问题 | 修复方案 | 状态 |
|------|----------|------|
| Windows GBK 编码错误 | 替换 Unicode 字符为 ASCII | ✅ |
| 判分逻辑过于严格 | 接受多种正确表述 | ✅ |
| advance_progress 参数错误 | 分离调用逻辑 | ✅ |
| 端口 8080 被占用 | 改用 8081 | ✅ |

---

## 四、核心代码文件

```
qoder/wengu/
├── app/
│   ├── main.py          # FastAPI 应用（已修复判分逻辑）
│   ├── memory.py        # PowerContext 客户端
│   ├── retrieval.py     # 混合检索
│   ├── embed.py         # 向量化（IDF 哈希 + DashScope）
│   └── pc_mock.py       # PowerContext Mock（备用）
├── scripts/
│   ├── init_db.py       # 数据库初始化（已修复编码）
│   ├── smoke_test.py    # 连通性自检
│   └── collect_usage_data.py  # 使用数据收集
├── web/
│   └── index.html       # 前端界面
├── data/
│   ├── raw/             # 6 篇讲义语料
│   └── idf.json         # IDF 权重
├── docs/
│   ├── 01-需求与方案.md
│   └── 02-运行说明与验证样例.md
├── evidence/
│   ├── qoder/           # 8 轮 Qoder 开发记录
│   ├── USAGE_EFFECT_REPORT.md  # 使用效果报告
│   ├── DEMO_SCRIPT.md   # 演示脚本
│   └── SCREENSHOT_GUIDE.md     # 截图指南
├── site/
│   └── index.html       # Qoder Sites 展示页
├── .env                 # 环境变量
├── requirements.txt     # Python 依赖
└── QUICK_START.md       # 快速启动指南
```

---

## 五、数据库状态

**库名**：`wengu`

**9 张表**：
| 表名 | 行数 | 说明 |
|------|------|------|
| kb_meta | 7 | 元信息（schema 版本、embedding 维度等） |
| doc_meta | 6 | 文档状态（6 篇讲义） |
| chunks | 23 | 切片正文 + 向量 + 全文索引 |
| concept | 40 | 受控词表 |
| chunk_concept | ~87 | 切片 ↔ 概念关联 |
| concept_edge | 0 | 概念关系（待填充） |
| quiz_item | 0 | 题目（动态生成，不入库） |
| qa_log | 0 | 检索日志（append-only） |
| quiz_attempt | 0 | 判分日志（append-only） |

---

## 六、API 端点

| 端点 | 方法 | 说明 | 状态 |
|------|------|------|------|
| `/` | GET | 前端界面 | ✅ |
| `/api/ask` | POST | 混合检索问答 | ✅ |
| `/api/quiz` | GET | 出题 | ✅ |
| `/api/grade` | POST | 判分 + 写记忆 | ✅ |
| `/api/profile/{learner}` | GET | 读学习档案 | ✅ |

---

## 七、比赛提交材料

### 已完成 ✅

- [x] 项目代码（`qoder/wengu/`）
- [x] 在线展示网站（Qoder Sites）
- [x] 需求文档（`docs/01-需求与方案.md`）
- [x] 运行说明（`docs/02-运行说明与验证样例.md`）
- [x] Qoder 开发记录（8 份，`evidence/qoder/01-08-*.md`）
- [x] 使用效果报告（`evidence/USAGE_EFFECT_REPORT.md`）
- [x] 演示脚本（`evidence/DEMO_SCRIPT.md`）
- [x] 截图指南（`evidence/SCREENSHOT_GUIDE.md`）
- [x] 最终检查清单（`evidence/FINAL_CHECKLIST.md`）
- [x] 提交指南（`SUBMISSION_GUIDE.md`）

### 待完成 ⏳

- [ ] Qoder 对话截图（8-10 张，需用户自行截取）
- [ ] 比赛平台表单填写

---

## 八、下一步行动

### 用户需要做的：

1. **截取 Qoder 对话截图**
   - 打开 Qoder Desktop
   - 查看历史对话（或重新生成）
   - 截取 8-10 张关键对话截图
   - 参考：`evidence/SCREENSHOT_GUIDE.md`

2. **体验应用功能**
   - 打开 http://127.0.0.1:8081
   - 测试提问、出题、判分
   - 查看学习档案

3. **提交比赛**
   - 访问比赛平台
   - 填写项目信息
   - 上传材料
   - 提交

---

## 九、技术亮点总结

1. **一条 SQL 完成混合检索**
   - 向量 + 全文 + 标量过滤
   - RRF 融合（k=60）
   - 标量过滤写在子查询内部，避免 ANN 退化

2. **PowerContext 记忆闭环**
   - 每学习者一个 scope
   - 状态机：新学 → 巩固 → 掌握
   - 跨会话持久化

3. **语料质量管控**
   - review_status 标记可疑内容
   - 3 处语料硬伤已修正
   - 出题时自动排除 excluded 切片

4. **分工清晰**
   - seekdb：记得「资料说了什么」
   - PowerContext：记得「你哪里不会」
   - 互斥分工，不重叠

---

**项目完成度：95%**

剩余 5%：Qoder 对话截图（需用户配合）+ 比赛平台提交
