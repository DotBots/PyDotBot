import { firmwareTooOld, heldCalibrationId } from "../botFacts";
import type { UnifiedBot } from "../types";

// What the console's push sheet says about each robot and about the push.

export interface PushRow {
  id: string;
  tail: string;
  state: string;
  /** "4640cfde", "none", "not reported" or "old firmware". */
  holds: string;
  /** Whether it already holds the calibration being pushed. */
  current: boolean;
  /** Running its app: it takes a push only once the app is stopped. */
  appStops: boolean;
}

export function pushRows(bots: UnifiedBot[], calibrationId: string): PushRow[] {
  return [...bots]
    .sort((a, b) => a.id.localeCompare(b.id))
    .map((b) => {
      const info = b.swarmit?.info;
      const held = info ? heldCalibrationId(b) : "";
      const holds = !info ? "not reported" : firmwareTooOld(b) ? "old firmware" : held ? held.slice(0, 8) : "none";
      return {
        id: b.id,
        tail: b.id.slice(-6).toUpperCase(),
        state: b.state ?? "unknown",
        holds,
        current: !!held && !!calibrationId && held.toLowerCase().startsWith(calibrationId.toLowerCase().slice(0, 8)),
        appStops: b.state === "Running",
      };
    });
}

/** The sheet's title: what it pushes and who in their app will not take it. */
export function pushTitle(id8: string, rows: PushRow[], ticked: ReadonlySet<string>): string {
  const stops = rows.filter((r) => ticked.has(r.id) && r.appStops).length;
  return stops ? `Push ${id8} · ${stops} robot${stops === 1 ? "" : "s"} in their app will not take it` : `Push ${id8}`;
}

/** The confirm button's words; empty while nothing is ticked. */
export function confirmLabel(rows: PushRow[], ticked: ReadonlySet<string>): string {
  const n = rows.filter((r) => ticked.has(r.id)).length;
  if (!n) return "";
  const stops = rows.filter((r) => ticked.has(r.id) && r.appStops).length;
  return stops ? `Send to ${n}; ${stops} in their app will not take it` : `Push to ${n} robot${n === 1 ? "" : "s"}`;
}

/** The same push from a terminal. */
export function pushTwin(id8: string, site: string, ticked: string[]): string {
  const devices = ticked.length ? ` -d ${[...ticked].sort().join(",")}` : "";
  return `dotbot swarm${devices} calibrate-lh2 push ${id8}${site ? ` --site ${site}` : ""}`;
}
