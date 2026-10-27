export default function AboutPanel() {
  return (
    <div className="max-w-4xl space-y-5">
      <div>
        <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--color-muted)]">
          方法 · 边界
        </p>
        <h2 className="serif mt-1 text-2xl">这个应用做了什么，没做什么</h2>
      </div>

      <section className="card space-y-3 px-6 py-5 text-[13px] leading-6">
        <h3 className="serif text-lg font-semibold">端侧推理</h3>
        <p>
          文档和查询的 embedding 都在浏览器里算：Transformers.js 3.8.1 加载
          Xenova/bge-small-zh-v1.5（512 维），WebGPU 可用时用 FP16
          执行提供者，初始化失败或用户强制时降级到 WASM + INT8。Node
          侧只做 seekdb 的连接、写入、刷新和检索，依赖树里没有任何推理模型；
          collection 的 <span className="mono">embeddingFunction</span> 显式设为{" "}
          <span className="mono">null</span>，避免数据库替我们算向量。
        </p>
        <p>
          查询侧会加 BGE 的中文检索指令“为这个句子生成表示以用于检索相关文章：”，
          文档侧不加。这个选择在{" "}
          <span className="mono">docs/BENCHMARK.md</span> 里有 A/B
          记录；如果最终数据不支持，就以数据为准改回。
        </p>
      </section>

      <section className="card space-y-3 px-6 py-5 text-[13px] leading-6">
        <h3 className="serif text-lg font-semibold">量化</h3>
        <p>
          FP32 权重 90.46 MiB，FP16 45.30 MiB（2.00×），INT8 22.80
          MiB（3.97×）。FP16 与 FP32 的三条样本文本余弦相似度约 0.99999，基本无损；
          INT8 的余弦在 0.96 左右，说明它确实改变了向量方向。因此 INT8
          只作为 WASM 降级路径，并在界面和报告里标注质量代价，而不是假装“无损压缩”。
        </p>
        <p>
          HF 的 INT8 文件使用 per-channel、reduce_range=true 的动态量化。仓库另外提供{" "}
          <span className="mono">scripts/quantize.py</span>，用 reduce_range=false
          从 FP32 重新量化，和官方文件比体积/余弦/检索指标，最终选谁由数据决定。
        </p>
      </section>

      <section className="card space-y-3 px-6 py-5 text-[13px] leading-6">
        <h3 className="serif text-lg font-semibold">seekdb 数据层</h3>
        <p>
          每个知识库对应一个 collection，物理表里有{" "}
          <span className="mono">VECTOR(512)</span>、<span className="mono">document</span>{" "}
          和 <span className="mono">metadata JSON</span>；索引是 HNSW（cosine,
          m=16, ef_construction=200, ef_search=64, SYNC_MODE=ASYNC）加上 IK
          分词的全文索引。写入是异步索引，导入结束后调用{" "}
          <span className="mono">refresh_index()</span>（内部是{" "}
          <span className="mono">CALL dbms_index_manager.refresh()</span>），
          然后用同一条查询验证新片段可见。
        </p>
        <p>
          检索走 <span className="mono">collection.hybridSearch()</span>：seekdb
          生成
          <span className="mono"> match(document) against(...)</span> 与{" "}
          <span className="mono">cosine_distance(embedding, ...)</span> 两路候选，
          在一条 SQL 里用{" "}
          <span className="mono">1/(60+keyword_rank) + 1/(60+semantic_rank)</span>{" "}
          融合。界面的“查看 SQL”能看到原始语句；客户端没有二次融合。
        </p>
      </section>

      <section className="card space-y-3 px-6 py-5 text-[13px] leading-6">
        <h3 className="serif text-lg font-semibold">已知限制</h3>
        <ul className="list-disc space-y-1 pl-5 text-[var(--color-muted)]">
          <li>
            当前只支持文本；图片 OCR 没有做，题目把它列为扩展。
          </li>
          <li>
            Windows 原生嵌入式 seekdb 会挂起，Windows 走 Docker/WSL；Linux/macOS
            的嵌入式路径在 README 里有一条命令。
          </li>
          <li>
            WSL2 下退出进程时 seekdb 偶发 pthread 告警，查询不受影响；原生 Linux
            未复现。
          </li>
          <li>
            示例语料只有 20 篇，检索质量结论只在这个规模上成立；完整评测集和原始
            数据在 <span className="mono">bench/</span>。
          </li>
        </ul>
      </section>
    </div>
  );
}
