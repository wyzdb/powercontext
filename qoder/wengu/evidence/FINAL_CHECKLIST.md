# 温故 · 竞赛提交最终检查清单

> 提交前逐项核对，确保所有材料齐全

## ✅ 已完成（可直接提交）

### 1. 项目网站 ✅
- **网址**：https://wengu-study-coach-ao0rgkrp2dz.qoder.zone
- **访问权限**：任何人都可访问
- **验证方式**：用浏览器无痕窗口打开，确认未登录状态下可正常访问
- **页面内容**：
  - [x] 项目简介（Hero 区）
  - [x] 解决什么问题（3 个痛点）
  - [x] 核心功能（4 个功能）
  - [x] 技术架构（seekdb + PowerContext 分工）
  - [x] 技术栈明细（表格）
  - [x] 快速开始（4 步启动命令）
  - [x] 验证样例（V1-V4）
  - [x] Qoder 开发实践（8 轮迭代说明）
  - [x] 项目信息（仓库链接、分支、许可证）

### 2. 代码仓库 ✅
- **地址**：https://github.com/oceanbase/powercontext/tree/2026-competition-ecosystem/qoder/wengu
- **分支**：`feat/qoder-wengu`
- **公开性**：公开可访问
- **关键文件**：
  - [x] `app/main.py`：FastAPI 应用（260 行）
  - [x] `app/retrieval.py`：混合检索（151 行）
  - [x] `app/memory.py`：PowerContext 客户端（193 行）
  - [x] `app/ingest.py`：数据管道（236 行）
  - [x] `app/embed.py`：向量化模块（173 行）
  - [x] `web/index.html`：单页前端（300 行）
  - [x] `requirements.txt`：Python 依赖
  - [x] `.env.example`：配置模板（占位值，无密钥）
  - [x] `scripts/init_db.py`：数据库初始化
  - [x] `scripts/init_demo.sh`：一键启动
  - [x] `scripts/smoke_test.py`：连通性验证

### 3. 运行说明 ✅
- **文件**：[`docs/02-运行说明与验证样例.md`](docs/02-运行说明与验证样例.md)
- **内容**：
  - [x] 环境要求（Python 3.11+, seekdb v1.4.0）
  - [x] 从零到跑通（6 步）
  - [x] 验证样例（V1-V4）
  - [x] 技术分工表
  - [x] 已知限制（不掩饰）
  - [x] 出问题怎么查（故障排查表）

### 4. 验证样例 ✅
- **文件**：[`docs/02-运行说明与验证样例.md`](docs/02-运行说明与验证样例.md) 第三节
- **样例**：
  - [x] V1 · 混合检索命中（输入「非阻塞通信会造成死锁吗」）
  - [x] V2 · 拒绝编造（输入「红烧肉怎么做好吃」）
  - [x] V3 · 出题与判分（概念「伪共享」）
  - [x] V4 · 事实核查（输入「Amdahl 定律的加速比上限」）

### 5. 技术结合证据 ✅
- **seekdb**：
  - [x] 9 张表完整 DDL（[`docs/01-需求与方案.md`](docs/01-需求与方案.md) §4.2）
  - [x] 混合检索 SQL（[`app/retrieval.py`](app/retrieval.py)）
  - [x] 查询日志（`qa_log` 表）
- **PowerContext**：
  - [x] 4 个核心函数（[`app/memory.py`](app/memory.py)）
  - [x] 跨会话验证（[`evidence/qoder/05-记忆层.md`](evidence/qoder/05-记忆层.md)）
  - [x] 降级处理（[`evidence/qoder/08-交付打包.md`](evidence/qoder/08-交付打包.md)）
- **分工原则**：
  > seekdb 记得「资料说了什么」，PowerContext 记得「你哪里不会」

### 6. Qoder 开发记录（文档部分）✅
- **文件**：[`evidence/qoder/01-08-*.md`](evidence/qoder/)
- **内容**：
  - [x] 第 1 轮 · 需求拆解
  - [x] 第 2 轮 · 连通性验证
  - [x] 第 3 轮 · 数据管道
  - [x] 第 4 轮 · 混合检索
  - [x] 第 5 轮 · 记忆层
  - [x] 第 6 轮 · 应用层
  - [x] 第 7 轮 · 复习闭环
  - [x] 第 8 轮 · 交付打包
- **每轮包含**：
  - [x] 本轮目标
  - [x] Qoder 对话要点
  - [x] 关键产出
  - [x] 实测结果
  - [x] 验收标准
  - [x] Commit message
  - [x] 截图建议
  - [x] 踩坑记录

---

## ️ 待补充（需要你完成）

### 7. Qoder 对话截图 ⚠️
**必须补充**，这是判断「真用了 Qoder」最硬的证据。

