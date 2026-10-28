# 财报 PDF 页级来源与离线检索

安装 `powercontext[pdf,builtin]`。解析器使用 pypdf，不执行 OCR，不调用模型或在线服务。

## 全页解析

```python
from pathlib import Path
from powercontext.sources.pdf_pages import PDFDocumentInput, parse_pdf_document

pages = parse_pdf_document(PDFDocumentInput(
    document_id="company_2025_annual_report",
    content=Path("report.pdf").read_bytes(),
))
```

返回值为按物理页顺序排列的 `tuple[PDFPageInput, ...]`，页码从 1 开始，包括空白页。文本使用 pypdf 普通提取模式，不增删财务词项，不跨页拼接。每页保存完整输入字节的 SHA-256 摘要。

文档 ID 不能为空或纯空白。空文件、非 PDF、损坏文件、需要非空密码的文件及无法完整提取的文件抛出 `ValueError`；后续页失败也不会返回前缀结果。空密码权限保护可正常读取。无效的内容流结构不能被静默当作空白页。

## Source 与标准投影

```python
from powercontext.sources import SourceDefinitionRegistry, project_source_for_transport
from powercontext.sources.pdf_pages import PDF_PAGE_SOURCE_DEFINITION

registry = SourceDefinitionRegistry((PDF_PAGE_SOURCE_DEFINITION,))
source = await registry.resolve(pages[0])
assert await registry.read(source) == pages[0]
observation = project_source_for_transport(registry, source)
```

Definition 名称为 `pdf-page`，版本为 `1`，输入类型为 `PDFPageInput`，Source 为 `CAPTURED`。身份使用文档 ID、完整摘要及物理页码的规范 JSON 编码计算 SHA-256，名称长度固定为 73 字符。文档修订会生成新身份；捕获页本身保留旧修订文本。

标准文本投影的内容为 `document_id + "\n" + page.text`，metadata 仅含 `document_id`、`document_sha256` 和 `page_number`。先以摘要查找原文件，再按物理页码回查，不使用印刷页码。

提交 observation 前需在 Runtime ingestion 注册 `manifest_for_definition(PDF_PAGE_SOURCE_DEFINITION)`。通过 Runtime 的现有 pipeline 将投影正文存入 scoped Memory；该模块不替换调用方的处理流水线。

## 检索

```python
from powercontext.sources.pdf_pages import search_pdf_pages

memory = runtime.memory.for_scope(scope_id)
citations = await search_pdf_pages(memory, "What was the operating income in FY2025?", limit=20)
```

检索仅通过传入 Memory 的公开 `search` 和 `get` API。使用 `fts` 模式，移除问题中的功能词，以短查询和通用财务词汇扩展获取候选，再按 BM25、相邻词组、报表标题及文档身份匹配排序。标题信号取自页面内的短文本行，兼顾一页中途开始的新章节，减少附录中的长段重复提及对主报表的干扰。最多执行 14 次搜索，每次最多 512 个候选；不会遍历文件系统、读取评测标注、写辅助索引或访问网络。

每个返回值保留 Memory 给出的精确 revision、entry ID 和 entry version ID。返回前执行 `get`，过滤非 PDF 来源和含多个 PDF 页的歧义条目，并按页级 Source 身份去重。返回数量不超过 `limit`；空问题及非正 limit 返回空元组。只在调用方给定 scope 中搜索，不跨 scope 缓存。

## 验证范围

公开验收命令见 `competition/README.md`，独立回归测试位于 `tests/test_pdf_pages.py`。公开验收覆盖完整 503 页、持久化、幂等、重启和精确引用；不提供解析质量或 evidence-page Recall@20 的正式分数。没有标注数据时不能确认隐藏集质量阈值或承诺赛事得分。
