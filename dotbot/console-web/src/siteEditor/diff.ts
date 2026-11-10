// A unified diff of two short texts, for the review: lines kept, removed and
// added, with a little context around each change.

export type DiffLine = { op: " " | "-" | "+"; text: string } | { op: "…"; text: "" };

export function lineDiff(before: string, after: string, context = 2): DiffLine[] {
  const a = before.split("\n");
  const b = after.split("\n");
  // Longest common subsequence table, from the end
  const lcs: number[][] = Array.from({ length: a.length + 1 }, () => new Array(b.length + 1).fill(0));
  for (let i = a.length - 1; i >= 0; i--)
    for (let j = b.length - 1; j >= 0; j--)
      lcs[i][j] = a[i] === b[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1]);
  const all: { op: " " | "-" | "+"; text: string }[] = [];
  let i = 0;
  let j = 0;
  while (i < a.length || j < b.length) {
    if (i < a.length && j < b.length && a[i] === b[j]) {
      all.push({ op: " ", text: a[i] });
      i++;
      j++;
    } else if (i < a.length && (j >= b.length || lcs[i + 1][j] >= lcs[i][j + 1])) {
      all.push({ op: "-", text: a[i++] });
    } else {
      all.push({ op: "+", text: b[j++] });
    }
  }
  const near = all.map((_, k) =>
    all.slice(Math.max(0, k - context), k + context + 1).some((l) => l.op !== " "),
  );
  const out: DiffLine[] = [];
  all.forEach((l, k) => {
    if (near[k]) out.push(l);
    else if (!out.length || out[out.length - 1].op !== "…") out.push({ op: "…", text: "" });
  });
  while (out.length && out[out.length - 1].op === "…") out.pop();
  return out;
}
