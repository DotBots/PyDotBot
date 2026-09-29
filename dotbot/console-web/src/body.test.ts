import { describe, expect, it } from "vitest";

import { bodyOf, robotBody } from "./body";
import { RobotBody, RobotPose } from "./types";

// dotbot-v3's shape as the controller sends it, cut down to what is checked.
const SHAPE: RobotBody = {
  heading_deg: 0,
  heading_source: "none",
  photodiode: { x: 0, y: 53.5 },
  axle: { x: 0, y: 0 },
  centre: { x: 0, y: 24.5 },
  nose: { x: 0, y: 72 },
  led: { x: 0, y: 59 },
  outline: [{ x: -43, y: 64 }],
  wheels: [[{ x: -39, y: 0 }]],
  reach_mm: 88.91,
  core_mm: 18.5,
  envelope_mm: 95,
};

const pose = (over: Partial<RobotPose> = {}): RobotPose => ({
  x: 1053.5,
  y: 1000,
  heading_deg: 90,
  heading_source: "travel",
  ...over,
});

describe("a robot's body from its pose", () => {
  it("turns the shape by the heading and moves it onto the axle", () => {
    const body = bodyOf(SHAPE, pose());
    // The controller's own expansion of the same fix: photodiode at (1000, 1000)
    expect(body.photodiode.x).toBeCloseTo(1000);
    expect(body.photodiode.y).toBeCloseTo(1000);
    expect(body.centre.x).toBeCloseTo(1029);
    expect(body.axle).toEqual({ x: 1053.5, y: 1000 });
    expect(body.wheels[0][0].x).toBeCloseTo(1053.5);
    expect(body.wheels[0][0].y).toBeCloseTo(961);
    expect(body).toMatchObject({ heading_deg: 90, heading_source: "travel", reach_mm: 88.91 });
  });

  it("is the shape moved without turning at heading 0", () => {
    const body = bodyOf(SHAPE, pose({ heading_deg: 0 }));
    expect(body.outline).toEqual([{ x: 1053.5 - 43, y: 1064 }]);
  });

  it("is built once per pose and model shape", () => {
    const p = pose();
    const shapes = { "dotbot-v3": SHAPE };
    expect(robotBody(p, undefined, shapes)).toBe(robotBody(p, "dotbot-v3", shapes));
    expect(robotBody(p, "dotbot-v9", shapes)).toBeNull();
    const reshaped = { "dotbot-v3": { ...SHAPE, reach_mm: 1 } };
    expect(robotBody(p, undefined, reshaped)?.reach_mm).toBe(1);
  });
});
