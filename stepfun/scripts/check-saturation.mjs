#!/usr/bin/env node
// Sanity check: how hard is the 20-query set? A character-bigram overlap
// ranker is a deliberately weak lexical baseline. If it already puts the
// primary document at rank 1 for every query, the set is saturated and cannot
// distinguish embedding models by nDCG/Recall.
import { readFile, writeFile } from "node:fs/promises";

const corpus = JSON.parse(await readFile("public/corpus/sample.json", "utf8"));
const queries = JSON.parse(await readFile("public/bench/queries.json", "utf8"));

const clean = (text) => text.replace(/[^\u4e00-\u9fa5A-Za-z0-9]/g, "");
const bigrams = (text) => {
  const value = clean(text);
  const set = new Set();
  for (let index = 0; index < value.length - 1; index += 1) {
    set.add(value.slice(index, index + 2));
  }
  return set;
};

const docs = corpus.map((doc) => ({ id: doc.id, grams: bigrams(doc.text) }));
const perQuery = [];
let top1 = 0;

for (const query of queries) {
  const queryGrams = bigrams(query.query);
  const ranked = docs
    .map((doc) => {
      let intersection = 0;
      for (const gram of queryGrams) if (doc.grams.has(gram)) intersection += 1;
      return { id: doc.id, score: intersection / Math.sqrt(doc.grams.size || 1) };
    })
    .sort((a, b) => b.score - a.score);
  const primary = Object.entries(query.qrels).sort((a, b) => b[1] - a[1])[0][0];
  const rank = ranked.findIndex((item) => item.id === primary) + 1;
  if (rank === 1) top1 += 1;
  perQuery.push({
    id: query.id,
    primary,
    rank,
    top1: ranked[0]?.id,
    score: ranked[0]?.score,
  });
}

const report = {
  method: "character bigram overlap / sqrt(document bigrams)",
  queries: queries.length,
  top1,
  top1Rate: top1 / queries.length,
  perQuery,
};
await writeFile(
  "bench/results/phase4/saturation.json",
  JSON.stringify(report, null, 2),
);
console.log(
  `bigram baseline top-1: ${top1}/${queries.length} (${(report.top1Rate * 100).toFixed(0)}%)`,
);
