# Qoder 对话截图收集指南

> 用于竞赛提交，证明项目由 Qoder 开发

## 一、截图清单（共 10 张）

### 必须截图（8 张）

| 编号 | 文件命名 | 内容 | 优先级 |
|------|---------|------|--------|
| 1 | `01-需求拆解.png` | 第 1 轮 Qoder 对话 + `docs/01-需求与方案.md` | 高 |
| 2 | `02-连通性验证.png` | 第 2 轮对话 + `smoke_test.py` 运行输出 | 高 |
| 3 | `03-数据管道.png` | 第 3 轮对话 + `ingest.py` 运行输出 | 高 |
| 4 | `04-混合检索.png` | 第 4 轮对话 + 检索结果表格 | 高 |
| 5 | `05-记忆跨会话.png` | 第 5 轮对话 + PowerContext 读写日志 | 高 |
| 6 | `06-应用层.png` | 第 6 轮对话 + Web UI 界面 | 高 |
| 7 | `07-复习闭环.png` | 第 7 轮对话 + profile 前后对比 | 高 |
| 8 | `08-交付打包.png` | 第 8 轮对话 + 一键脚本运行 | 中 |

### 建议截图（2 张）

| 编号 | 文件命名 | 内容 | 优先级 |
|------|---------|------|--------|
| 9 | `09-commit 时间线.png` | `git log --oneline --graph` 输出 | 中 |
| 10 | `10-Qoder-UID.png` | Qoder 设置界面的 UID | 高 |

---

## 二、截图方法

### 方法 1：从 Qoder 历史对话截图（推荐）

1. 打开 Qoder Desktop 或 IDE 插件
2. 找到对应的历史对话（按日期或关键词搜索）
3. 调整窗口大小，确保对话内容和生成的文件都能看见
4. 使用系统截图工具（Windows: `Win+Shift+S`，Mac: `Cmd+Shift+4`）
5. 保存到 `evidence/qoder/` 目录

**截图要点**：
- 显示 Qoder 界面（证明是 Qoder 对话）
- 显示对话内容（提示词和回复）
- 显示生成的文件内容（可以分屏或滚动）
- 显示时间戳（证明开发时间线）

### 方法 2：重新生成对话并截图

如果历史对话已清除，可以重新打开 Qoder 并：

1. 打开对应的源文件（如 `docs/01-需求与方案.md`）
2. 在 Qoder 中输入类似的提示词
3. 让 Qoder 重新生成或解释该文件
4. 截图对话过程

**注意**：在截图说明中注明「这是重新生成的对话，原始对话已清除，但文件内容和 commit 时间戳可佐证」

### 方法 3：用文件 + commit 时间戳佐证

如果无法截图对话，可以：

1. 打开生成的文件
2. 运行 `git log --oneline --graph --all --decorate` 显示 commit 历史
3. 截图文件内容 + commit 时间戳
4. 在说明中解释「这是第 X 轮产物，commit 时间戳证明开发时间线」

---

## 三、每张截图的具体要求

### 截图 1：需求拆解

**对话内容**：
- 提示词：「先把这些文件逐篇读一遍，统计主题覆盖、概念重叠...」
- Qoder 回复：生成 `docs/01-需求与方案.md`

**截图要素**：
- [ ] Qoder 界面可见
- [ ] 对话内容可见（至少 3-5 轮对话）
- [ ] 生成的文档内容可见（可以分屏）
- [ ] 时间戳可见

**文件保存**：`evidence/qoder/01-需求拆解.png`

---

### 截图 2：连通性验证

**对话内容**：
- 提示词：「最小连通性验证，不要写任何业务逻辑...」
- Qoder 回复：生成 `smoke_test.py`

**截图要素**：
- [ ] Qoder 界面可见
- [ ] 对话内容可见
- [ ] `python scripts/smoke_test.py` 运行输出可见（显示 ok）
- [ ] 时间戳可见

**文件保存**：`evidence/qoder/02-连通性验证.png`

