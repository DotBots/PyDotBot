import { describe, expect, it } from "vitest";

import {
  CORNERS,
  PHONE_MAX_PX,
  cornerTitle,
  currentPoint,
  expectedErrorLine,
  isPhoneWidth,
  noseHeading,
  noseRotation,
  placementInstruction,
  readFraction,
  residualLines,
  sessionRect,
  stepLabel,
} from "./calibration";
import type { CalibrationPoint, CalibrationSession } from "./types";

// The arena's four edge-aligned photodiode marks, as the controller resolves
// them: the corner inset by the robot's own geometry, 47 mm in x and 18.5 mm
// in y, nose toward the nearest top or bottom edge.
const POINTS: CalibrationPoint[] = [
  { x: 47, y: 18.5, corner: "top-left", nose: "top" },
  { x: 1953, y: 18.5, corner: "top-right", nose: "top" },
  { x: 47, y: 1981.5, corner: "bottom-left", nose: "bottom" },
  { x: 1953, y: 1981.5, corner: "bottom-right", nose: "bottom" },
].map((p, index) => ({
  index,
  x: p.x,
  y: p.y,
  corner: p.corner,
  area: "arena",
  where: `${p.corner} corner of arena`,
  how: `robot inside the rectangle, ${p.corner!.split("-")[1]} edge on the ${
    p.corner!.split("-")[1]
  } line, front edge on the ${p.corner!.split("-")[0]} line, nose toward the ${p.nose}`,
  nose: p.nose,
  captured: false,
  reads: [],
  dropped: 0,
}));

const session = (over: Partial<CalibrationSession> = {}): CalibrationSession => ({
  at: "arena:corners",
  site: "c405-arena",
  area: "",
  device: "",
  reads: 25,
  status: "collecting",
  outstanding: 0,
  captured: 0,
  total: 4,
  expected_error_mm: null,
  points: POINTS,
  stations: [],
  unsolved: [],
  saved_path: null,
  saved_id: "",
  error: "",
  ...over,
});

describe("the corners, numbered in capture order", () => {
  it("numbers them top-left, top-right, bottom-left, bottom-right", () => {
    expect(CORNERS).toEqual([
      "top-left",
      "top-right",
      "bottom-left",
      "bottom-right",
    ]);
    expect(session().points.map((p) => p.index)).toEqual([0, 1, 2, 3]);
    expect(session().points.map((p) => p.corner)).toEqual([...CORNERS]);
  });

  it("spans the rectangle its points enclose", () => {
    expect(sessionRect(session())).toEqual({
      x: 47,
      y: 18.5,
      w: 1906,
      h: 1963,
      name: "arena:corners",
    });
  });

  it("has no rectangle before the controller answers", () => {
    expect(sessionRect(null)).toBeNull();
  });
});

describe("the robot glyph at each corner", () => {
  it("turns the top pair's nose up and the bottom pair's down", () => {
    // Heading 0 is +y, the bottom of the map, so a nose toward the top is
    // half a circle from it. The two pairs therefore face away from each
    // other, which is what edge alignment looks like on the floor.
    expect(session().points.map((p) => noseHeading(p.nose))).toEqual([
      180, 180, 0, 0,
    ]);
    expect(session().points.map((p) => noseRotation(p.nose))).toEqual([0, 0, 180, 180]);
  });
});

describe("the step card's wording", () => {
  it("counts the outstanding point from one", () => {
    expect(stepLabel(session({ outstanding: 0 }))).toBe("Step 1 of 4");
    expect(stepLabel(session({ outstanding: 2, captured: 2 }))).toBe("Step 3 of 4");
  });

  it("stays on the last step once every point is captured", () => {
    expect(stepLabel(session({ outstanding: null, captured: 4 }))).toBe("Step 4 of 4");
  });

  it("names the corner in words, not as a coordinate", () => {
    expect(cornerTitle(POINTS[2])).toBe("Bottom-left corner");
  });

  it("states the placement as an instruction", () => {
    expect(placementInstruction(POINTS[2])).toMatch(/^Robot inside the rectangle/);
    expect(placementInstruction(POINTS[2])).toContain("nose toward the bottom");
  });

  it("falls back to the coordinate for a point that constrains no pose", () => {
    const typed: CalibrationPoint = {
      ...POINTS[0],
      corner: null,
      how: "",
      where: "",
    };
    expect(cornerTitle(typed)).toBe("Typed point");
    expect(placementInstruction(typed)).toBe("Photodiode on (47, 18.5) mm.");
  });

  it("shows the outstanding point, and the last one once there is none", () => {
    expect(currentPoint(session({ outstanding: 2 }))?.index).toBe(2);
    expect(currentPoint(session({ outstanding: null }))?.index).toBe(3);
  });
});

describe("the read bars", () => {
  it("fills in proportion to the target and never past it", () => {
    expect(readFraction(0, 25)).toBe(0);
    expect(readFraction(18, 25)).toBeCloseTo(0.72);
    expect(readFraction(30, 25)).toBe(1);
  });

  it("stays empty when no target is known yet", () => {
    expect(readFraction(3, 0)).toBe(0);
  });
});

describe("the expected-error line", () => {
  it("is absent while the controller sends no number", () => {
    // The predictor is a later phase, so the line is not shown rather than
    // shown with a guess in it.
    expect(expectedErrorLine(session(), ["arena"])).toBeNull();
    expect(expectedErrorLine(null, ["arena"])).toBeNull();
  });

  it("names the area the session was started over", () => {
    expect(expectedErrorLine(session({ expected_error_mm: 1.6 }), ["arena"])).toBe(
      "expected 1.6 mm over arena",
    );
  });

  it("says the whole site when the session named no area", () => {
    expect(expectedErrorLine(session({ expected_error_mm: 18.5 }), [])).toBe(
      "expected 18.5 mm over the whole site",
    );
  });
});

describe("what the card says after the last point", () => {
  it("gives one residual line per solved station", () => {
    const solved = session({
      outstanding: null,
      captured: 4,
      stations: [
        { index: 0, points: 4, residual_mm: 0, solved_from: "direct" },
        { index: 1, points: 4, residual_mm: 0.04, solved_from: "direct" },
      ],
    });
    expect(residualLines(solved)).toEqual([
      "station 0  residual 0.0 mm",
      "station 1  residual 0.0 mm",
    ]);
  });
});

describe("the phone layout", () => {
  it("takes over below 480 px, so a 390 px screen gets the card", () => {
    expect(PHONE_MAX_PX).toBe(480);
    expect(isPhoneWidth(390)).toBe(true);
    expect(isPhoneWidth(479)).toBe(true);
    expect(isPhoneWidth(480)).toBe(false);
    expect(isPhoneWidth(1440)).toBe(false);
  });
});
