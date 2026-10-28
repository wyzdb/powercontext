# 温故

> 把一份讲义变成会记住你弱点的复习教练。
> 赛题：Qoder × OceanBase —— Build with Qoder。

**状态**：语料已就绪（原创示例讲义），应用代码待 Qoder 按 [`docs/00-Qoder提示词脚本.md`](docs/00-Qoder提示词脚本.md) 逐轮生成。

## 目录

| 路径 | 用途 |
|---|---|
| [`docs/00-Qoder提示词脚本.md`](docs/00-Qoder提示词脚本.md) | 八轮开发脚本：提示词、验收标准、截图点、commit 规范 |
| [`data/raw/`](data/raw/) | 语料，6 篇原创讲义，1.27 万字 / 23 节 |
| [`data/CORPUS.md`](data/CORPUS.md) | 语料来源、许可、结构约定、替换方式 |
| [`data/manifest.json`](data/manifest.json) | 清单（doc_id / 节数 / 字数 / 估算块数） |
| [`scripts/build_manifest.py`](scripts/build_manifest.py) | 生成清单 + 隐私自检 |
| `data/local/` | **私有目录，已 gitignore，永不提交** |

## 语料

6 篇自编讲义，覆盖并行计算的核心概念：体系结构、性能度量、MPI 点对点、MPI 集合通信、OpenMP、算法设计。

选择自编语料而不是课程资料，是因为课程资料同时踩了三个坑：含他人材料、含身份信息、有版权。自编语料这三条一次性消除，许可以 CC BY 4.0 发布。详见 [`data/CORPUS.md`](data/CORPUS.md)。

每个 `##` 小节就是切片单元，400–700 字，所以「引用溯源」能精确到「哪个文件第几节」。

## 技术栈（待实现）

| 组件 | 职责 |
|---|---|
| seekdb | 切片、向量、全文索引；一条 SQL 完成混合检索与出处溯源 |
| PowerContext | 每个学习者一个 scope，存薄弱点、进度、讲解偏好 |
| Qoder | 全部开发工作，项目网站通过 Qoder Sites 发布 |

## 隐私

- 仓库内不含任何个人信息、他人材料或受限版权内容
- `data/local/` 整棵树被 `.gitignore` 挡住，`.doc` / `.docx` / `.pdf` 也一并挡掉
- `scripts/build_manifest.py --check` 可作提交前自检

运行说明由第 8 轮生成，届时替换本节。

## 运行与验证

按 [`docs/02-运行说明与验证样例.md`](docs/02-运行说明与验证样例.md) 六步启动：

```powershell
docker run -d --name seekdb -p 2881:2881 oceanbase/seekdb:latest
python -m pip install pymysql fastapi "uvicorn[standard]" -i https://pypi.tuna.tsinghua.edu.cn/simple
python -m app.ingest
python -m uvicorn app.main:app --port 8080
```

四个接口：`/api/ask`（带出处问答）、`/api/quiz`（出题）、`/api/grade`（判分）、`/api/profile/{learner}`（弱点画像）。

## 当前状态

| 项 | 状态 |
|---|---|
| 语料 | 6 篇 / 23 节，CC BY 4.0 |
| 表结构 | 12 条 DDL 在 seekdb v1.4.0 实测通过 |
| 入库 | 23 块 / 40 概念 |
| 检索 | 验收 5/7，两条排在相邻小节 |
| 出题判分 | 可用（qwen-plus） |
| PowerContext | 已接入（本地构建 `powercontext-server:local`，`127.0.0.1:8000`），`/api/profile` 读真数据 |
| 网站 | ✅ 已发布：https://wengu-study-coach-ao0rgkrp2dz.qoder.zone |
