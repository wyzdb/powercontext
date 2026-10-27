import { describe, expect, it } from "vitest";
import {
  jaccardAtK,
  kendallTau,
  mrrAtK,
  ndcgAtK,
  p95,
  recallAtK,
} from "./metrics";

describe("retrieval metrics", () => {
  it("computes recall at k", () => {
    expect(recallAtK(["a", "x"], { a: 2, b: 1 }, 5)).toBe(0.5);
    expect(recallAtK(["b", "a"], { a: 2, b: 1 }, 5)).toBe(1);
    expect(recallAtK([], { a: 2 }, 5)).toBe(0);
  });

  it("computes nDCG with graded relevance", () => {
    expect(ndcgAtK(["a", "b"], { a: 2, b: 1 }, 2)).toBeCloseTo(1, 10);
    expect(ndcgAtK(["b", "a"], { a: 2, b: 1 }, 2)).toBeCloseTo(0.7967, 3);
    expect(ndcgAtK(["x"], { a: 2 }, 5)).toBe(0);
  });

  it("computes MRR at k", () => {
    expect(mrrAtK(["x", "a"], { a: 2 }, 10)).toBe(0.5);
    expect(mrrAtK(["x"], { a: 2 }, 10)).toBe(0);
    expect(mrrAtK(["a"], { a: 2 }, 1)).toBe(1);
  });

  it("computes top-k Jaccard", () => {
    expect(jaccardAtK(["a", "b"], ["b", "c"], 2)).toBeCloseTo(1 / 3, 10);
    expect(jaccardAtK(["a", "b"], ["a", "b"], 2)).toBe(1);
  });

  it("computes Kendall tau", () => {
    expect(kendallTau(["a", "b", "c"], ["a", "b", "c"])).toBe(1);
    expect(kendallTau(["a", "b", "c"], ["c", "b", "a"])).toBe(-1);
  });

  it("computes p95", () => {
    expect(p95([1, 2, 3, 4, 5])).toBe(5);
    expect(p95([])).toBe(0);
  });
});