---

### 截图 3：数据管道

**对话内容**：
- 提示词：「产出 scripts/ingest.py...」
- Qoder 回复：生成 `ingest.py`

**截图要素**：
- [ ] Qoder 界面可见
- [ ] 对话内容可见
- [ ] `python -m app.ingest` 运行输出可见（显示 chunks=23, concept=40）
- [ ] 时间戳可见

**文件保存**：`evidence/qoder/03-数据管道.png`

---

### 截图 4：混合检索

**对话内容**：
- 提示词：「产出 app/retrieval.py...」
- Qoder 回复：生成 `retrieval.py`

**截图要素**：
- [ ] Qoder 界面可见
- [ ] 对话内容可见
- [ ] 检索结果表格可见（显示排名/融合分/出处）
- [ ] 时间戳可见

**文件保存**：`evidence/qoder/04-混合检索.png`

---

### 截图 5：记忆跨会话

**对话内容**：
- 提示词：「产出 app/memory.py...」
- Qoder 回复：生成 `memory.py`

**截图要素**：
- [ ] Qoder 界面可见
- [ ] 对话内容可见
- [ ] PowerContext API 调用日志可见
- [ ] 时间戳可见

**文件保存**：`evidence/qoder/05-记忆跨会话.png`

---

### 截图 6：应用层

**对话内容**：
- 提示词：「产出 app/main.py + web/index.html...」
- Qoder 回复：生成 FastAPI 应用和前端

**截图要素**：
- [ ] Qoder 界面可见
- [ ] 对话内容可见
- [ ] Web UI 界面可见（三个功能区）
- [ ] 时间戳可见

**文件保存**：`evidence/qoder/06-应用层.png`

---

### 截图 7：复习闭环

**对话内容**：
- 提示词：「把 seekdb 和 PowerContext 真正咬合起来...」
- Qoder 回复：实现状态机和写回逻辑

**截图要素**：
- [ ] Qoder 界面可见
- [ ] 对话内容可见
- [ ] profile 前后对比可见（答错 3 次后 count=3）
- [ ] 时间戳可见

**文件保存**：`evidence/qoder/07-复习闭环.png`

---

### 截图 8：交付打包

**对话内容**：
- 提示词：「异常矩阵、测试、一键启动脚本...」
- Qoder 回复：生成 `init_demo.sh` 等

**截图要素**：
- [ ] Qoder 界面可见
- [ ] 对话内容可见
- [ ] `bash scripts/init_demo.sh` 运行输出可见
- [ ] 时间戳可见

**文件保存**：`evidence/qoder/08-交付打包.png`

---

### 截图 9：commit 时间线

**命令**：
```bash
cd qoder/wengu
git log --oneline --graph --all --decorate
```

**预期输出**：
```
* 8e463c73 (HEAD -> feat/qoder-wengu) fix(wengu): 对齐 memory 返回值类型
* de721d7f chore(wengu): pc_scopes.json 是运行时状态，不纳入版本控制
* 21d8e00a feat(wengu): 接入 PowerContext 真实记忆，文档同步，修复 .env 粘行
* 5f422a0b chore(wengu): PowerContext 服务跑通，记忆闭环验证
* 0edb0009 feat(wengu): 检索、出题判分、Web 界面
* b0f21865 feat(gaode): add nearby place recommendation skill
* d647275c chore: initialize 2026 competition ecosystem directories
```

**截图要素**：
- [ ] 终端窗口可见
- [ ] commit 历史完整（7 个 commit）
- [ ] 分支名可见（feat/qoder-wengu）

**文件保存**：`evidence/qoder/09-commit 时间线.png`

---

### 截图 10：Qoder UID

**步骤**：
1. 打开 Qoder Desktop
2. 点击设置（齿轮图标）
3. 找到「账号」或「Account」部分
4. 显示 UID

**截图要素**：
- [ ] Qoder 设置界面可见
- [ ] UID 清晰可见
- [ ] 账号信息可见

