import type { Points } from "./assign";

// A word as a set of arena points, one per bot. The mask comes from the
// browser's own text rendering, which is why this runs on the page's thread
// rather than in the world's worker; everything after the mask is pure, and
// mirrors `common/raster.py` so both worlds spell a word the same way.

/** The ink of one word, row-major, one byte per pixel. */
export interface Mask {
  width: number;
  height: number;
  ink: Uint8Array;
}

/** Pixel height the word is rendered at before it is sampled. */
export const RENDER_PX = 240;

/** A cell counts as ink when this fraction of it is covered. */
export const COVERAGE = 0.32;

/** Ink cells of a `stepPx` grid, as x, y pixel centres. */
export function sampleMask(mask: Mask, stepPx: number): Points {
  const { width, height, ink } = mask;
  if (width === 0 || height === 0 || stepPx <= 0) return new Float64Array(0);
  const step = Math.max(1, stepPx);
  const out: number[] = [];
  for (let y = 0; y < height; y += step) {
    const y0 = Math.floor(y);
    const y1 = Math.min(height, Math.floor(y + step));
    for (let x = 0; x < width; x += step) {
      const x0 = Math.floor(x);
      const x1 = Math.min(width, Math.floor(x + step));
      let lit = 0;
      let cells = 0;
      for (let cy = y0; cy < y1; cy++) {
        for (let cx = x0; cx < x1; cx++) {
          cells++;
          if (ink[cy * width + cx]) lit++;
        }
      }
      // The nominal centre, not the clipped one: a cell cut short at the edge
      // would otherwise sit closer than `step` to its neighbour.
      if (cells > 0 && lit / cells >= COVERAGE) out.push(x + step / 2, y + step / 2);
    }
  }
  return Float64Array.from(out);
}

export interface WordOptions {
  /** How many points the fleet can hold. */
  budget: number;
  heightMm: number;
  arenaW: number;
  arenaH: number;
  /** Closest two points are ever placed. */
  minSpacingMm: number;
  marginMm?: number;
}

/**
 * Up to `budget` arena points spelling the mask, centred in the arena.
 *
 * The word is scaled to `heightMm`, or to whatever fits the arena if that is
 * smaller. Spacing starts at `minSpacingMm` and widens until the point count
 * is inside the budget, so bots never end up closer than the caller's floor
 * whatever the word.
 */
export function wordPoints(mask: Mask, opts: WordOptions): Points {
  const margin = opts.marginMm ?? 150;
  if (mask.width === 0 || mask.height === 0 || opts.budget <= 0) return new Float64Array(0);

  let mmPerPx = opts.heightMm / mask.height;
  const widest = opts.arenaW - 2 * margin;
  if (mask.width * mmPerPx > widest) mmPerPx = widest / mask.width;
  const tallest = opts.arenaH - 2 * margin;
  if (mask.height * mmPerPx > tallest) mmPerPx = tallest / mask.height;

  let spacing = Math.max(opts.minSpacingMm, 1e-6);
  let points = sampleMask(mask, spacing / mmPerPx);
  // Widening the grid drops points roughly as the square of the step, so a
  // 12% step per try converges in a handful of rounds even from far over.
  for (let i = 0; i < 60 && points.length >> 1 > opts.budget; i++) {
    spacing *= 1.12;
    points = sampleMask(mask, spacing / mmPerPx);
  }
  if (points.length >> 1 > opts.budget) points = points.slice(0, opts.budget * 2);

  const originX = opts.arenaW / 2 - (mask.width * mmPerPx) / 2;
  const originY = opts.arenaH / 2 - (mask.height * mmPerPx) / 2;
  for (let i = 0; i < points.length; i += 2) {
    points[i] = points[i] * mmPerPx + originX;
    points[i + 1] = points[i + 1] * mmPerPx + originY;
  }
  return points;
}

function context(width: number, height: number): CanvasRenderingContext2D | null {
  if (typeof document === "undefined") return null;
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.ceil(width));
  canvas.height = Math.max(1, Math.ceil(height));
  return canvas.getContext("2d", { willReadFrequently: true });
}

/**
 * The word as an ink mask cropped to its own bounding box, drawn once on an
 * offscreen canvas. Null when there is no canvas or the word left no ink.
 */
export function textMask(text: string, heightPx = RENDER_PX): Mask | null {
  const word = text.trim();
  if (word === "") return null;
  const font = `700 ${heightPx}px sans-serif`;
  const probe = context(8, 8);
  if (probe === null) return null;
  probe.font = font;
  const width = Math.ceil(probe.measureText(word).width) + 8;
  const height = Math.ceil(heightPx * 1.8);

  const ctx = context(width, height);
  if (ctx === null) return null;
  ctx.font = font;
  ctx.textBaseline = "alphabetic";
  ctx.fillStyle = "#fff";
  ctx.fillText(word, 4, Math.round(heightPx * 1.3));

  const pixels = ctx.getImageData(0, 0, ctx.canvas.width, ctx.canvas.height).data;
  let left = ctx.canvas.width;
  let right = -1;
  let top = ctx.canvas.height;
  let bottom = -1;
  for (let y = 0; y < ctx.canvas.height; y++) {
    for (let x = 0; x < ctx.canvas.width; x++) {
      if (pixels[(y * ctx.canvas.width + x) * 4 + 3] <= 127) continue;
      if (x < left) left = x;
      if (x > right) right = x;
      if (y < top) top = y;
      if (y > bottom) bottom = y;
    }
  }
  if (right < left || bottom < top) return null;

  const w = right - left + 1;
  const h = bottom - top + 1;
  const ink = new Uint8Array(w * h);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      ink[y * w + x] = pixels[((y + top) * ctx.canvas.width + (x + left)) * 4 + 3] > 127 ? 1 : 0;
    }
  }
  return { width: w, height: h, ink };
}

/** The whole path: render the word, sample it, place it in the arena. */
export function rasterWord(text: string, opts: WordOptions): Points {
  const mask = textMask(text);
  return mask === null ? new Float64Array(0) : wordPoints(mask, opts);
}
