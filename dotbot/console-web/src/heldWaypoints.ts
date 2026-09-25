import { UnifiedBot, Waypoint, lastMissionTargets } from "./types";

// Every robot's waypoint batch as the controller holds it. The controller
// keeps a batch after the robot finishes it, so a row is either under way or
// the robot's last word on it.

export interface HeldRow {
  id: string;
  targets: Waypoint[];
  active: boolean;
  status: string;
  tone: "run" | "ok" | "err" | "idle";
}

function statusOf(b: UnifiedBot, n: number): Pick<HeldRow, "status" | "tone"> {
  const m = b.mission;
  if (b.nav === "auto") {
    const at = m?.state === "in_progress" && m.index !== null ? Math.min(m.index + 1, n) : null;
    return { status: at === null ? "under way" : `to ${at} of ${n}`, tone: "run" };
  }
  if (m?.state === "arrived") return { status: "arrived", tone: "ok" };
  if (m?.state === "failed" || m?.state === "aborted")
    return { status: m.reason ? `${m.state}: ${m.reason}` : m.state, tone: "err" };
  return { status: "done", tone: "idle" };
}

/** The robots holding a batch, under way first. */
export function heldWaypoints(bots: UnifiedBot[]): HeldRow[] {
  return bots
    .map((b) => {
      const targets = lastMissionTargets(b);
      return targets.length ? { id: b.id, targets, active: b.nav === "auto", ...statusOf(b, targets.length) } : null;
    })
    .filter((r): r is HeldRow => r !== null)
    .sort((a, b) => Number(b.active) - Number(a.active) || a.id.localeCompare(b.id));
}

/** The rows among `ids`. */
export const heldAmong = (rows: HeldRow[], ids: Set<string>) => rows.filter((r) => ids.has(r.id));

/** One point as the list prints it. */
export function describePoint(w: Waypoint): string {
  const at = `${Math.round(w.x)}, ${Math.round(w.y)}`;
  return w.heading_deg === undefined || w.heading_deg === null ? at : `${at} @ ${Math.round(w.heading_deg)}°`;
}
