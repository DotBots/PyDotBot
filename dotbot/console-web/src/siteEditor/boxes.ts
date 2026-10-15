import type { Issue, Rect } from "./edit";
import type { CalibrationOverlay } from "./types";

// A calibration's station rectangles as the Station boxes tool edits them:
// x, y, w, h in frame mm, where the file keeps [x_min, y_min, x_max, y_max].
// The checks mirror dotbot/calibration/station_boxes.py, which has the last word.

/** One colour per station, in station order. */
export const STATION_COLOURS = ["var(--accent)", "var(--s-Running)", "var(--s-Programming)", "var(--s-Bootloader)"];

export type Corners = [number, number, number, number];

export function rectOf([x0, y0, x1, y1]: number[]): Rect {
  return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
}

export function cornersOf(r: Rect): Corners {
  return [r.x, r.y, r.x + r.w, r.y + r.h];
}

/** Each station's rectangle, in the overlay's station order. */
export function boxesOf(overlay: CalibrationOverlay): Rect[] {
  return overlay.stations.map((st) => rectOf(st.rect));
}

export function sameBoxes(a: Rect[], b: Rect[]): boolean {
  return JSON.stringify(a.map(cornersOf)) === JSON.stringify(b.map(cornersOf));
}

function label(st: { index: number; channel: number }): string {
  return `station ${st.index} (channel ${st.channel})`;
}

/** What stops a save (errors) and what is worth knowing (warnings). */
export function boxIssues(overlay: CalibrationOverlay, boxes: Rect[], extent: [number, number] | null): Issue[] {
  const issues: Issue[] = [];
  overlay.stations.forEach((st, k) => {
    const r = boxes[k];
    if (!r) return;
    const name = label(st);
    if (![r.x, r.y, r.w, r.h].every(Number.isFinite)) {
      issues.push({ level: "error", message: `${name}: x, y, w and h must be numbers` });
      return;
    }
    if (!(r.w > 0) || !(r.h > 0)) issues.push({ level: "error", message: `${name}'s rectangle is empty` });
    if (r.x < 0 || r.y < 0) {
      issues.push({ level: "error", message: `${name}'s rectangle reaches below zero, where a robot cannot report a position` });
    }
    if (extent && (r.x + r.w > extent[0] || r.y + r.h > extent[1])) {
      issues.push({ level: "error", message: `${name}'s rectangle reaches outside the site's extent` });
    }
    const out = st.circles.filter((c) => c.x < r.x || c.x > r.x + r.w || c.y < r.y || c.y > r.y + r.h);
    if (out.length > 0) {
      issues.push({
        level: "warning",
        message: `${name}'s rectangle leaves out ${out.length} of its ${st.circles.length} spin circle${st.circles.length === 1 ? "" : "s"}`,
      });
    }
  });
  return issues;
}
