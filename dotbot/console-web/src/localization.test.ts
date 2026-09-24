import { describe, expect, it } from "vitest";

import {
  calibrationCoverage,
  camerasSummary,
  cameraStatusRows,
  coverageLabel,
  extentLabel,
  minimapLabel,
  stationRows,
  stationsSummary,
} from "./localization";
import type {
  Area,
  CalibrationSession,
  CameraDetection,
  RegisteredCamera,
  Site,
  SwarmitNode,
  UnifiedBot,
} from "./types";

const ARENA: Area = { x: 0, y: 0, w: 2000, h: 2000, name: "arena" };
const ANNEX: Area = { x: 0, y: 2000, w: 2000, h: 2000, name: "annex" };
const DEV: Area = { x: 1000, y: 0, w: 1000, h: 1000, name: "dev-corner" };

const C405: Site = {
  name: "c405-arena",
  anchor: "the arena's top-left corner, against the door wall of C405",
  extent_mm: [3330, 4000],
  areas: [ARENA, ANNEX, DEV],
};

const bot = (id: string, calibrationId?: string): UnifiedBot =>
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
    pose: null,
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
      calibrationId === undefined
        ? null
        : ({
            info: { info_version: 2, lh2_calibration_id: calibrationId },
          } as unknown as SwarmitNode),
  }) as UnifiedBot;

const session = (over: Partial<CalibrationSession> = {}): CalibrationSession => ({
  at: "arena:corners",
  site: "c405-arena",
  area: "",
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

describe("the footer minimap label", () => {
  it("names the site and its extent", () => {
    expect(minimapLabel(C405)).toBe("SITE c405-arena · 3330 x 4000 mm");
  });

  it("stays honest before the controller answers", () => {
    expect(minimapLabel(null)).toBe("SITE unknown · not measured");
  });
});

const SAVED = "3f9a1c07e2b845d6";

describe("what the fleet carries", () => {
  it("compares the fleet against the saved calibration's id", () => {
    const coverage = calibrationCoverage([bot("a", SAVED), bot("b", SAVED)], SAVED);
    expect(coverage.unknown).toBe(false);
    expect(coverage.id).toBe(SAVED);
    expect(coverage.carrying).toBe(2);
  });

  it("lists the robots reporting another id, or none, as the worklist a push acts on", () => {
    const coverage = calibrationCoverage(
      [bot("aaaa", SAVED.toUpperCase()), bot("bbbb", "1111111111111111"), bot("cccc", ""), bot("dddd")],
      SAVED,
    );
    expect(coverage.carrying).toBe(1);
    expect(coverage.total).toBe(4);
    expect(coverage.stale).toEqual(["bbbb", "cccc"]);
    expect(coverage.unchecked).toEqual(["dddd"]);
  });

  it("keeps the robots whose device info cannot say off the worklist", () => {
    const old = { ...bot("eeee"), swarmit: { info: { info_version: 1 } } as unknown as SwarmitNode };
    const silent = { ...bot("ffff"), swarmit: { info: null } as unknown as SwarmitNode };
    const coverage = calibrationCoverage([bot("aaaa", "1111111111111111"), old, silent], SAVED);
    expect(coverage.stale).toEqual(["aaaa"]);
    expect(coverage.unchecked).toEqual(["eeee", "ffff"]);
  });

  it("calls nobody stale while nothing is saved", () => {
    // With no id to compare against, the panel does not offer a push
    // worklist that is the whole fleet.
    const coverage = calibrationCoverage([bot("aaaa", SAVED)], "");
    expect(coverage.unknown).toBe(true);
    expect(coverage.carrying).toBe(0);
    expect(coverage.stale).toEqual([]);
  });

  it("words the coverage, and the empty fleet", () => {
    expect(coverageLabel(calibrationCoverage([bot("a", SAVED), bot("b", SAVED)], SAVED))).toBe(
      "on 2 of 2 bots",
    );
    expect(coverageLabel(calibrationCoverage([], SAVED))).toBe(
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

const camera = (area: string) => ({ area }) as RegisteredCamera;
const detection = (
  area: string,
  status: CameraDetection["status"],
  robots = status === "none" ? 0 : 1,
) =>
  ({
    area,
    status,
    robots: Array.from({ length: robots }, () => ({ status })),
  }) as CameraDetection;

describe("the camera rows", () => {
  it("names each camera's area and what it last saw", () => {
    expect(
      cameraStatusRows([camera("dev-corner"), camera("arena")], {
        "dev-corner": detection("dev-corner", "found"),
      }),
    ).toEqual([
      { area: "dev-corner", label: "robot seen" },
      { area: "arena", label: "no frame yet" },
    ]);
  });

  it("tells a refused pose from an empty floor", () => {
    expect(
      cameraStatusRows([camera("a"), camera("b")], {
        a: detection("a", "refused"),
        b: detection("b", "none"),
      }),
    ).toEqual([
      { area: "a", label: "robot, low confidence" },
      { area: "b", label: "no robot" },
    ]);
  });

  it("counts the robots when there is more than one", () => {
    expect(
      cameraStatusRows([camera("a"), camera("b")], {
        a: detection("a", "found", 3),
        b: detection("b", "refused", 2),
      }),
    ).toEqual([
      { area: "a", label: "3 robots seen" },
      { area: "b", label: "2 robots, low confidence" },
    ]);
  });

  it("has nothing to say with no camera registered", () => {
    expect(cameraStatusRows([], {})).toEqual([]);
    expect(camerasSummary([])).toBe("none registered");
  });

  it("counts the cameras that are registered", () => {
    expect(camerasSummary([camera("a"), camera("b")])).toBe("2 registered");
  });
});

describe("a camera with its detector off", () => {
  const off = (area: string) =>
    ({ area, detect: false }) as RegisteredCamera;

  it("says so rather than reading as an empty floor", () => {
    expect(cameraStatusRows([off("dev-corner")], {})).toEqual([
      { area: "dev-corner", label: "detection off" },
    ]);
  });

  it("says so even while a stale detection is still held", () => {
    expect(
      cameraStatusRows([off("dev-corner")], {
        "dev-corner": detection("dev-corner", "found"),
      }),
    ).toEqual([{ area: "dev-corner", label: "detection off" }]);
  });
});
