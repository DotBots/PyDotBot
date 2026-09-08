import type { Goal, RectShape, Vec2 } from "./types";

// What the map collects beyond the pointer: pins and rectangles. Pure, so the
// gesture handlers in Arena stay thin and every rule is testable without a
// canvas.

/** Tap radius around a pin, arena mm. About a bot and a half. */
export const GOAL_HIT_MM = 120;

/** How close to an edge counts as grabbing it, arena mm. */
export const RECT_EDGE_MM = 90;

/** A rectangle smaller than this in either axis is not worth keeping. */
export const RECT_MIN_MM = 120;

let nextId = 1;

/** Ids are page-local and only have to be distinct within one set. */
export function newId(): number {
  return nextId++;
}

/** The pin under a point, or -1. */
export function goalAt(goals: Goal[], p: Vec2, hitMm = GOAL_HIT_MM): number {
  let best = -1;
  let bestDistance = hitMm * hitMm;
  goals.forEach((g, i) => {
    const d = (g.x - p.x) ** 2 + (g.y - p.y) ** 2;
    if (d <= bestDistance) {
      best = i;
      bestDistance = d;
    }
  });
  return best;
}

/**
 * A tap on empty arena: one pin replaces the set, shift adds to it. A tap on
 * an existing pin removes it, which is `removeGoal`; the two are split so a
 * drag can start on a pin without the tap having already fired.
 */
export function addGoal(goals: Goal[], p: Vec2, additive: boolean): Goal[] {
  const pin: Goal = { id: newId(), x: p.x, y: p.y };
  return additive ? [...goals, pin] : [pin];
}

export function removeGoal(goals: Goal[], index: number): Goal[] {
  return goals.filter((_, i) => i !== index);
}

export function moveGoal(goals: Goal[], index: number, p: Vec2): Goal[] {
  return goals.map((g, i) => (i === index ? { ...g, x: p.x, y: p.y } : g));
}

/** A rectangle from two opposite corners, with a positive width and height. */
export function normalizeRect(a: Vec2, b: Vec2): { x: number; y: number; w: number; h: number } {
  return {
    x: Math.min(a.x, b.x),
    y: Math.min(a.y, b.y),
    w: Math.abs(a.x - b.x),
    h: Math.abs(a.y - b.y),
  };
}

/** Which part of a rectangle a point grabs. `inside` is the body, not an edge. */
export type RectHandle = "n" | "s" | "e" | "w" | "nw" | "ne" | "sw" | "se" | "inside";

/**
 * The rectangle under a point and what it grabs there, topmost first, or
 * index -1. An edge wins over the body so a resize is reachable on a
 * rectangle that fills the arena.
 */
export function rectHandleAt(
  rects: RectShape[],
  p: Vec2,
  edgeMm = RECT_EDGE_MM,
): { index: number; handle: RectHandle | null } {
  for (let i = rects.length - 1; i >= 0; i--) {
    const r = rects[i];
    const inX = p.x >= r.x - edgeMm && p.x <= r.x + r.w + edgeMm;
    const inY = p.y >= r.y - edgeMm && p.y <= r.y + r.h + edgeMm;
    if (!inX || !inY) continue;
    const west = Math.abs(p.x - r.x) <= edgeMm;
    const east = Math.abs(p.x - (r.x + r.w)) <= edgeMm;
    const north = Math.abs(p.y - r.y) <= edgeMm;
    const south = Math.abs(p.y - (r.y + r.h)) <= edgeMm;
    if (north && west) return { index: i, handle: "nw" };
    if (north && east) return { index: i, handle: "ne" };
    if (south && west) return { index: i, handle: "sw" };
    if (south && east) return { index: i, handle: "se" };
    if (north) return { index: i, handle: "n" };
    if (south) return { index: i, handle: "s" };
    if (west) return { index: i, handle: "w" };
    if (east) return { index: i, handle: "e" };
    if (p.x >= r.x && p.x <= r.x + r.w && p.y >= r.y && p.y <= r.y + r.h) {
      return { index: i, handle: "inside" };
    }
  }
  return { index: -1, handle: null };
}

/** The rectangle after one edge or corner is dragged to `p`. */
export function resizeRect(rect: RectShape, handle: RectHandle, p: Vec2): RectShape {
  if (handle === "inside") return rect;
  let { x, y, w, h } = rect;
  const right = x + w;
  const bottom = y + h;
  if (handle.includes("w")) {
    x = Math.min(p.x, right);
    w = right - x;
  }
  if (handle.includes("e")) {
    w = Math.max(0, p.x - x);
  }
  if (handle.includes("n")) {
    y = Math.min(p.y, bottom);
    h = bottom - y;
  }
  if (handle.includes("s")) {
    h = Math.max(0, p.y - y);
  }
  return { ...rect, x, y, w, h };
}

export function replaceRect(rects: RectShape[], index: number, rect: RectShape): RectShape[] {
  return rects.map((r, i) => (i === index ? rect : r));
}

export function removeRect(rects: RectShape[], index: number): RectShape[] {
  return rects.filter((_, i) => i !== index);
}

/** Rectangles worth keeping: a stray click while drawing leaves a sliver. */
export function pruneRects(rects: RectShape[], minMm = RECT_MIN_MM): RectShape[] {
  return rects.filter((r) => r.w >= minMm && r.h >= minMm);
}

/** What one press did, which is what decides what its release means. */
export interface Gesture {
  /** The pin or rectangle the press grabbed, or -1. */
  index: number;
  /** The press travelled further than the click slop. */
  moved: boolean;
  /** The press created what it is holding, rather than grabbing it. */
  created: boolean;
}

/**
 * The pins after a release. A click on an existing pin removes it; a click
 * that placed one keeps it, and so does any drag.
 */
export function endGoalGesture(goals: Goal[], gesture: Gesture): Goal[] {
  const clicked = !gesture.moved && !gesture.created && gesture.index >= 0;
  return clicked ? removeGoal(goals, gesture.index) : goals;
}

/** The rectangles after a release, on the same rule, minus any sliver. */
export function endRectGesture(
  rects: RectShape[],
  gesture: Gesture,
  minMm = RECT_MIN_MM,
): RectShape[] {
  const clicked = !gesture.moved && !gesture.created && gesture.index >= 0;
  return pruneRects(clicked ? removeRect(rects, gesture.index) : rects, minMm);
}
