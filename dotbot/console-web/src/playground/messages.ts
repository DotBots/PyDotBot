import type { Goal, RectShape, Vec2 } from "./types";

// The page's half of the /in wire format. One module so the shapes a script
// parses are stated once; the helper's parse_input reads exactly these.

export function pointerMessage(at: Vec2 | null): Record<string, unknown> {
  return { kind: "pointer", at: at === null ? null : { x: at.x, y: at.y } };
}

export function goalsMessage(goals: Goal[]): Record<string, unknown> {
  return { kind: "goals", points: goals.map((g) => ({ x: g.x, y: g.y })) };
}

export function rectsMessage(rects: RectShape[]): Record<string, unknown> {
  return {
    kind: "rects",
    rects: rects.map((r) => ({ x: r.x, y: r.y, w: r.w, h: r.h })),
  };
}

export function textMessage(text: string): Record<string, unknown> {
  return { kind: "text", text };
}

export function controlMessage(
  id: string,
  value: number | boolean | string,
): Record<string, unknown> {
  return { kind: "control", id, value };
}

/** A button press. It carries no value, so it is its own kind. */
export function actionMessage(id: string): Record<string, unknown> {
  return { kind: "action", id };
}
