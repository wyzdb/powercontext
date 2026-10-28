# 温故 · 快速启动指南

> 让你立即体验温故应用

## 一、启动步骤

### 步骤 1：启动 Docker Desktop

1. 在 Windows 开始菜单搜索「Docker Desktop」
2. 点击打开
3. 等待 Docker 图标变为绿色（表示正在运行）
4. 预计耗时：30-60 秒

### 步骤 2：启动 seekdb 容器

打开 PowerShell 或 CMD，运行：

```powershell
docker run -d --name seekdb -p 2881:2881 -p 2886:2886 oceanbase/seekdb:latest
```

等待容器启动（约 30 秒），可以用以下命令检查：

```powershell
docker ps | grep seekdb
```

看到 seekdb 容器在运行即可。

### 步骤 3：安装 Python 依赖

```powershell
cd C:\Users\L\powercontext\qoder\wengu
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 步骤 4：初始化数据库

```powershell
python scripts/init_db.py
```

预期输出：
```
连接 seekdb: 127.0.0.1:2881
执行 DDL...
写入初始数据...
✓ 数据库初始化完成
  库名：wengu
  表数：9
  初始数据：kb_meta 7 行
```

### 步骤 5：导入语料

```powershell
python -m app.ingest
```

预期输出：
```
语料 6 篇，向量方案 = dashscope（1024 维）
  01-architecture.md       4 节   1717 字
  02-performance.md        4 节   1626 字
  03-mpi-basics.md         4 节   2728 字
  04-collectives.md        4 节   2143 字
  05-openmp.md             4 节   2789 字
  06-design.md             3 节   1696 字
概念词表 40 条，切片 23 块

拟合 IDF...
向量化中...
  完成，首条维度 1024
  概念关联 87 条

入库完成：chunks=23  concept=40
```

### 步骤 6：启动应用

```powershell
python -m uvicorn app.main:app --port 8081
```

预期输出：
```
INFO:     Started server process [xxxxx]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8081 (Press CTRL+C to quit)
```

### 步骤 7：打开浏览器

在浏览器中打开：http://127.0.0.1:8081

---

## 二、一键启动脚本

如果你想一键完成所有步骤，运行：

```powershell
cd C:\Users\L\powercontext\qoder\wengu
bash scripts/init_demo.sh
```

这个脚本会自动：
1. 检查 seekdb 连接
2. 安装 Python 依赖
3. 初始化数据库
4. 导入语料
5. 启动服务

---

## 三、验证功能

启动后，你可以体验以下功能：

### 1. 提问检索
- 在提问框输入：「非阻塞通信会造成死锁吗」
- 点击「检索」
- 查看返回的引用卡片

### 2. 出题判分
- 在出题区输入：「伪共享」
- 点击「出题」
- 等待 5-10 秒，查看生成的题目
- 写下答案，点击「提交判分」

### 3. 查看弱点
- 滚动到「我的弱点」区域
- 查看弱点表格和复习清单

---

## 四、常见问题

### Q1: Docker 启动失败
**A**: 确保 Docker Desktop 已安装并运行。如果没有安装，从 https://www.docker.com/products/docker-desktop 下载。

### Q2: seekdb 容器启动失败
**A**: 检查端口 2881 是否被占用：
```powershell
netstat -ano | findstr :2881
```
如果被占用，先停止占用端口的进程。

### Q3: 导入语料失败
**A**: 检查 `.env` 文件是否存在：
```powershell
copy .env.example .env
```
然后编辑 `.env`，填入你的 DashScope API Key（可选，不填会使用离线 IDF 哈希）。

### Q4: 应用启动失败
**A**: 检查 Python 依赖是否安装完整：
```powershell
pip install pymysql fastapi "uvicorn[standard]"
```

---

## 五、停止应用

按 `Ctrl+C` 停止 uvicorn 服务。

停止 seekdb 容器：
```powershell
docker stop seekdb
docker rm seekdb
```

---

**祝你使用愉快！**