- [ ] **截图 1-8**：8 轮开发的 Qoder 对话窗口
  - 文件命名：`evidence/qoder/01-08-*.png`
  - 内容要求：
    - 显示 Qoder 界面和对话历史
    - 显示生成的文件内容（同框或分屏）
    - 显示 commit 时间戳
    - **至少 2-3 轮要显示报错→分析→修复的往返过程**

- [ ] **截图 9**：commit 时间线
  - 文件命名：`evidence/qoder/09-commit 时间线.png`
  - 命令：`git log --oneline --graph`
  - 内容：显示 7 个 commit 的时间顺序

- [ ] **截图 10**：Qoder UID
  - 文件命名：`evidence/qoder/10-Qoder-UID.png`
  - 内容：Qoder 设置界面显示 UID
  - 用途：用于核对站点归属

**截图建议**：
1. 打开 Qoder Desktop 或 IDE 插件
2. 找到对应的历史对话
3. 截图时包含：对话内容 + 生成的文件 + 时间戳
4. 如果对话已清除，可以重新打开文件并说明「这是第 X 轮产物」

---

### 8. 使用效果数据 ⚠️（鼓励提交，非必须）

**如果时间允许，建议收集**，这会作为评价维度之一。

- [ ] **邀请试用**：3-5 位同学试用 1 周
- [ ] **记录数据**：
  - 使用人数、使用次数
  - 提效对比（使用前 vs 使用后）
  - 用户反馈（问卷、评价）
- [ ] **访问统计**：Qoder Sites 后台截图
  - 文件：`evidence/screenshots/sites-analytics.png`
- [ ] **整理文档**：填写 [`evidence/USAGE_EFFECT_TEMPLATE.md`](evidence/USAGE_EFFECT_TEMPLATE.md)

**最低要求**：
- 至少 1 位同学试用
- 至少记录 3 次使用
- 至少 1 条用户反馈

---

### 9. 演示视频 ⚠️（鼓励提交，非必须）

**如果时间允许，建议录制**，60 秒即可。

- [ ] **录制内容**：按 [`evidence/DEMO_SCRIPT.md`](evidence/DEMO_SCRIPT.md) 的 60 秒脚本
- [ ] **视频格式**：MP4，1080p
- [ ] **文件位置**：`evidence/demo.mp4`
- [ ] **上传位置**：B 站或 YouTube（可选）

**最低要求**：
- 展示 4 个核心功能
- 有旁白或字幕说明
- 时长 60-120 秒

---

##  提交前最终检查

### 网站可访问性
- [ ] 用浏览器无痕窗口打开 https://wengu-study-coach-ao0rgkrp2dz.qoder.zone
- [ ] 确认未登录状态下可正常访问
- [ ] 确认页面内容完整（滚动到底部）
- [ ] 确认「查看源代码」链接可点击

### 代码仓库
- [ ] 确认分支 `feat/qoder-wengu` 已推送到 GitHub
- [ ] 确认仓库公开可访问（或已向评审开放权限）
- [ ] 确认 `.env.example` 使用占位值，不含真实密钥
- [ ] 确认 `data/local/` 目录不存在或为空（隐私保护）

### 可复现性
- [ ] 在干净环境按运行说明从头跑一遍
- [ ] 确认四个验证样例都能通过
- [ ] 确认 seekdb 和 PowerContext 的集成有实际效果
- [ ] 确认 `bash scripts/init_demo.sh` 能一键启动

### 材料完整性
- [ ] Qoder 对话截图已补充（至少 8 张）
- [ ] Qoder UID 已记录
- [ ] commit 时间线截图已准备
- [ ] 使用效果数据已收集（如有）
- [ ] 演示视频已录制（如有）

---

##  提交步骤

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

## 🎯 评分维度自评

| 维度 | 权重 | 自评 | 证据 |
|------|------|------|------|
| 实用价值 | - | ⭐⭐⭐⭐⭐ | 针对课程复习痛点，混合检索 + 弱点记忆 |
| 使用效果 | - | ⭐⭐⭐☆☆ | 待收集真实用户数据 |
| 完成度与体验 | - | ⭐⭐⭐⭐⭐ | 四个核心功能完整，流程顺畅 |
| 技术结合 | - | ⭐⭐⭐⭐⭐ | seekdb/PC 分工明确，证据充分 |
| Qoder 开发实践 | - | ⭐⭐⭐⭐☆ | 文档完整，待补充对话截图 |
| 工程质量 | - | ⭐⭐⭐⭐⭐ | 代码清晰，文档齐全，一键启动 |

**总体自评**：⭐⭐⭐⭐☆（4.5/5）

---

## 📞 联系方式

如有问题，通过以下方式联系：
- GitHub Issues：https://github.com/oceanbase/powercontext/issues
- 项目网站：https://wengu-study-coach-ao0rgkrp2dz.qoder.zone

---

**祝比赛顺利！** 🎉

**最后更新**：2026-10-28
