import { describe, expect, it } from "vitest";

import type { UnifiedBot } from "../types";
import { goals, verdict, type GoalInputs } from "./checks";
import { docFromSite } from "./model";
import type { LibraryRow } from "./types";

const SERVED = {
  id: "4640cfde014c7232",
  id8: "4640cfde",
  tag: "r3",
  spin: "s1",
  in_frame: true,
  served: true,
  reading: "S0 and S1 share one box",
  stations: [
    { index: 0, residual_mm: 1.1, box: [0, 0, 1060, 1220], solved_from: "conics-joint" },
    { index: 1, residual_mm: 1.13, box: [0, 0, 1060, 1220], solved_from: "conics-joint" },
  ],
} as unknown as LibraryRow;

const bot = (id: string, held?: string) =>
  ({ id, state: "Running", position: { x: 300, y: 400 }, swarmit: held === undefined ? null : { info: { info_version: 4, lh2_station_mask: 3, lh2_calibration_id: held } } }) as unknown as UnifiedBot;

const inputs = (robots: UnifiedBot[]): GoalInputs => ({
  doc: docFromSite({ anchor: "the door", extent_mm: [1060, 1220], areas: [{ name: "field", x: 0, y: 0, w: 1060, h: 1220 }] }),
  served: SERVED,
  servedId: SERVED.id,
  rows: [SERVED],
  coverage: { id: SERVED.id, limit_mm: 2, geometry: { stations: {}, apart_mm: {} }, links: [], fog: null, next: [], headline: { worst_mm: 1.49, at: [1050, 50], bound: true, fused_worst_mm: 0.98, cells: 132, cells_over_limit: 0, cell_mm: 100, per_station: {} } },
  robots,
  live: true,
  problems: [],
  checks: [],
  frameChangeOpen: false,
});

describe("the ready verdict", () => {
  it("counts a robot that does not report its calibration as an unknown, never as a pass", () => {
    const v = verdict(goals(inputs([bot("A1"), bot("B2"), bot("C3")])));
    expect(v.state).toBe("ready");
    expect(v.unknown).toBe(1);
    expect(v.title).toBe("Ready to run · 1 unknown");
    const held = goals(inputs([bot("A1")])).find((g) => g.id === "held")!;
    expect(held.state).toBe("unknown");
  });

  it("is ready with no unknown once every robot reports the served id", () => {
    const v = verdict(goals(inputs([bot("A1", SERVED.id), bot("B2", SERVED.id)])));
    expect(v.title).toBe("Ready to run");
  });

  it("is not ready when a robot holds another calibration or the error passes the limit", () => {
    expect(verdict(goals(inputs([bot("A1", "a1b41f12aaaa0000")]))).state).toBe("not-ready");
    const over = inputs([bot("A1", SERVED.id)]);
    over.coverage!.headline!.worst_mm = 2.5;
    expect(verdict(goals(over)).title).toBe("Not ready · 1 to fix");
  });
});
