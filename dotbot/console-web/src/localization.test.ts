import { describe, expect, it } from "vitest";

import {
  areasShownLabel,
  calibrationCoverage,
  coverageLabel,
  extentLabel,
  minimapLabel,
  minimapLines,
  stationRows,
  stationsSummary,
} from "./localization";
import type { Area, CalibrationSession, Site, SwarmitNode, UnifiedBot } from "./types";

const ARENA: Area = { x: 0, y: 0, w: 2000, h: 2000, name: "arena" };
const ANNEX: Area = { x: 0, y: 2000, w: 2000, h: 2000, name: "annex" };
const DEV: Area = { x: 1000, y: 0, w: 1000, h: 1000, name: "dev-corner" };

const C405: Site = {
  name: "c405-arena",
  anchor: "the arena's top-left corner, against the door wall of C405",
  extent_mm: [3330, 4000],
  areas: [ARENA, ANNEX, DEV],
};

const bot = (id: string, homographies?: number): UnifiedBot =>
  ({
    id,
    state: "Running",
    link: "active",
    position: null,
    heading: null,
    battery: 3.9,
    led: null,
    deviceType: "DotBotV3",
    application: 0,
    drivable: true,
    nav: "drive",
    waypoints: [],
    trail: [],
    image: null,
    resetCause: null,
    severity: "normal",
    batteryPct: null,
    batteryLevel: null,
    swarmit:
      homographies === undefined
        ? null
        : ({
            info: { lh2_homography_count: homographies },
          } as unknown as SwarmitNode),
  }) as UnifiedBot;

const session = (over: Partial<CalibrationSession> = {}): CalibrationSession => ({
  at: "arena:corners",
  site: "c405-arena",
  device: "",
  reads: 25,
  status: "collecting",
  outstanding: null,
  captured: 4,
  total: 4,
  expected_error_mm: null,
  points: [],
  stations: [],
  unsolved: [],
  saved_path: null,
  saved_id: "",
  error: "",
  ...over,
});

describe("the site line", () => {
  it("states the extent in millimetres", () => {
    expect(extentLabel(C405)).toBe("3330 x 4000 mm");
  });

  it("says so rather than inventing a floor nobody measured", () => {
    expect(extentLabel({ ...C405, extent_mm: null })).toBe("not measured");
    expect(extentLabel(null)).toBe("not measured");
  });
});

describe("the areas shown", () => {
  it("names them in the order the controller sends", () => {
    expect(areasShownLabel([ARENA, DEV])).toBe("arena, dev-corner");
  });

  it("says the whole site when none is shown", () => {
    expect(areasShownLabel([])).toBe("the whole site");
  });

  it("ignores a literal rectangle's absent name", () => {
    expect(areasShownLabel([{ x: 0, y: 0, w: 100, h: 100 }])).toBe("the whole site");
  });
});

describe("the footer minimap label", () => {
  it("splits in two for a column too narrow for one line", () => {
    expect(minimapLines(C405, [ARENA])).toEqual([
      "SITE c405-arena · 3330 x 4000 mm",
      "showing arena",
    ]);
  });

  it("names the site, its extent and what is shown", () => {
    expect(minimapLabel(C405, [ARENA, DEV])).toBe(
      "SITE c405-arena · 3330 x 4000 mm · showing arena, dev-corner",
    );
  });

  it("stays honest before the controller answers", () => {
    expect(minimapLabel(null, [])).toBe(
      "SITE unknown · not measured · showing the whole site",
    );
  });
});

describe("what the fleet carries", () => {
  it("cannot name the id, because today's firmware does not report one", () => {
    // The bitmask says how many matrices a robot holds, not which
    // calibration; the panel says "unknown" rather than showing a guess.
    const coverage = calibrationCoverage([bot("a", 2), bot("b", 2)], 2);
    expect(coverage.unknown).toBe(true);
    expect(coverage.id).toBe("");
  });

  it("lists the robots missing a matrix as the worklist a push acts on", () => {
    const coverage = calibrationCoverage(
      [bot("aaaa", 2), bot("bbbb", 1), bot("cccc")],
      2,
    );
    expect(coverage.carrying).toBe(1);
    expect(coverage.total).toBe(3);
    expect(coverage.stale).toEqual(["bbbb", "cccc"]);
  });

  it("calls nobody stale while no calibration is solved", () => {
    // With nothing solved there is nothing to be missing, so the panel does
    // not offer a push worklist that is the whole fleet.
    const coverage = calibrationCoverage([bot("aaaa", 2)], 0);
    expect(coverage.carrying).toBe(0);
    expect(coverage.stale).toEqual([]);
  });

  it("words the coverage, and the empty fleet", () => {
    expect(coverageLabel(calibrationCoverage([bot("a", 2), bot("b", 2)], 2))).toBe(
      "on 2 of 2 bots",
    );
    expect(coverageLabel(calibrationCoverage([], 2))).toBe(
      "no bots on the control plane",
    );
  });
});

describe("the station rows", () => {
  it("gives one row per solved station, with its residual", () => {
    const rows = stationRows(
      session({
        stations: [
          { index: 0, points: 4, residual_mm: 0, solved_from: "direct" },
          { index: 1, points: 8, residual_mm: 2.86, solved_from: "direct" },
        ],
      }),
    );
    expect(rows).toEqual([
      { index: 0, label: "4 points · residual 0.0 mm" },
      { index: 1, label: "8 points · residual 2.9 mm" },
    ]);
  });

  it("counts a station that was seen but not solved as seen", () => {
    expect(
      stationsSummary(
        session({
          stations: [{ index: 0, points: 4, residual_mm: 0, solved_from: "direct" }],
          unsolved: [{ index: 1, points: 2 }],
        }),
      ),
    ).toBe("2 seen · 1 solved");
  });

  it("has nothing to say with no session", () => {
    expect(stationRows(null)).toEqual([]);
    expect(stationsSummary(null)).toBe("no calibration loaded");
  });
});
