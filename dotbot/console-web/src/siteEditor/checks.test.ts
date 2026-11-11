import { describe, expect, it } from "vitest";

import type { UnifiedBot } from "../types";
import { goals, verdict, type CheckRecord, type GoalInputs } from "./checks";
import { docFromSite } from "./model";
import type { LibraryRow } from "./types";

const SERVED = {
  id: "4640cfde014c7232",
  id8: "4640cfde",
  tag: "r3",
  created_at: "2026-11-09T08:12:50Z",
  spin: "s1",
  in_frame: true,
  served: true,
  reading: "S0 and S1 share one box: the boxes do not decide",
  stations: [
    { index: 0, residual_mm: 1.1, box: [0, 0, 1060, 1220], solved_from: "conics-joint" },
    { index: 1, residual_mm: 1.13, box: [0, 0, 1060, 1220], solved_from: "conics-joint" },
  ],
} as unknown as LibraryRow;
const HANDOVER = { ...SERVED, reading: "S0 x 0-630, y 0-1220 · S1 x 430-1060, y 0-1220 · S0/S1 handover x 530", stations: [{ ...SERVED.stations[0], box: [0, 0, 630, 1220] }, { ...SERVED.stations[1], box: [430, 0, 1060, 1220] }] } as LibraryRow;

const bot = (id: string, held?: string) =>
  ({ id, state: "Running", position: { x: 300, y: 400 }, swarmit: held === undefined ? null : { info: { info_version: 4, lh2_station_mask: 3, lh2_calibration_id: held } } }) as unknown as UnifiedBot;

const inputs = (robots: UnifiedBot[], over: Partial<GoalInputs> = {}): GoalInputs => ({
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
  ...over,
});
const goal = (i: GoalInputs, id: string) => goals(i).find((g) => g.id === id)!;

describe("the rows", () => {
  it("each has one of three states and one action", () => {
    const all = goals(inputs([bot("A1", SERVED.id)]));
    expect(all.map((g) => g.id)).toEqual(["floor", "origin", "stations", "coverage", "accuracy", "field", "robots", "verified"]);
    for (const g of all) {
      expect(["ok", "warn", "fail", "unknown"]).toContain(g.state);
      expect(g.action, g.id).toBeTruthy();
    }
  });

  it("counts a robot that cannot say which calibration it has as unknown, never as a pass", () => {
    expect(goal(inputs([bot("A1")]), "robots")).toMatchObject({ state: "unknown", detail: "1 on the floor · cannot tell which calibration they have (no device info)" });
    expect(verdict(goals(inputs([bot("A1"), bot("B2"), bot("C3")]))).unknown).toBeGreaterThan(0);
  });

  it("points at Push when a robot has another calibration, and says all have it otherwise", () => {
    const other = goal(inputs([bot("A1", "a1b41f12aaaa0000"), bot("B2", SERVED.id)]), "robots");
    expect(other.state).toBe("warn");
    expect(other.detail).toContain("Push to robots, in the title bar");
    expect(other.action).toEqual({ label: "Show…", go: { tab: "outline" } });
    expect(goal(inputs([bot("A1", SERVED.id), bot("B2", SERVED.id)]), "robots")).toMatchObject({ state: "ok", detail: "2 of 2 in the field · all have r3" });
  });

  it("reads coverage as a handover, or asks for one when both stations cover everything", () => {
    expect(goal(inputs([]), "coverage")).toMatchObject({ state: "warn", action: { label: "Add a handover…" } });
    expect(goal(inputs([], { served: HANDOVER }), "coverage")).toMatchObject({ state: "ok", detail: "handover at x 530 mm" });
  });

  it("states accuracy against the limit", () => {
    expect(goal(inputs([]), "accuracy").detail).toBe("within 1.5 mm everywhere (limit 2 mm)");
    const over = inputs([]);
    over.coverage!.headline!.worst_mm = 2.5;
    expect(goal(over, "accuracy")).toMatchObject({ state: "warn", detail: "up to 2.5 mm, over the 2 mm limit" });
    expect(verdict(goals(over)).fails).toBe(0);
  });
});

describe("the origin and the verification", () => {
  const check = (over: Partial<CheckRecord> = {}): CheckRecord => ({ calibration: SERVED.id, mark_mm: [300, 400], measured_mm: [301, 400], error_mm: 1, robot: "DE00000000000001", at: "2026-11-10T09:30:00Z", ...over });

  it("turns green only on a check the robot vouched for", () => {
    expect(goal(inputs([], { checks: [check()] }), "origin")).toMatchObject({ state: "ok", detail: "verified with a robot on 10 Nov 09:30" });
    expect(goal(inputs([], { checks: [check({ assumed: true })] }), "origin")).toMatchObject({ state: "warn", detail: "verified assuming the robots had the calibration: not proven" });
    expect(goal(inputs([], { checks: [check({ assumed: true })] }), "verified").detail).toContain("assumed the robot had the calibration: unverified");
    expect(goal(inputs([], { checks: [check({ error_mm: 9 })] }), "origin").detail).toBe("the last check was off: check the tape, or move the origin");
  });

  it("is unknown, not a warning, before a calibration is in use", () => {
    const i = inputs([], { served: null, servedId: null, coverage: null, rows: [{ ...SERVED, served: false } as LibraryRow] });
    expect(goal(i, "origin")).toMatchObject({ state: "unknown", action: { label: "Describe…" } });
    expect(goal(i, "verified").state).toBe("unknown");
  });
});

describe("with nothing in use", () => {
  const FREE = { ...SERVED, id: "6e13c58faad5d3f7", id8: "6e13c58f", in_frame: false, served: false, free: true } as LibraryRow;
  const IN_FRAME = { ...SERVED, served: false } as LibraryRow;
  const unserved = (rows: LibraryRow[]): GoalInputs => inputs([bot("A1")], { served: null, servedId: null, rows, coverage: null });

  it("has one calibration row that leads to choosing, placing or measuring", () => {
    expect(goals(unserved([IN_FRAME])).filter((g) => g.id === "calibration" || g.id === "stations")).toHaveLength(1);
    expect(goal(unserved([FREE, IN_FRAME]), "calibration")).toMatchObject({ state: "warn", detail: "1 measured for this room, none in use", action: { label: "Choose…", go: { tab: "library" } } });
    expect(goal(unserved([]), "calibration").action).toEqual({ label: "Mount and measure…", go: { sheet: "newroom" } });
    expect(goal(unserved([FREE]), "calibration").action).toEqual({ label: "Put the spin in the room…", go: { sheet: "newroom" } });
    expect(verdict(goals(unserved([IN_FRAME]))).title).toBe("1 needs you");
  });
});
