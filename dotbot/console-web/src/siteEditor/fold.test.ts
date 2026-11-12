import { describe, expect, it } from "vitest";

import { nextFold } from "./fold";

// What useFold does after each render: draw a level, measure it, step, until it holds.
function settle(widths: number[], roomAt: (l: number) => number, from = 0, known: (number | undefined)[] = []): number {
  const max = widths.length - 1;
  let level = from;
  for (let n = 0; n < 50; n++) {
    known[level] = widths[level];
    const next = nextFold(level, max, widths[level], roomAt, known);
    if (next === level) return level;
    level = next;
  }
  throw new Error("the fold never settled");
}

// The kinds bar: wide, full, compact, icons, icons with the presets on a second row
const KINDS = [760, 680, 560, 300, 300];
const PRESETS = 270;
const kindsRoom = (map: number) => (l: number) => (l >= 4 ? map - 24 : map - 24 - PRESETS - 8);

describe("folding by measured room", () => {
  it("keeps everything when it fits", () => {
    expect(settle(KINDS, kindsRoom(1200))).toBe(0);
  });

  it("drops one level at a time until the bar fits beside the presets", () => {
    expect(settle(KINDS, kindsRoom(1000))).toBe(1);
    expect(settle(KINDS, kindsRoom(880))).toBe(2);
    expect(settle(KINDS, kindsRoom(700))).toBe(3);
  });

  it("puts the presets on a second row when even the icons do not fit beside them", () => {
    expect(settle(KINDS, kindsRoom(560))).toBe(4);
  });

  it("never settles on a level wider than its room", () => {
    for (let map = 300; map <= 1400; map += 7) {
      const l = settle(KINDS, kindsRoom(map));
      if (l < 4) expect(KINDS[l]).toBeLessThanOrEqual(kindsRoom(map)(l));
    }
  });

  it("unfolds again when the room grows, without trying a level known not to fit", () => {
    const known: (number | undefined)[] = [];
    const folded = settle(KINDS, kindsRoom(700), 0, known);
    expect(folded).toBe(3);
    expect(settle(KINDS, kindsRoom(880), folded, known)).toBe(2);
    expect(settle(KINDS, kindsRoom(1200), 2, known)).toBe(0);
  });

  it("stays at the last level when nothing fits", () => {
    expect(settle([500, 400], () => 100)).toBe(1);
  });
});
