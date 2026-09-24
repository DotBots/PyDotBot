import { afterEach, describe, expect, it } from "vitest";

import { DEFAULT_WAYPOINT_SETTINGS, batchFields, clampTo, loadWaypointSettings, RADIUS_MM } from "./arrival";

const KEY = "dotbot.console.waypointSettings";
afterEach(() => window.localStorage.clear());

describe("the waypoint settings", () => {
  it("clamps a number to its range, and refuses what is not one", () => {
    expect(clampTo("0.4", RADIUS_MM)).toBe(1);
    expect(clampTo(800, RADIUS_MM)).toBe(500);
    expect(clampTo("", RADIUS_MM)).toBeNull();
    expect(clampTo("abc", RADIUS_MM)).toBeNull();
  });

  it("reads back field by field, the default for anything unreadable", () => {
    expect(loadWaypointSettings()).toEqual(DEFAULT_WAYPOINT_SETTINGS);
    window.localStorage.setItem(KEY, JSON.stringify({ arrivalMm: 2, passMm: "x", headingTolDeg: 90 }));
    expect(loadWaypointSettings()).toEqual({ arrivalMm: 2, passMm: 20, headingTolDeg: 45 });
    window.localStorage.setItem(KEY, "{nope");
    expect(loadWaypointSettings()).toEqual(DEFAULT_WAYPOINT_SETTINGS);
  });

  it("leaves the tolerance to the firmware unless one is set", () => {
    expect(batchFields(DEFAULT_WAYPOINT_SETTINGS)).toEqual({ intermediate_threshold: 20 });
    expect(batchFields({ arrivalMm: 5, passMm: 25, headingTolDeg: 4 })).toEqual({
      intermediate_threshold: 25,
      heading_tolerance: 4,
    });
  });
});
