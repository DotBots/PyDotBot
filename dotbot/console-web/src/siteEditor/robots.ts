import { firmwareTooOld, heldCalibrationId } from "../botFacts";
import type { UnifiedBot } from "../types";
import type { Doc } from "./model";
import { candidates } from "./stationRule";
import type { Rect } from "./types";

// What the editor says about one live robot. It reads the robot's fix and
// what swarmit reports; it never sends anything.

export type Held =
  | { kind: "served"; id8: string }
  | { kind: "other"; id8: string; site: string }
  | { kind: "none" }
  | { kind: "old-firmware" }
  | { kind: "not-reported" };

/** Which calibration a robot holds, as far as swarmit's device info says. */
export function heldBy(bot: UnifiedBot, servedId: string | null): Held {
  const info = bot.swarmit?.info;
  if (!info) return { kind: "not-reported" };
  if (firmwareTooOld(bot)) return { kind: "old-firmware" };
  const id = heldCalibrationId(bot);
  if (!id) return { kind: "none" };
  if (servedId && id.toLowerCase() === servedId.toLowerCase()) return { kind: "served", id8: id.slice(0, 8) };
  return { kind: "other", id8: id.slice(0, 8), site: info.lh2_site_name ?? "" };
}

export function heldText(h: Held): string {
  switch (h.kind) {
    case "served":
      return `holds ${h.id8}, the served calibration`;
    case "other":
      return `holds ${h.id8}${h.site ? ` (${h.site})` : ""}, not the served one`;
    case "none":
      return "holds no calibration";
    case "old-firmware":
      return "its firmware predates the held id: reflash to read it";
    default:
      return "not reported";
  }
}

/** The robot's last 4 hex digits, as its label shows them. */
export const tail = (id: string, n = 4) => id.slice(-n).toUpperCase();

export interface WhereItStands {
  area: string | null;
  inFloor: boolean;
  /** Stations whose box holds the sensor. */
  boxes: number[];
  /** Who gives the fix there when every station sees the robot. */
  fix: number[];
  /** Distance from the sensor to the floor's nearest edge, mm, and which. */
  edge: { mm: number; side: string } | null;
}

/** What applies at the robot's sensor: its area, the boxes, who gives the fix. */
export function whereItStands(doc: Doc, boxes: { index: number; rect: Rect }[], x: number, y: number): WhereItStands {
  const area = doc.areas.find((a) => x >= a.x && x <= a.x + a.w && y >= a.y && y <= a.y + a.h);
  const rects = Object.fromEntries(boxes.map((b) => [b.index, b.rect]));
  const ext = doc.extent_mm;
  let edge: WhereItStands["edge"] = null;
  if (ext) {
    const sides: [number, string][] = [
      [x, "left"],
      [ext[0] - x, "right"],
      [y, "top"],
      [ext[1] - y, "bottom"],
    ];
    const [mm, side] = sides.reduce((a, b) => (b[0] < a[0] ? b : a));
    edge = { mm: Math.round(mm), side };
  }
  return {
    area: area?.name ?? null,
    inFloor: !!ext && x >= 0 && y >= 0 && x <= ext[0] && y <= ext[1],
    boxes: boxes.filter((b) => x >= b.rect[0] && x <= b.rect[2] && y >= b.rect[1] && y <= b.rect[3]).map((b) => b.index),
    fix: boxes.length ? candidates(rects, x, y) : [],
    edge,
  };
}
