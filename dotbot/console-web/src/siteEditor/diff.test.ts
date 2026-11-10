import { describe, expect, it } from "vitest";

import { fullDiff, lineDiff } from "./diff";

describe("the review's diff", () => {
  it("shows the changed lines with their context and elides the rest", () => {
    const before = ["a", "b", "c", "d", "e", "f", "g", "h"].join("\n");
    const after = ["a", "b", "c", "d", "E", "f", "g", "h"].join("\n");
    expect(lineDiff(before, after, 1)).toEqual([
      { op: "…", text: "" },
      { op: " ", text: "d" },
      { op: "-", text: "e" },
      { op: "+", text: "E" },
      { op: " ", text: "f" },
    ]);
  });

  it("is empty for the same text", () => {
    expect(lineDiff("x\ny", "x\ny")).toEqual([]);
  });
});

describe("the full diff", () => {
  it("keeps every line, marked", () => {
    expect(fullDiff("a\nb\nc", "a\nB\nc").map((l) => `${l.op}${l.text}`)).toEqual([" a", "-b", "+B", " c"]);
    expect(fullDiff("a\nb", "a\nb")).toHaveLength(2);
  });
});
