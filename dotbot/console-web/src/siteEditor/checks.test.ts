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
  reading: "S0 and S1 share one coverage: the coverages do not decide",
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

const sub = (i: GoalInputs, id: string) => goal(i, "stations").subs!.find((x) => x.id === id)!;

describe("the rows", () => {
  it("come in the operator's order, each naming its subject, with a button only when something needs doing", () => {
    const all = goals(inputs([bot("A1", SERVED.id)]));
    expect(all.map((g) => g.id)).toEqual(["floor", "stations", "anchor", "areas", "walls", "objects", "robots"]);
    for (const g of all) expect(g.subject.length, g.id).toBeGreaterThan(0);
    expect(goal(inputs([bot("A1", SERVED.id)]), "floor").action).toBeUndefined();
    expect(goal(inputs([bot("A1", SERVED.id)]), "robots").action).toBeUndefined();
    // Only the Anchor flow, which asks for a robot on the floor first, reads as more to come
    for (const g of all) if (g.action && g.id !== "anchor") expect(g.action.label, g.id).not.toMatch(/…/);
  });

  it("asks for the floor's size only when it is missing", () => {
    const none = inputs([], { doc: docFromSite({ anchor: null, extent_mm: null, areas: [] }) });
    expect(goal(none, "floor")).toMatchObject({ state: "fail", action: { label: "Set the size" } });
  });

  it("counts a robot that cannot say which calibration it has as unknown, never as a pass", () => {
    expect(goal(inputs([bot("A1")]), "robots")).toMatchObject({ state: "unknown", detail: "1 on the floor · cannot tell which calibration they have (no device info)" });
    expect(verdict(goals(inputs([bot("A1"), bot("B2"), bot("C3")]))).unknown).toBeGreaterThan(0);
  });

  it("offers Push to robots when a robot has another calibration, and says all have it otherwise", () => {
    const other = goal(inputs([bot("A1", "a1b41f12aaaa0000"), bot("B2", SERVED.id)]), "robots");
    expect(other.state).toBe("warn");
    expect(other.action).toEqual({ label: "Push to robots", go: { push: true } });
    expect(goal(inputs([bot("A1", SERVED.id), bot("B2", SERVED.id)]), "robots")).toMatchObject({ state: "ok", detail: "2 of 2 in the field · all have r3" });
  });

  it("reads coverage as a sub-line of Stations, with a split offered only when both cover everything", () => {
    expect(sub(inputs([]), "coverage")).toMatchObject({ state: "warn", action: { label: "Split at the best line" } });
    expect(goal(inputs([]), "stations").state).toBe("warn");
    expect(sub(inputs([], { served: HANDOVER }), "coverage")).toMatchObject({ state: "ok", text: "handover at x 530 mm" });
    expect(sub(inputs([], { served: HANDOVER }), "coverage").action).toBeUndefined();
  });

  it("describes the drafted coverage when it differs from the file in use", () => {
    const drawn = HANDOVER.stations.map((s) => ({ index: s.index, rect: s.box }));
    expect(sub(inputs([], { drawn }), "coverage")).toMatchObject({ state: "warn", text: "handover at x 530 mm · not in use yet (in use: both cover the whole extent)" });
    expect(sub(inputs([], { drawn }), "coverage").action).toBeUndefined();
  });

  it("states accuracy against the limit, with Show where only over it", () => {
    expect(sub(inputs([]), "accuracy")).toMatchObject({ state: "ok", text: "accurate within 1.5 mm everywhere (limit 2 mm)" });
    expect(sub(inputs([]), "accuracy").action).toBeUndefined();
    const over = inputs([], { served: HANDOVER });
    over.coverage!.headline!.worst_mm = 2.5;
    expect(sub(over, "accuracy")).toMatchObject({ state: "warn", text: "up to 2.5 mm off, over the 2 mm limit", action: { label: "Show where" } });
    expect(verdict(goals(over)).fails).toBe(0);
  });

  it("folds the field into Areas, and offers to draw one when none is", () => {
    expect(goal(inputs([]), "areas")).toMatchObject({ state: "ok", detail: "field 1060 × 1220" });
    const bare = inputs([], { doc: docFromSite({ anchor: null, extent_mm: [1060, 1220], areas: [{ name: "pen", x: 0, y: 0, w: 100, h: 100 }] }) });
    expect(goal(bare, "areas")).toMatchObject({ state: "warn", action: { label: "Draw the field", go: { kind: "areas", tool: "area" } } });
    expect(goal(bare, "areas").detail).toContain("no area is the field");
  });

  it("lists walls and objects, as optional when there are none", () => {
    expect(goal(inputs([]), "walls")).toMatchObject({ state: "none", detail: "none drawn: robots may go anywhere in the extent" });
    expect(goal(inputs([]), "objects").state).toBe("none");
    expect(verdict(goals(inputs([bot("A1", SERVED.id)]))).needs).toBe(2);
  });
});

