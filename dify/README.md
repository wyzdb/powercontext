# 斗地主 · 读心牌桌

> 赛题：Just for Fun —— 用 Dify 做一个好玩的智能应用
> 一句话：残局闯关，**牌由引擎打，话由 LLM 说，旧账由 PowerContext 记**。你上一关怎么赢的，下一关它还记得。

## 现在是什么状态

| 项 | 状态 |
|---|---|
| Dify Chatflow（14 节点） | ✅ 已搭好并发布 |
| 规则引擎（783 行，20 条单测） | ✅ 跑在 Dify 代码节点里 |
| seekdb 存知识库向量 | ✅ 1 张表、36 条向量 |
| PowerContext 存玩家战绩 | ✅ 跨会话召回已验证 |
| DSL 导出 | ✅ `dsl/斗地主-读心牌桌.yml` |
| 验证截图 | ✅ `evidence/` 6 张 |

## 目录

| 路径 | 内容 |
|---|---|
| [`docs/01-斗地主-执行手册.md`](docs/01-斗地主-执行手册.md) | 从零部署：Dify + seekdb + PowerContext + 搭应用 |
| [`docs/02-验证样例.md`](docs/02-验证样例.md) | V1–V4 样例与实测输出 |
| [`docs/03-技术说明.md`](docs/03-技术说明.md) | 分工、时序、适配补丁、踩坑记录 |
| [`engine/`](engine/) | 规则引擎、20 个残局、单测、Dify 节点代码 |
| [`data/kb/`](data/kb/) | 知识库三个文档 |
| [`deploy/`](deploy/) | seekdb compose、适配补丁、PowerContext 环境变量 |
| [`dsl/`](dsl/) | 导出的 DSL |
| [`evidence/`](evidence/) | 运行证据截图 |
| `scripts/dify-api/` | 通过控制台 API 构建/验证应用的脚本 |

## 先跑通引擎（不依赖 Dify）

```bash
cd engine
python3 -m unittest          # 20 条测试全过
python3 build_dify_node.py   # 生成 dify_node.py（粘进 Dify 代码节点）
python3 make_kb.py           # 重新生成 data/kb/01-残局讲解.md
```

## 版本

| 组件 | 版本 |
|---|---|
| Dify | 1.9.1 |
| seekdb | `quay.io/oceanbase/seekdb:latest`（2881） |
| PowerContext | 1.4.1 |
| 对话模型 | 百炼 `qwen-plus` |
| Embedding | 百炼 `text-embedding-v3`（1024 维） |

## 导入顺序

1. 按 `docs/01` 部署 Dify + seekdb + PowerContext，跑冒烟测试
2. 先执行 `deploy/patch_oceanbase_vector.py` 打适配补丁（否则知识库建不出来）
3. 建知识库，导入 `data/kb/` 三个文档
4. 导入 `dsl/斗地主-读心牌桌.yml`
5. 重新绑定知识库、把环境变量 `PC_BASE_URL` 改成你的 PowerContext 地址
6. 配置模型（`qwen-plus` + `text-embedding-v3`）并发布
7. 按 `docs/02` 跑 V1–V4

## 许可与来源

- 规则引擎、关卡数据、知识库文档均为原创。
- `deploy/patch_oceanbase_vector.py` 修改的是 Dify（Apache-2.0 + 附加条款）的源码，仅作兼容性修复，未改变其许可。
