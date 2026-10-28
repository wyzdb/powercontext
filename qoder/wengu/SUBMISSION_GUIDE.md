# 温故 · 竞赛提交指南

> Qoder × OceanBase 2026 大赛 —— Build with Qoder

## ✅ 已完成的工作

### 1. 项目开发 ✅
- 核心功能完整：混合检索、出题判分、弱点记忆、复习清单
- seekdb 集成：9 张表，向量+全文+标量混合检索
- PowerContext 集成：跨会话学习者记忆
- Web UI：单页应用，纯 HTML+JS
- 文档齐全：需求方案、运行说明、验证样例、开发脚本

### 2. 项目网站 ✅
- 展示网站已创建：`site/index.html`
- 已通过 Qoder Sites 发布
- 访问权限已设为公开
- **网站地址**：https://wengu-study-coach-ao0rgkrp2dz.qoder.zone

### 3. 辅助脚本 ✅
- `requirements.txt`：Python 依赖清单
- `scripts/init_db.py`：数据库初始化脚本
- `scripts/init_demo.sh`：一键启动脚本

---

##  提交材料清单

### 必填项

#### 1. 项目网站网址 ✅
```
https://wengu-study-coach-ao0rgkrp2dz.qoder.zone
```
- 已通过无痕窗口验证可访问
- 访问权限：任何人都可访问

#### 2. 代码仓库 ✅
```
https://github.com/oceanbase/powercontext/tree/2026-competition-ecosystem/qoder/wengu
```
- 分支：`feat/qoder-wengu`
- 公开可访问

#### 3. 运行说明 ✅
见 [`docs/02-运行说明与验证样例.md`](docs/02-运行说明与验证样例.md)

**快速启动（四步）：**
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

或一键启动：
```bash
bash scripts/init_demo.sh
```

#### 4. 验证样例 ✅
见 [`docs/02-运行说明与验证样例.md`](docs/02-运行说明与验证样例.md) 第三节

**四个验证场景：**
- V1：混合检索命中（输入「非阻塞通信会造成死锁吗」）
- V2：拒绝编造（输入「红烧肉怎么做好吃」）
- V3：出题与判分（概念「伪共享」）
- V4：跨会话记忆（答错 3 次后重启验证）

#### 5. Qoder 开发记录 ️ **待准备**
需要整理以下内容：
- [ ] 8 轮开发的 Qoder 对话截图
- [ ] 每轮的 commit 记录（已有 7 个 commit）
- [ ] Qoder 账号 UID
- [ ] 关键开发环节的录屏（可选但推荐）

**建议截图点：**
1. 第 1 轮：需求拆解对话 + `docs/01-需求与方案.md` 生成结果
2. 第 2 轮：`smoke_test.py` 运行输出（seekdb + PowerContext 连通）
3. 第 3 轮：`ingest.py` 运行输出（入库统计）
4. 第 4 轮：混合检索 SQL + EXPLAIN 结果
5. 第 5 轮：PowerContext 记忆读写日志
6. 第 6 轮：Web UI 界面截图（提问/出题/弱点三区）
7. 第 7 轮：复习闭环演示（答错→记忆→下次出题）
8. 第 8 轮：一键启动脚本运行 + pytest 结果

#### 6. 技术结合证据 ✅
见 [`docs/01-需求与方案.md`](docs/01-需求与方案.md) 第 3 节

**seekdb 作用：**
- 存储 9 张表：文档、切片、概念、题目、日志
- 一条 SQL 完成向量+全文+标量混合检索
- 证据：`qa_log` 表记录每次查询

**PowerContext 作用：**
- 每个学习者一个 scope，存储弱点/进度/偏好
- 跨会话持久化记忆
- 证据：`/api/profile` 读真数据，答错后条目数 +1

**分工原则：**
> seekdb 记得「资料说了什么」，PowerContext 记得「你哪里不会」

---

### 鼓励提交项

#### 7. 使用效果 ⚠️ **待收集**
建议收集以下数据：
- [ ] 使用人数、使用次数
- [ ] 提效对比（使用前 vs 使用后）
- [ ] 用户反馈（问卷、评价）
- [ ] 访问统计截图（Qoder Sites 后台可查看）

**建议行动：**
1. 邀请 3-5 位同学试用 1 周
2. 记录他们的使用次数和反馈
3. 对比手动翻讲义 vs 用温故检索的时间
4. 截图 Qoder Sites 访问统计

---

## 🔍 提交前检查

### 网站可访问性
- [ ] 用无痕窗口打开 https://wengu-study-coach-ao0rgkrp2dz.qoder.zone
- [ ] 确认未登录状态下可正常访问
- [ ] 确认页面内容完整（项目简介、功能、技术栈、运行说明）

### 代码仓库
- [ ] 确认分支 `feat/qoder-wengu` 已推送到 GitHub
- [ ] 确认仓库公开可访问（或已向评审开放权限）
- [ ] 确认 `.env.example` 使用占位值，不含真实密钥

### 可复现性
- [ ] 在干净环境按运行说明从头跑一遍
- [ ] 确认四个验证样例都能通过
- [ ] 确认 seekdb 和 PowerContext 的集成有实际效果

### 配置示例
- [ ] `.env.example` 中所有密钥使用占位值
- [ ] 运行说明中的命令可直接复制执行
- [ ] 没有硬编码的本地路径或个人信息

---

## 📊 评分维度对照

| 维度 | 关注内容 | 当前状态 | 建议 |
|------|---------|---------|------|
| 实用价值 | 针对真实痛点，解决方式有效 | ✅ 针对课程复习痛点，混合检索+弱点记忆 | 在使用效果中强调提效数据 |
| 使用效果 | 真实用户，提效对比，可核对数据 | ⚠️ 待收集 | 邀请同学试用并记录 |
| 完成度与体验 | 流程完整顺畅，功能实现 | ✅ 四个核心功能完整 | 准备演示视频 |
| 技术结合 | seekdb/PC 实际发挥作用 | ✅ 分工明确，证据充分 | 在开发记录中突出 |
| Qoder 开发实践 | 开发记录展示 Qoder 作用 | ️ 待整理截图 | 整理 8 轮对话截图 |
| 工程质量 | 代码清晰，依赖齐全，可复现 | ✅ 文档齐全，一键启动 | 确保评审能顺利复现 |

---

## 🎯 下一步行动

### 必须完成
1. **整理 Qoder 开发记录**
   - 截图 8 轮开发对话
   - 记录 Qoder UID
   - 整理 commit 时间线

2. **准备演示材料**
   - 录制 60 秒演示视频（可选但推荐）
   - 截图核心功能界面
   - 准备演示脚本

### 建议完成
3. **收集使用效果**
   - 邀请同学试用并记录
   - 截图访问统计
   - 整理提效对比数据

4. **最终检查**
   - 用无痕窗口验证网站可访问
   - 在干净环境测试运行说明
   - 确认所有材料齐全

---

## 📝 提交入口

登录大赛测试平台，进入 Qoder 赛题的提交入口，填写：
- 项目网站网址：https://wengu-study-coach-ao0rgkrp2dz.qoder.zone
- 代码仓库地址：https://github.com/oceanbase/powercontext/tree/2026-competition-ecosystem/qoder/wengu
- Qoder 账号 UID：（你的 UID）
- 上传其余材料（运行说明、验证样例、开发记录等）

---

**祝比赛顺利！** 
