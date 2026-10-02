import { describe, expect, it } from "vitest";

import { HISTORY_LIMIT, record, redo, startHistory, undo } from "./history";

describe("history", () => {
  it("undoes and redoes one step at a time", () => {
    let h = startHistory(0);
    h = record(h, 1);
    h = record(h, 2);
    h = undo(h);
    expect(h.present).toBe(1);
    h = undo(h);
    expect(h.present).toBe(0);
    expect(undo(h)).toBe(h);
    h = redo(h);
    expect(h.present).toBe(1);
  });

  it("coalesces edits that share a key into one step", () => {
    let h = startHistory("a");
    h = record(h, "ab", "name");
    h = record(h, "abc", "name");
    h = record(h, "abcd", "other");
    expect(h.past).toEqual(["a", "abc"]);
    expect(undo(undo(h)).present).toBe("a");
  });

  it("drops the redo branch on a new edit", () => {
    let h = record(record(startHistory(0), 1), 2);
    h = record(undo(h), 5);
    expect(h.future).toEqual([]);
    expect(redo(h)).toBe(h);
  });

  it("keeps at most the limit of past steps", () => {
    let h = startHistory(0);
    for (let i = 1; i <= HISTORY_LIMIT + 10; i += 1) h = record(h, i);
    expect(h.past).toHaveLength(HISTORY_LIMIT);
  });
});
