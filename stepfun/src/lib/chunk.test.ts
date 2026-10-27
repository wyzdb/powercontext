import { describe, expect, it } from "vitest";
import { buildChunks, parseJsonDocs, splitText } from "./chunk";

describe("chunking", () => {
  it("keeps a short document as one chunk", () => {
    expect(splitText("第一段。\n\n第二段。", { size: 300 })).toHaveLength(1);
  });

  it("splits a long paragraph on sentence boundaries", () => {
    const sentence = "这是一个用于测试分块的句子。";
    const chunks = splitText(sentence.repeat(40), { size: 120, overlap: 20 });
    expect(chunks.length).toBeGreaterThan(1);
    for (const chunk of chunks) {
      expect(chunk.length).toBeLessThanOrEqual(200);
    }
  });

  it("produces stable ids and docId metadata", async () => {
    const doc = {
      id: "doc-1",
      title: "测试",
      text: "第一段。\n\n第二段。",
    };
    const first = await buildChunks(doc, { size: 300, overlap: 50 });
    const second = await buildChunks(doc, { size: 300, overlap: 50 });
    expect(first).toHaveLength(1);
    expect(first[0].id).toBe(second[0].id);
    expect(first[0].metadata.docId).toBe("doc-1");
    expect(first[0].metadata.title).toBe("测试");
  });

  it("parses JSON arrays and objects with documents", () => {
    expect(parseJsonDocs('[{"title":"a","text":"b"}]', "f")[0].title).toBe("a");
    expect(
      parseJsonDocs('{"documents":[{"title":"a","text":"b"}]}', "f")[0].text,
    ).toBe("b");
    expect(parseJsonDocs('["plain text"]', "f")[0].text).toBe("plain text");
  });
});
