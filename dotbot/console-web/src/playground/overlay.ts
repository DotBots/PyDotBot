import type { OutMessage, OverlayColor, OverlayItem, Vec2 } from "./types";

// What a script publishes on its /out topic, validated into what the canvas
// can draw. A script is not trusted to be well formed: an item the renderer
// does not know, or one missing a coordinate, is dropped and the rest is kept.

const COLORS: OverlayColor[] = ["accent", "muted", "good", "warn", "info"];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function num(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function color(raw: unknown): OverlayColor | undefined {
  return COLORS.includes(raw as OverlayColor) ? (raw as OverlayColor) : undefined;
}

function points(raw: unknown): Vec2[] | null {
  if (!Array.isArray(raw)) return null;
  const out: Vec2[] = [];
  for (const p of raw) {
    if (!isRecord(p)) return null;
    const x = num(p.x);
    const y = num(p.y);
    if (x === null || y === null) return null;
    out.push({ x, y });
  }
  return out;
}

function parseItem(raw: unknown): OverlayItem | null {
  if (!isRecord(raw)) return null;
  const c = color(raw.color);
  switch (raw.type) {
    case "point": {
      const x = num(raw.x);
      const y = num(raw.y);
      if (x === null || y === null) return null;
      const r = num(raw.r);
      return {
        type: "point",
        x,
        y,
        ...(r !== null ? { r } : {}),
        ...(typeof raw.label === "string" ? { label: raw.label } : {}),
        ...(c ? { color: c } : {}),
      };
    }
    case "polyline": {
      const pts = points(raw.points);
      if (pts === null || pts.length < 2) return null;
      return {
        type: "polyline",
        points: pts,
        ...(raw.closed === true ? { closed: true } : {}),
        ...(c ? { color: c } : {}),
      };
    }
    case "rect": {
      const x = num(raw.x);
      const y = num(raw.y);
      const w = num(raw.w);
      const h = num(raw.h);
      if (x === null || y === null || w === null || h === null) return null;
      return {
        type: "rect",
        x,
        y,
        w,
        h,
        ...(typeof raw.label === "string" ? { label: raw.label } : {}),
        ...(raw.fill === true ? { fill: true } : {}),
        ...(c ? { color: c } : {}),
      };
    }
    case "label": {
      const x = num(raw.x);
      const y = num(raw.y);
      if (x === null || y === null || typeof raw.text !== "string") return null;
      return { type: "label", x, y, text: raw.text, ...(c ? { color: c } : {}) };
    }
    case "badge": {
      if (typeof raw.address !== "string" || typeof raw.text !== "string") return null;
      return { type: "badge", address: raw.address, text: raw.text, ...(c ? { color: c } : {}) };
    }
    default:
      return null;
  }
}

/** Every drawable item in a list, dropping the ones the renderer cannot draw. */
export function parseOverlayItems(raw: unknown): OverlayItem[] {
  if (!Array.isArray(raw)) return [];
  return raw.map(parseItem).filter((i): i is OverlayItem => i !== null);
}

/**
 * One message off an app's /out topic, or null when it carries nothing the
 * page shows. An overlay replaces the previous one wholesale, so an empty
 * item list is how a script clears what it drew.
 */
export function parseOut(payload: unknown): OutMessage | null {
  if (!isRecord(payload)) return null;
  if (payload.kind === "overlay") {
    return { kind: "overlay", items: parseOverlayItems(payload.items) };
  }
  if (payload.kind === "status" && typeof payload.text === "string") {
    return { kind: "status", text: payload.text };
  }
  return null;
}