**文件保存**：`evidence/qoder/10-Qoder-UID.png`

---

## 四、截图后处理

### 文件命名
所有截图放在 `evidence/qoder/` 目录下，命名格式：
```
evidence/qoder/01-需求拆解.png
evidence/qoder/02-连通性验证.png
...
evidence/qoder/10-Qoder-UID.png
```

### 隐私检查
截图前检查是否包含：
- [ ] 个人邮箱（打码）
- [ ] 个人头像（打码）
- [ ] 本机路径（如 `C:\Users\你的名字\`，打码）
- [ ] API Key（打码）
- [ ] 其他敏感信息（打码）

### 文件大小
- 每张截图建议 < 2MB
- 如果太大，用压缩工具压缩（如 TinyPNG）

---

## 五、快速截图脚本（Windows）

保存为 `scripts/capture_screenshots.ps1`：

```powershell
# 截图收集脚本
# 用法：运行后按提示截图

$dirs = @(
    "evidence/qoder"
)

foreach ($dir in $dirs) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force
    }
}

Write-Host "=== Qoder 对话截图收集 ===" -ForegroundColor Green
Write-Host ""
Write-Host "请按以下顺序截图：" -ForegroundColor Yellow
Write-Host ""

$screenshots = @(
    "01-需求拆解.png",
    "02-连通性验证.png",
    "03-数据管道.png",
    "04-混合检索.png",
    "05-记忆跨会话.png",
    "06-应用层.png",
    "07-复习闭环.png",
    "08-交付打包.png",
    "09-commit 时间线.png",
    "10-Qoder-UID.png"
)

for ($i = 0; $i -lt $screenshots.Count; $i++) {
    $num = $i + 1
    $file = $screenshots[$i]
    Write-Host "[$num/10] 请截图：$file" -ForegroundColor Cyan
    Write-Host "  保存位置：evidence/qoder/$file" -ForegroundColor Gray
    Write-Host "  按回车继续..." -ForegroundColor Gray
    Read-Host
}

Write-Host ""
Write-Host "截图完成！请检查 evidence/qoder/ 目录" -ForegroundColor Green
```

**使用方法**：
1. 打开 PowerShell
2. 运行 `.\scripts\capture_screenshots.ps1`
3. 按提示逐个截图
4. 保存到对应位置

---

## 六、提交说明

在大赛平台提交时，在「Qoder 开发记录」部分说明：

```
本项目采用八轮迭代开发模式，每轮有明确目标、验收标准和 commit。

开发记录包括：
1. 8 轮 Qoder 对话截图（evidence/qoder/01-08-*.png）
2. 每轮详细文档（evidence/qoder/01-08-*.md）
3. commit 时间线（evidence/qoder/09-commit 时间线.png）
4. Qoder UID（evidence/qoder/10-Qoder-UID.png）

关键开发环节：
- 第 1 轮：需求拆解，产出完整方案文档
- 第 2 轮：连通性验证，证明 seekdb 和 PowerContext 都能连上
- 第 3 轮：数据管道，把 markdown 变成可检索的库
- 第 4 轮：混合检索，一条 SQL 完成向量 + 全文 + 标量融合
- 第 5 轮：记忆层，实现 PowerContext 客户端和跨会话记忆
- 第 6 轮：应用层，FastAPI + 单页前端
- 第 7 轮：复习闭环，把 seekdb 和 PowerContext 真正咬合
- 第 8 轮：交付打包，异常矩阵、测试、一键启动

Qoder 在开发中的作用：
- 需求拆解：Qoder 分析语料，识别痛点和功能边界
- 编码实现：Qoder 生成核心代码（retrieval.py, memory.py 等）
- 调试修复：遇到报错时，Qoder 分析原因并给出修复方案
- 文档生成：Qoder 生成运行说明、验证样例等文档

开发过程可追溯：
- 每轮对话有截图
- 每轮产出有 commit
- commit 时间线与对话时间对应
```
