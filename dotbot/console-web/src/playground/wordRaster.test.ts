import { describe, expect, it } from "vitest";

import { sampleMask, textMask, wordPoints, type Mask } from "./wordRaster";

// A 5x7 stroke font, only the letters DOTBOT needs. The browser's own text
// rendering is what the page uses; this stands in for it so the sampling and
// the budget can be exercised without a canvas.
const GLYPHS: Record<string, string[]> = {
  D: ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
  O: ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
  T: ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
  B: ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
};

/** The word as a mask, one font pixel blown up to `scale` mask pixels. */
function wordMask(text: string, scale = 8): Mask {
  const rows = 7;
  const columns = text.length * 6 - 1;
  const width = columns * scale;
  const height = rows * scale;
  const ink = new Uint8Array(width * height);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const column = Math.floor(x / scale);
      const letter = GLYPHS[text[Math.floor(column / 6)]];
      const inLetter = column % 6;
      if (letter === undefined || inLetter === 5) continue;
      if (letter[Math.floor(y / scale)][inLetter] === "1") ink[y * width + x] = 1;
    }
  }
  return { width, height, ink };
}

/** The closest two points in the set, mm. */
function closest(points: Float64Array): number {
  let best = Infinity;
  for (let i = 0; i < points.length; i += 2) {
    for (let j = i + 2; j < points.length; j += 2) {
      best = Math.min(best, Math.hypot(points[i] - points[j], points[i + 1] - points[j + 1]));
    }
  }
  return best;
}

const ARENA = 6000;
const SPACING = 160;

describe("sampleMask", () => {
  it("takes one point per grid cell that is inked enough", () => {
    const mask: Mask = { width: 4, height: 4, ink: Uint8Array.from([
      1, 1, 0, 0,
      1, 1, 0, 0,
      0, 0, 0, 0,
      0, 0, 0, 0,
    ]) };
    const points = sampleMask(mask, 2);
    expect([...points]).toEqual([1, 1]);
  });

  it("finds nothing in an empty mask", () => {
    expect(sampleMask({ width: 0, height: 0, ink: new Uint8Array(0) }, 2).length).toBe(0);
  });
});

describe("wordPoints", () => {
  const mask = wordMask("DOTBOT");

  it("spells DOTBOT with a point per bot, inside the budget", () => {
    const points = wordPoints(mask, {
      budget: 200,
      heightMm: 700,
      arenaW: ARENA,
      arenaH: ARENA,
      minSpacingMm: SPACING,
    });
    const count = points.length >> 1;
    expect(count).toBeGreaterThan(20);
    expect(count).toBeLessThanOrEqual(200);
  });

  it("widens the grid until a small fleet can hold the word", () => {
    const roomy = wordPoints(mask, {
      budget: 200,
      heightMm: 700,
      arenaW: ARENA,
      arenaH: ARENA,
      minSpacingMm: SPACING,
    });
    const tight = wordPoints(mask, {
      budget: 20,
      heightMm: 700,
      arenaW: ARENA,
      arenaH: ARENA,
      minSpacingMm: SPACING,
    });
    expect(tight.length >> 1).toBeLessThanOrEqual(20);
    expect(tight.length).toBeLessThan(roomy.length);
    expect(closest(tight)).toBeGreaterThan(closest(roomy));
  });

  it("never aims two bots closer than the spacing floor", () => {
    const points = wordPoints(mask, {
      budget: 400,
      heightMm: 700,
      arenaW: ARENA,
      arenaH: ARENA,
      minSpacingMm: SPACING,
    });
    expect(closest(points)).toBeGreaterThanOrEqual(SPACING * 0.99);
  });

  it("centres the word and keeps it inside the margin", () => {
    const points = wordPoints(mask, {
      budget: 400,
      heightMm: 900,
      arenaW: ARENA,
      arenaH: ARENA,
      minSpacingMm: SPACING,
    });
    let minX = Infinity;
    let maxX = -Infinity;
    for (let i = 0; i < points.length; i += 2) {
      minX = Math.min(minX, points[i]);
      maxX = Math.max(maxX, points[i]);
      expect(points[i + 1]).toBeGreaterThan(150);
      expect(points[i + 1]).toBeLessThan(ARENA - 150);
    }
    // The grid starts at the mask's edge, so the sampled word sits within a
    // cell of centred rather than exactly on the middle.
    expect(Math.abs((minX + maxX) / 2 - ARENA / 2)).toBeLessThan(SPACING);
  });

  // A 2 m room cannot hold a six-letter word at two footprints of spacing, so
  // the word gets coarser rather than the call failing.
  it("degrades a word that does not fit the room rather than dropping it", () => {
    const points = wordPoints(mask, {
      budget: 400,
      heightMm: 700,
      arenaW: 2000,
      arenaH: 2000,
      minSpacingMm: SPACING,
    });
    expect(points.length >> 1).toBeGreaterThan(0);
    expect(points.length >> 1).toBeLessThan(30);
  });

  it("spells nothing when there is no fleet to spell with", () => {
    expect(
      wordPoints(mask, {
        budget: 0,
        heightMm: 700,
        arenaW: ARENA,
        arenaH: ARENA,
        minSpacingMm: SPACING,
      }).length,
    ).toBe(0);
  });
});

describe("textMask", () => {
  it("reports no mask where there is no canvas to draw one on", () => {
    expect(textMask("DOT")).toBeNull();
  });
});
