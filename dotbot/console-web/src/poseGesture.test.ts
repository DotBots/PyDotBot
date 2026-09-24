import { describe, expect, it } from "vitest";

import {
  ARM_PX,
  DRAG_PX,
  HOLD_MS,
  bearing,
  headingOf,
  moveGesture,
  normDeg,
  poseAt,
  releaseGesture,
  silhouetteTemplate,
  snapDeg,
  startGesture,
  tickGesture,
  wheelSteps,
} from "./poseGesture";
import { poseShape } from "./PoseMarker";
import type { BotPose } from "./types";

// A robot facing down the map (heading 0) with its axle at (1000, 1000) and
// its photodiode 53.5 mm ahead, the v3's lever.
const LEVER = 53.5;
const template: BotPose = {
  heading_deg: 0,
  heading_source: "ekf",
  photodiode: { x: 1000, y: 1000 + LEVER },
  axle: { x: 1000, y: 1000 },
  centre: { x: 1000, y: 1000 + 20 },
  nose: { x: 1000, y: 1000 + 70 },
  led: { x: 1000, y: 1000 + 60 },
  outline: [
    { x: 970, y: 960 },
    { x: 1030, y: 960 },
    { x: 1030, y: 1070 },
    { x: 970, y: 1070 },
  ],
  wheels: [
    [
      { x: 960, y: 990 },
      { x: 968, y: 990 },
      { x: 968, y: 1010 },
      { x: 960, y: 1010 },
    ],
  ],
  reach_mm: 90,
  core_mm: 25,
  envelope_mm: 110,
};

const at = { x: 500, y: 500 };
const press = { x: 400, y: 300 };
const begin = () => startGesture(press, at, 0, 0);

describe("the heading convention", () => {
  it("is the robot's: 0 faces down the map, 270 right, 90 left, 180 up", () => {
    expect(headingOf(0, 100)).toBeCloseTo(0);
    expect(headingOf(100, 0)).toBeCloseTo(270);
    expect(headingOf(-100, 0)).toBeCloseTo(90);
    expect(headingOf(0, -100)).toBeCloseTo(180);
  });

  it("normalises into [0, 360)", () => {
    expect(normDeg(-15)).toBe(345);
    expect(normDeg(360)).toBe(0);
    expect(normDeg(725)).toBe(5);
    expect(Object.is(normDeg(-0), 0)).toBe(true);
  });

  it("snaps to 15 degree detents", () => {
    expect(snapDeg(52)).toBe(45);
    expect(snapDeg(53)).toBe(60);
    expect(snapDeg(358)).toBe(0);
  });

  it("measures an approach bearing, and none for a point onto itself", () => {
    expect(bearing({ x: 0, y: 0 }, { x: 100, y: 0 })).toBeCloseTo(270);
    expect(bearing({ x: 5, y: 5 }, { x: 5, y: 5 })).toBeNull();
  });
});

describe("the placing gesture", () => {
  it("queues a position for a click under the hold and the drag threshold", () => {
    const g = begin();
    expect(releaseGesture(g, press.x + 2, press.y + 2, HOLD_MS - 1, false)).toEqual(at);
  });

  it("turns into the silhouette after the hold, or after a drag", () => {
    expect(tickGesture(begin(), HOLD_MS - 1).phase).toBe("pressing");
    expect(tickGesture(begin(), HOLD_MS).phase).toBe("silhouette");
    expect(moveGesture(begin(), press.x + DRAG_PX, press.y, 10, false).phase).toBe("silhouette");
  });

  it("faces the cursor once it is out past the arming radius", () => {
    const g = tickGesture(begin(), HOLD_MS);
    const aimed = moveGesture(g, press.x + 100, press.y, HOLD_MS + 50, false);
    expect(aimed.phase).toBe("rotating");
    expect(aimed.heading).toBeCloseTo(270);
    expect(releaseGesture(g, press.x + 100, press.y, HOLD_MS + 60, false)).toEqual({
      ...at,
      heading_deg: 270,
    });
  });

  it("queues a position when released back inside the arming radius", () => {
    let g = moveGesture(begin(), press.x + 60, press.y, 20, false);
    expect(g.phase).toBe("rotating");
    g = moveGesture(g, press.x + DRAG_PX, press.y, 30, false);
    expect(g.phase).toBe("silhouette");
    expect(releaseGesture(g, press.x + ARM_PX - 1, press.y, 40, false)).toEqual(at);
  });

  it("snaps with Shift, read live at every move", () => {
    const r = 100;
    const x = press.x - r * Math.sin((52 * Math.PI) / 180);
    const y = press.y + r * Math.cos((52 * Math.PI) / 180);
    const g = moveGesture(begin(), x, y, 20, false);
    expect(g.heading).toBeCloseTo(52);
    expect(moveGesture(g, x, y, 30, true).heading).toBe(45);
    expect(releaseGesture(g, x, y, 40, true).heading_deg).toBe(45);
  });

  it("pins a pose started on a robot to that robot's axle", () => {
    const axle = { x: 1000, y: 1000 };
    const g = startGesture(press, at, 0, 0, { x: 410, y: 310 }, axle);
    const w = releaseGesture(g, 410, 410, 20, false);
    expect(w).toEqual({ ...axle, heading_deg: 0 });
  });
});

describe("the silhouette", () => {
  it("keeps the axle on the anchor and swings the body about it", () => {
    const p = poseAt(template, { x: 200, y: 300 }, 270);
    expect(p.axle).toEqual({ x: 200, y: 300 });
    expect(p.heading_deg).toBe(270);
    // Facing right, the photodiode is the lever out along +x.
    expect(p.photodiode.x).toBeCloseTo(200 + LEVER);
    expect(p.photodiode.y).toBeCloseTo(300);
    expect(p.outline).toHaveLength(template.outline.length);
  });

  it("borrows the first selected robot with a heading", () => {
    const bots = [
      { id: "a", pose: { ...template, heading_source: "none" as const } },
      { id: "b", pose: template },
      { id: "c", pose: null },
    ];
    expect(silhouetteTemplate(bots, ["a", "b"])).toBe(template);
    expect(silhouetteTemplate(bots, ["a", "c"])).toBeNull();
  });

  it("is the board when it reads, and the diamond with a tick otherwise", () => {
    expect(poseShape(template, at, 90, 1).kind).toBe("board");
    expect(poseShape(template, at, 90, 0.02).kind).toBe("tick");
    expect(poseShape(null, at, 90, 1).kind).toBe("tick");
  });
});

describe("the wheel over a pose", () => {
  it("steps once per mouse notch", () => {
    expect(wheelSteps(0, 120, 0).steps).toBe(1);
    expect(wheelSteps(0, -100, 0).steps).toBe(-1);
    expect(wheelSteps(0, 3, 1).steps).toBe(1);
  });

  it("accumulates trackpad scroll, one step per 60 px", () => {
    let carry = 0;
    let steps = 0;
    for (let i = 0; i < 10; i++) {
      const r = wheelSteps(carry, 15, 0);
      carry = r.carry;
      steps += r.steps;
    }
    expect(steps).toBe(2);
    expect(carry).toBe(30);
  });
});
