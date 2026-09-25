import { describe, expect, it } from "vitest";

import { describePoint, heldAmong, heldWaypoints } from "./heldWaypoints";
import type { MissionReport, UnifiedBot, Waypoint } from "./types";

const bot = (id: string, waypoints: Waypoint[], extra: Partial<UnifiedBot> = {}) =>
  ({ id, waypoints, nav: "drive", mission: null, ...extra }) as UnifiedBot;
const report = (state: MissionReport["state"], index: number | null = null, reason: string | null = null) => ({
  state,
  index,
  reason,
  code: null,
});
const start = { x: 0, y: 0 };

describe("heldWaypoints", () => {
  const bots = [
    bot("C", [start, { x: 1, y: 1 }], { mission: report("arrived", 1) }),
    bot("A", [start]), // what a stop leaves behind: nothing held
    bot("B", [start, { x: 1, y: 1 }, { x: 2, y: 2 }], { nav: "auto", mission: report("in_progress", 1) }),
    bot("D", [start, { x: 3, y: 3 }], { mission: report("failed", 0, "could not turn") }),
    bot("E", []),
  ];

  it("lists each robot holding a batch, under way first, without its start", () => {
    const rows = heldWaypoints(bots);
    expect(rows.map((r) => r.id)).toEqual(["B", "C", "D"]);
    expect(rows[0]).toMatchObject({ targets: [{ x: 1, y: 1 }, { x: 2, y: 2 }], active: true, status: "to 2 of 2", tone: "run" });
    expect(rows[1]).toMatchObject({ status: "arrived", tone: "ok" });
    expect(rows[2]).toMatchObject({ status: "failed: could not turn", tone: "err" });
  });

  it("reads a robot under way that sends no report, and one that finished without a word", () => {
    const rows = heldWaypoints([bot("A", [start, start], { nav: "auto" }), bot("B", [start, start])]);
    expect(rows.map((r) => r.status)).toEqual(["under way", "done"]);
  });

  it("picks the rows of a selection", () => {
    expect(heldAmong(heldWaypoints(bots), new Set(["D", "A"])).map((r) => r.id)).toEqual(["D"]);
  });
});

describe("describePoint", () => {
  it("prints a position, and a pose with its heading", () => {
    expect(describePoint({ x: 10.4, y: 20.6 })).toBe("10, 21");
    expect(describePoint({ x: 10, y: 20, heading_deg: 89.6 })).toBe("10, 20 @ 90°");
  });
});
