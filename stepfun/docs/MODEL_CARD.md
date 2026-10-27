# 模型卡：bge-small-zh-v1.5（ONNX）

## 基本信息

| 项 | 值 |
|---|---|
| 基础模型 | `BAAI/bge-small-zh-v1.5` |
| ONNX 转换 | `Xenova/bge-small-zh-v1.5` |
| Revision | `75c43b069aac4d136ba6bc1122f995fedcfd2781` |
| License | MIT（基础模型与转换仓库） |
| 架构 | BERT（4 层，hidden 512，8 个注意力头，intermediate 2048） |
| 参数量 | 约 24M |
| 最大输入 | 512 token |
| 输出 | 512 维句向量；CLS pooling（BGE 官方 `1_Pooling/config.json`）+ L2 normalize |
| 查询指令 | `为这个句子生成表示以用于检索相关文章：`（仅 query，文档不加） |
| 语言 | 中文为主，混合英文术语可用 |

## 文件与校验

`pnpm models:fetch` 会按下面的字节数与 SHA-256 校验；任何一个不匹配都会失败，不会静默使用损坏文件。

| 文件 | 字节 | SHA-256 |
|---|---:|---|
| `config.json` | 716 | `d4193ead3a810fd694fa8a31d7fc72fbaebc0668b603e398734bf2f6538ff42f` |
| `quantize_config.json` | 674 | `2cc488b20fa05fe86aba2fdc2be44d24827e11e2b7c7a0753d1427da6797b46f` |
| `special_tokens_map.json` | 125 | `b6d346be366a7d1d48332dbc9fdf3bf8960b5d879522b7799ddba59e76237ee3` |
| `tokenizer.json` | 439,125 | `48cea5d44424912a6fd1ea647bf4fe50b55ab8b1e5879c3275f80e339e8fae26` |
| `tokenizer_config.json` | 367 | `e6f3b96db926a37d4039995fbf5ad17de158dfb8f6343d607e4dbaad18d75f5a` |
| `vocab.txt` | 109,540 | `45bbac6b341c319adc98a532532882e91a9cefc0329aa57bac9ae761c27b291c` |
| `onnx/model.onnx` | 94,851,877 | `69a0b846f4f116b5e6aabf9546ea6754d02264f3211a13a1bd69b31b8040749a` |
| `onnx/model_fp16.onnx` | 47,497,427 | `60d0fe5eb8d4e251d4b24dff010a2625c10a013503f0d09f625e8a9b0311315f` |
| `onnx/model_int8.onnx` | 23,903,394 | `b9837c19ce154ff0726d398ee77abbc03a7faf0476c6f93016c84e531be7ebb5` |

## 量化

| 变体 | 方式 | 说明 |
|---|---|---|
| FP32 | 原始导出 | 基线；90.46 MiB |
| FP16 | FP32 → 半精度转换 | 2.00× 压缩；与 FP32 余弦 0.99999；WebGPU 默认 |
| INT8 | 动态量化，per-channel，`reduce_range=true`，QInt8 | 3.97× 压缩；与 FP32 余弦均值约 0.966；WASM 降级 |

`scripts/quantize.py` 可从 FP32 重新生成 INT8（默认 `reduce_range=false`），用于对照。它不改变本仓库默认使用的 `model_int8.onnx`，除非手动覆盖文件。

## 预期用途

- 个人知识库的中文段落检索；查询与文档都在浏览器本地编码。
- 作为 Transformers.js / ONNX Runtime Web 的最小端侧检索样例。
- 作为“量化前后检索质量对比”的工程基线。

## 不适用

- 不能当作通用语义相似度模型做跨语言检索（英文长文本、代码检索未评估）。
- 不适合需要 1024 维或更长上下文的场景；bge-m3 / bge-large 更合适，但端侧成本高。
- 不能用本仓库的 20 条查询集去宣称模型在中文检索上的 SOTA。

## 引用

```bibtex
@misc{bge_embedding,
  title={C-Pack: Packaged Resources To Advance General Chinese Embedding},
  author={Shitao Xiao and Zheng Liu and Peitian Zhang and Niklas Muennighoff},
  year={2023},
  eprint={2309.07597},
  archivePrefix={arXiv},
  primaryClass={cs.CL}
}
```