describe("the Anchor row", () => {
  const check = (over: Partial<CheckRecord> = {}): CheckRecord => ({ calibration: SERVED.id, mark_mm: [300, 400], measured_mm: [301, 400], error_mm: 1, robot: "DE00000000000001", at: "2026-11-10T09:30:00Z", ...over });
  const anchored = (errors: number[]) => {
    const doc = docFromSite({ anchor: "the door", extent_mm: [1060, 1220], areas: [{ name: "field", x: 0, y: 0, w: 1060, h: 1220 }] });
    return { ...doc, anchor_spots: errors.map((e, i) => ({ at: [i * 100, 0] as [number, number], error_mm: e })) };
  };

  it("asks to anchor a map not tied to the floor, from a controller only", () => {
    expect(goal(inputs([]), "anchor")).toMatchObject({ state: "warn", action: { label: "Anchor with a robot…", go: { anchor: "anchor" } } });
    const standalone = goal(inputs([], { live: false }), "anchor");
    expect(standalone.action).toBeUndefined();
    expect(standalone.detail).toContain("open the editor from a controller");
  });

  it("says how many spots and the worst once anchored, and offers Check again", () => {
    expect(goal(inputs([], { doc: anchored([1.2, 4, 0.5, 2]) }), "anchor")).toMatchObject({ state: "ok", detail: "anchored on 4 spots, worst 4.0 mm", action: { label: "Check again", go: { anchor: "check" } } });
    expect(goal(inputs([], { doc: anchored([0, 0]) }), "anchor").detail).toBe("anchored on 2 spots, no error check");
  });

  it("says when the draft holds the anchoring, with nothing to press but Save", () => {
    const g = goal(inputs([], { doc: anchored([1, 2, 3]), anchorDrafted: true }), "anchor");
    expect(g).toMatchObject({ state: "warn", detail: "anchored on 3 spots, worst 3.0 mm · in the draft: Save writes it" });
    expect(g.action).toBeUndefined();
  });

  it("turns amber when a check again is far off or unverified", () => {
    const far = goal(inputs([], { doc: anchored([1, 1, 1]), checks: [check({ error_mm: 14 })] }), "anchor");
    expect(far.state).toBe("warn");
    expect(far.detail).toContain("checked again 10 Nov 09:30: 14.0 mm off, re-anchor");
    expect(goal(inputs([], { doc: anchored([1, 1, 1]), checks: [check({ assumed: true })] }), "anchor")).toMatchObject({ state: "warn" });
    expect(goal(inputs([], { doc: anchored([1, 1, 1]), checks: [check()] }), "anchor").state).toBe("ok");
  });

  it("is unknown, not a warning, before a calibration is in use", () => {
    const i = inputs([], { served: null, servedId: null, coverage: null, rows: [{ ...SERVED, served: false } as LibraryRow] });
    expect(goal(i, "anchor")).toMatchObject({ state: "unknown" });
    expect(goal(i, "anchor").action).toBeUndefined();
  });
});

describe("with nothing in use", () => {
  const FREE = { ...SERVED, id: "6e13c58faad5d3f7", id8: "6e13c58f", in_frame: false, served: false, free: true } as LibraryRow;
  const IN_FRAME = { ...SERVED, served: false } as LibraryRow;
  const unserved = (rows: LibraryRow[]): GoalInputs => inputs([bot("A1")], { served: null, servedId: null, rows, coverage: null });

  it("the Stations row leads to choosing, placing or setting up the room", () => {
    expect(goal(unserved([FREE, IN_FRAME]), "stations")).toMatchObject({ state: "warn", detail: "1 measured for this site, none in use", action: { label: "Choose one", go: { tab: "library" } } });
    expect(goal(unserved([]), "stations").action).toEqual({ label: "Set up the site", go: { sheet: "newroom" } });
    expect(goal(unserved([FREE]), "stations").action).toEqual({ label: "Place the spin in the site", go: { sheet: "newroom" } });
  });
});

describe("what the extent leaves outside", () => {
  it("is a warning on the Extent check, naming the coverage and the measured spots", () => {
    const doc = docFromSite({ anchor: "the door", extent_mm: [900, 1220], areas: [{ name: "field", x: 0, y: 0, w: 1060, h: 1220 }] });
    const g = goals(inputs([], { doc, spins: [[100, 100], [1000, 600]] })).find((x) => x.id === "floor")!;
    expect(g.state).toBe("warn");
    expect(g.subs![0].text).toBe("outside the extent: area field, S0 and S1's coverage, 1 measured spot; robots there drop their positions");
  });

  it("stays ok when everything is inside", () => {
    const g = goals(inputs([], { spins: [[100, 100]] })).find((x) => x.id === "floor")!;
    expect(g.state).toBe("ok");
    expect(g.subs).toBeUndefined();
  });
});
