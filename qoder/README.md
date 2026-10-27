# ResearchFlow · 研途

面向研究生和科研人员的**资料检索 + 研究记忆**工具。

- 论文笔记、实验记录、组会待办写入 **seekdb** 表 `rf_notes`，按标题/正文/标签检索。
- 研究兴趣、当前阶段、下一步目标写入 **PowerContext Memory**，模块重启后读取并用于推荐。
- FastAPI + 原生 HTML/CSS/JS，Qoder Sites 站点源码在 `site/`。

## 目录

```
app/            FastAPI 服务、seekdb/SQLite 适配、PowerContext 记忆
app/static/     可交互的研究工作台
data/           6 篇种子研究笔记
site/           Qoder Sites 项目网站源码
validation/     一键验证脚本
record/         Qoder 开发记录、验证日志、数据库/记忆记录
```

## 运行

```bash
cd qoder
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH="$(cd .. && pwd)/src"
```

`requirements.txt` 使用 `pylibseekdb==1.3.0.post5`；如果评测环境锁定 1.3.x 其他小版本，替换为环境提供的版本。没有 seekdb 绑定时自动回退 SQLite，接口返回的 `store` 会标注实际后端。

初始化并验证：

```bash
python validation/run.py seekdb
# 或
python validation/run.py sqlite
```

启动：

```bash
uvicorn app.main:app --reload
```

打开 <http://127.0.0.1:8000>：

1. 在“检索研究资料”输入 `transformer attention`，应返回 `note-001`；
2. 保存研究画像（兴趣 `retrieval, memory`，目标“完成 retrieval baseline 的消融实验”）；
3. 点击“读取记忆并推荐”，应返回 `note-002`、`note-006` 等；
4. 重启服务后再次推荐，画像仍存在。

## 验证样例

```bash
cd qoder
python validation/run.py sqlite
```

预期：

- `seeded` = 6
- 检索命中 `note-001`
- 画像 interests = `["retrieval", "memory"]`
- 重启后推荐命中 `note-002`、`note-006`、`note-003`
- `state_reused` = “完成 retrieval baseline 的消融实验”

完整输出见 `record/validation_result.json`。

## 技术分工

| 技术 | 实际作用 |
| --- | --- |
| seekdb | `rf_notes` 表存储笔记；检索查询返回来源 `seekdb://rf_notes/...`；无绑定环境回退 SQLite |
| PowerContext | Memory scope 保存 `RESEARCHFLOW_PROFILE:` 画像；重启后读取并驱动推荐 |
| Qoder | 需求拆解、编码、调试、Qoder Sites 发布（见 `record/qoder_development.md`） |

## Qoder Sites

`site/` 是可直接由 Qoder Sites 发布的静态站点源码。发布步骤：

1. 在 Qoder 中打开本项目，使用 Sites 导入 `qoder/site/`；
2. 发布后将可见范围设为“任何人都可访问”；
3. 把站点 URL 和 Qoder 账号 UID 填入 `record/qoder_development.md` 与平台提交表单。

仓库不保存任何 Qoder 或数据库凭据。

## 已知限制

- seekdb Python 绑定仅支持 Linux；其他平台自动回退 SQLite，属于可运行的回退路径。
- 笔记为 6 篇本地样例，便于评审复现；可替换 `data/notes.json` 导入真实资料。
