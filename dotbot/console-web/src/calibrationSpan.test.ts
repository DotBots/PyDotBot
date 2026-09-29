import { describe, expect, it } from "vitest";

import {
  ageDays,
  calibrationSpans,
  convexHull,
  describePointsFrom,
  hatchBox,
  spanTitle,
} from "./calibrationSpan";
import type { SiteCalibration } from "./types";

// A 500 mm square at the centre of a 2 x 2 m field, in capture order.
const SQUARE: [number, number][] = [
  [750, 750],
  [1250, 750],
  [750, 1250],
  [1250, 1250],
];

const CALIBRATION: SiteCalibration = {
  id: "ac893d2d85e3068c",
  tag: "demo",
  created_at: "2026-09-10T09:12:00Z",
  placements: [{ points_mm: SQUARE, points_from: { kind: "square", side_mm: 500 } }],
};

describe("convexHull", () => {
  it("orders four corners captured in Z order round the square", () => {
    expect(convexHull(SQUARE)).toEqual([
      [750, 750],
      [1250, 750],
      [1250, 1250],
      [750, 1250],
    ]);
  });

  it("drops a point inside the others", () => {
    expect(convexHull([...SQUARE, [1000, 1000]])).toHaveLength(4);
  });
});

describe("calibrationSpans", () => {
  it("gives the span of four points, with how they were chosen", () => {
    const [span] = calibrationSpans(CALIBRATION);
    expect(span.points).toHaveLength(4);
    expect(span.pointsFrom).toEqual({ kind: "square", side_mm: 500 });
  });

  it("skips a placement whose points do not span an area", () => {
    const line = {
      ...CALIBRATION,
      placements: [{ points_mm: [[0, 0], [10, 0], [20, 0]] as [number, number][], points_from: { kind: "points" } as const }],
    };
    expect(calibrationSpans(line)).toEqual([]);
    expect(calibrationSpans(null)).toEqual([]);
  });
});

describe("hatchBox", () => {
  it("clips the hatch to the site's extent", () => {
    expect(hatchBox([2000, 4000])).toEqual({ x: 0, y: 0, w: 2000, h: 4000 });
  });

  it("draws no hatch for a site with no extent", () => {
    expect(hatchBox(null)).toBeNull();
  });
});

describe("the tooltip", () => {
  it("says how the points were chosen", () => {
    expect(describePointsFrom({ kind: "field" })).toBe("the field's corners");
    expect(describePointsFrom({ kind: "over", area: "dev-corner" })).toBe(
      "the corners of dev-corner",
    );
    expect(describePointsFrom({ kind: "square", side_mm: 500 })).toBe(
      "a 500 mm square in the field",
    );
    expect(describePointsFrom({ kind: "points" })).toBe("points given by hand");
    expect(describePointsFrom(null)).toBe("its recorded points");
  });

  it("names the calibration and its age", () => {
    const now = new Date("2026-09-29T10:00:00Z");
    expect(ageDays(CALIBRATION.created_at, now)).toBe(19);
    expect(ageDays("", now)).toBeNull();
    expect(ageDays("2099-01-01T00:00:00Z", now)).toBe(0);
    const [span] = calibrationSpans(CALIBRATION);
    expect(spanTitle(CALIBRATION, span, now)).toBe(
      "LH2 calibration demo (ac893d2d), 19 days old: calibrated over a 500 mm " +
        "square in the field. Positions outside the outline are extrapolated.",
    );
  });
});
