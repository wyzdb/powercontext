export type Qrels = Record<string, number>;

export function recallAtK(ranked: string[], qrels: Qrels, k: number): number {
  const relevant = Object.keys(qrels).filter((id) => qrels[id] >= 1);
  if (relevant.length === 0) return 0;
  const top = new Set(ranked.slice(0, k));
  return relevant.filter((id) => top.has(id)).length / relevant.length;
}

export function ndcgAtK(ranked: string[], qrels: Qrels, k: number): number {
  const dcg = ranked.slice(0, k).reduce((sum, id, index) => {
    const rel = qrels[id] ?? 0;
    return sum + (2 ** rel - 1) / Math.log2(index + 2);
  }, 0);

  const idealRels = Object.values(qrels)
    .filter((rel) => rel > 0)
    .sort((a, b) => b - a)
    .slice(0, k);
  const idcg = idealRels.reduce(
    (sum, rel, index) => sum + (2 ** rel - 1) / Math.log2(index + 2),
    0,
  );
  return idcg === 0 ? 0 : dcg / idcg;
}

export function mrrAtK(ranked: string[], qrels: Qrels, k: number): number {
  for (let index = 0; index < Math.min(ranked.length, k); index += 1) {
    if ((qrels[ranked[index]] ?? 0) >= 1) return 1 / (index + 1);
  }
  return 0;
}

export function jaccardAtK(a: string[], b: string[], k: number): number {
  const left = new Set(a.slice(0, k));
  const right = new Set(b.slice(0, k));
  if (left.size === 0 && right.size === 0) return 1;
  let intersection = 0;
  for (const id of left) if (right.has(id)) intersection += 1;
  return intersection / (left.size + right.size - intersection);
}

export function kendallTau(a: string[], b: string[]): number {
  const common = a.filter((id) => b.includes(id));
  if (common.length < 2) return 1;
  let concordant = 0;
  let discordant = 0;
  for (let i = 0; i < common.length; i += 1) {
    for (let j = i + 1; j < common.length; j += 1) {
      const deltaA = a.indexOf(common[i]) - a.indexOf(common[j]);
      const deltaB = b.indexOf(common[i]) - b.indexOf(common[j]);
      if (deltaA * deltaB > 0) concordant += 1;
      else if (deltaA * deltaB < 0) discordant += 1;
    }
  }
  return (concordant - discordant) / (concordant + discordant || 1);
}

export function mean(values: number[]): number {
  if (values.length === 0) return 0;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

export function median(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0
    ? (sorted[middle - 1] + sorted[middle]) / 2
    : sorted[middle];
}

export function p95(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.min(sorted.length - 1, Math.ceil(sorted.length * 0.95) - 1);
  return sorted[index];
}
