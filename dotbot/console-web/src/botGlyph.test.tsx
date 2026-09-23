import React from "react";
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import {
  BOT_MIN_PX,
  BotGlyph,
  FOOTPRINT_MIN_PX,
  GLYPH_CROWD_BOTS,
  GLYPH_DETAIL_PX,
  SENSOR_POINT_PX,
  botBody,
  botFootprintPx,
  glyphLevel,
  robotDraw,
} from "./BotGlyph";
import type { RobotDrawing } from "./robotDrawing";
import type { BotPose, LH2Position } from "./types";

afterEach(cleanup);

// A v3 body as the controller ships it: the board path, the centre, the nose,
// all in frame millimetres and already rotated. This is a payload, not a
// geometry the console may compute - the point of the fixture is that the
// numbers arrive from outside.
const V3_AT_ORIGIN: LH2Position[] = [
  { x: -43, y: 10.5 },
  { x: -47, y: 10.5 },
  { x: -47, y: -27.5 },
  { x: -28.5, y: -27.5 },
  { x: -28.5, y: -76.5 },
  { x: 28.5, y: -76.5 },
  { x: 28.5, y: -27.5 },
  { x: 47, y: -27.5 },
  { x: 47, y: 10.5 },
  { x: 43, y: 10.5 },
  { x: 42, y: 11.5 },
  { x: 42, y: 18.5 },
  { x: -42, y: 18.5 },
  { x: -42, y: 11.5 },
];

// The two tyres in the same payload frame: the track between their centres,
// one tyre's width across the robot and the wheel's diameter along it.
const V3_WHEELS_AT_ORIGIN: LH2Position[][] = [
  [
    { x: 30.25, y: -31.5 },
    { x: 47.75, y: -31.5 },
    { x: 47.75, y: -75.5 },
    { x: 30.25, y: -75.5 },
  ],
  [
    { x: -47.75, y: -31.5 },
    { x: -30.25, y: -31.5 },
    { x: -30.25, y: -75.5 },
    { x: -47.75, y: -75.5 },
  ],
];

const SENSOR: LH2Position = { x: 1000, y: 1000 };

// The pose of a bot standing on SENSOR facing `heading`. The board turns with
// the robot, which is what the controller sends: the heading is a label on an
// already-rotated path, never an instruction to rotate one.
const pose = (heading = 0, over: Partial<BotPose> = {}): BotPose => {
  const theta = (heading * Math.PI) / 180;
  const place = (p: LH2Position): LH2Position => ({
    x: SENSOR.x + p.x * Math.cos(theta) - p.y * Math.sin(theta),
    y: SENSOR.y + p.x * Math.sin(theta) + p.y * Math.cos(theta),
  });
  return {
    heading_deg: heading,
    heading_source: "travel",
    photodiode: SENSOR,
    axle: place({ x: 0, y: -53.5 }),
    centre: place({ x: 0, y: -29 }),
    nose: place({ x: 0, y: 18.5 }),
    led: place({ x: 0, y: 5.5 }),
    outline: V3_AT_ORIGIN.map(place),
    wheels: V3_WHEELS_AT_ORIGIN.map((wheel) => wheel.map(place)),
    reach_mm: 89.33,
    core_mm: 18.5,
    envelope_mm: 95,
    ...over,
  };
};

describe("the body a pose describes", () => {
  it("is the payload's own path, put back on the fix it belongs to", () => {
    const body = botBody(pose())!;
    expect(body.outline).toEqual(V3_AT_ORIGIN);
    expect(body.centre).toEqual({ x: 0, y: -29 });
    expect(body.nose).toEqual({ x: 0, y: 18.5 });
  });

  it("is the robot's own size, not the box it happens to occupy", () => {
    // 95 mm long by 94 wide, whichever way it faces. Measured in the arena
    // frame instead, a body turned 45 degrees spans 134 mm and the chrome
    // around it would breathe as the robot turned.
    for (const heading of [0, 37, 90, 180, -135]) {
      const turned = botBody(pose(heading))!;
      expect(turned.spanMm).toBeCloseTo(95, 6);
    }
  });

  it("is nothing at all without a heading, which is the whole rule", () => {
    expect(botBody(pose(0, { heading_source: "none" }))).toBeNull();
  });

  it("is hung off the pose's photodiode, not the LH2 fix", () => {
    // A pose placed 10 mm off SENSOR, the bot's lh2_position: read against
    // the fix the board would come out 10 mm askew.
    const shift = (p: LH2Position): LH2Position => ({ x: p.x + 10, y: p.y });
    const p = pose();
    const body = botBody({
      ...p,
      photodiode: shift(p.photodiode),
      centre: shift(p.centre),
      nose: shift(p.nose),
      outline: p.outline.map(shift),
    })!;
    expect(body.outline).toEqual(V3_AT_ORIGIN);
    expect(body.centre).toEqual({ x: 0, y: -29 });
    expect(body.nose).toEqual({ x: 0, y: 18.5 });
  });

  it("is nothing without a pose or an outline", () => {
    expect(botBody(undefined)).toBeNull();
    expect(botBody(null)).toBeNull();
    expect(botBody(pose(0, { outline: [] }))).toBeNull();
  });
});

describe("how big a bot is drawn", () => {
  it("is its true footprint wherever that is big enough to see", () => {
    // 1 m across 200 px: a 95 mm robot is 19 px of it.
    expect(botFootprintPx(200 / 1000, 95)).toBeCloseTo(19, 6);
    expect(botFootprintPx(1000 / 1000, 95)).toBeCloseTo(95, 6);
  });

  it("grows with the camera rather than staying a fixed size", () => {
    expect(botFootprintPx(0.6, 95) / botFootprintPx(0.3, 95)).toBeCloseTo(2, 6);
  });

  it("floors at a size that can still be seen and clicked", () => {
    expect(botFootprintPx(0.001, 95)).toBe(BOT_MIN_PX);
    expect(botFootprintPx(0, 95)).toBe(BOT_MIN_PX);
  });

  it("is that floor for a bot with no body, which is a point", () => {
    expect(botFootprintPx(1, 0)).toBe(BOT_MIN_PX);
  });
});

describe("how much of a bot is drawn", () => {
  it("is whatever its on-screen size can carry", () => {
    expect(glyphLevel(GLYPH_DETAIL_PX, 1)).toBe("detail");
    expect(glyphLevel(GLYPH_DETAIL_PX - 1, 1)).toBe("dot");
  });

  it("draws the board from the size the outline was judged legible at", () => {
    // Read off the map itself, with a bot turned 45 degrees so the outline is
    // hardest to make out: the stepped board and a tyre still show at 17 px,
    // and are a coloured blob at 11.
    expect(glyphLevel(17, 1)).toBe("detail");
    expect(glyphLevel(11, 1)).toBe("dot");
  });

  it("drops the board to a square in a crowd, where detail is lost anyway", () => {
    const many = GLYPH_CROWD_BOTS + 1;
    expect(glyphLevel(GLYPH_DETAIL_PX, many)).toBe("dot");
    expect(glyphLevel(200, many)).toBe("dot");
  });

  it("bottoms out at the dot however crowded the map gets", () => {
    expect(glyphLevel(1, 100000)).toBe("dot");
  });

  it("takes zoom over crowding: a fleet zoomed into still gets its detail", () => {
    expect(glyphLevel(200, GLYPH_CROWD_BOTS)).toBe("detail");
  });
});

describe("what a robot is drawn as", () => {
  const BODY: RobotDrawing = { mode: "body", footprint: true };
  const SENSOR_MODE: RobotDrawing = { mode: "sensor", footprint: true };
  // Scales at which the 95 mm board is 95 px, and 9.5 px.
  const NEAR = 1;
  const FAR = 0.1;

  it("is the board for a robot with a heading, big enough and not crowded", () => {
    const d = robotDraw(pose(), BODY, NEAR, 1);
    expect(d.shape.kind).toBe("board");
    expect(d.turned).toBe(true);
    expect(d.battery && d.drive).toBe(true);
  });

  it("is drawn fainter as an estimate only when built on the travel bearing", () => {
    expect(robotDraw(pose(), BODY, NEAR, 1).estimate).toBe(true);
    expect(robotDraw(pose(0, { heading_source: "ekf" }), BODY, NEAR, 1).estimate).toBe(false);
  });

  it("is the square below the size the board reads at", () => {
    const d = robotDraw(pose(), BODY, FAR, 1);
    expect(d.shape.kind).toBe("mark");
    expect(d.footprintPx).toBeLessThan(GLYPH_DETAIL_PX);
    expect(d.battery || d.drive).toBe(false);
  });

  it("is the envelope disc where a crowd hides a board big enough to read", () => {
    const d = robotDraw(pose(), BODY, NEAR, GLYPH_CROWD_BOTS + 1);
    expect(d.shape.kind).toBe("disc");
    expect(d.shape.kind === "disc" && d.shape.radiusPx).toBeCloseTo(47.5, 6);
    expect(d.centre).toEqual({ x: 0, y: -29 });
  });

  it("is the square in a crowd too, once the board is too small anyway", () => {
    expect(robotDraw(pose(), BODY, FAR, GLYPH_CROWD_BOTS + 1).shape.kind).toBe("mark");
  });

  it("is the sensor point for a robot with no heading, whatever the zoom", () => {
    for (const scale of [NEAR, FAR]) {
      const d = robotDraw(pose(0, { heading_source: "none" }), BODY, scale, 1);
      expect(d.shape.kind).toBe("sensor");
      expect(d.centre).toEqual({ x: 0, y: 0 });
      expect(d.drive).toBe(false);
    }
  });

  it("is the sensor point for every robot in Sensor mode", () => {
    expect(robotDraw(pose(), SENSOR_MODE, NEAR, 1).shape.kind).toBe("sensor");
  });

  it("rings the sensor point with the host's reach and core", () => {
    const { shape, footprintPx } = robotDraw(pose(), SENSOR_MODE, NEAR, 1);
    expect(shape).toEqual({ kind: "sensor", ringPx: 89.33, corePx: 18.5, crowded: false });
    expect(footprintPx).toBeCloseTo(2 * 89.33, 6);
  });

  it("hides the ring below the size it reads at, and the core with it", () => {
    const scale = (FOOTPRINT_MIN_PX - 1) / (2 * 89.33);
    const { shape, footprintPx } = robotDraw(pose(), SENSOR_MODE, scale, 1);
    expect(shape).toMatchObject({ ringPx: null, corePx: null });
    expect(footprintPx).toBe(SENSOR_POINT_PX);
  });

  it("draws the core only when it is visibly larger than the point", () => {
    const scale = SENSOR_POINT_PX / (2 * 18.5);
    const { shape } = robotDraw(pose(), SENSOR_MODE, scale, 1);
    expect(shape).toMatchObject({ corePx: null });
    expect(shape.kind === "sensor" && shape.ringPx).toBeGreaterThan(0);
  });

  it("draws no footprint with the checkbox off", () => {
    const { shape } = robotDraw(pose(), { mode: "sensor", footprint: false }, NEAR, 1);
    expect(shape).toMatchObject({ ringPx: null, corePx: null });
  });

  it("marks the ring as crowded past the crowd size", () => {
    const { shape } = robotDraw(pose(), SENSOR_MODE, NEAR, GLYPH_CROWD_BOTS + 1);
    expect(shape).toMatchObject({ crowded: true });
  });
});

describe("the glyph a shape draws", () => {
  const svg = (props: Parameters<typeof BotGlyph>[0]) =>
    render(<BotGlyph {...props} />).container.querySelector("svg")!;

  const body = botBody(pose())!;
  const board = { kind: "board", body } as const;

  it("draws the layers of one robot at full detail", () => {
    const el = svg({ color: "red", shape: board, pxPerMm: 1, footprintPx: 95 });
    // The tyres, the board over them, the line out to its nose, and the
    // photodiode the fix came from.
    expect(el.querySelectorAll('[data-layer="wheel"]')).toHaveLength(2);
    expect(el.querySelectorAll('[data-layer="board"]')).toHaveLength(1);
    expect(el.querySelectorAll("line")).toHaveLength(1);
    expect(el.querySelectorAll("circle")).toHaveLength(1);
  });

  it("draws each tyre where the pose puts it, at the size it was sent", () => {
    const el = svg({ color: "red", shape: board, pxPerMm: 1, footprintPx: 95 });
    const wheels = [...el.querySelectorAll('[data-layer="wheel"]')].map((w) =>
      w.getAttribute("points"),
    );
    expect(wheels[0]).toBe("30.25,-31.5 47.75,-31.5 47.75,-75.5 30.25,-75.5");
    expect(wheels[1]).toBe("-47.75,-31.5 -30.25,-31.5 -30.25,-75.5 -47.75,-75.5");
  });

  it("draws the board alone from a host that sends no tyres", () => {
    const older = botBody(pose(0, { wheels: undefined }))!;
    const el = svg({ color: "red", shape: { kind: "board", body: older }, pxPerMm: 1, footprintPx: 95 });
    expect(el.querySelectorAll('[data-layer="wheel"]')).toHaveLength(0);
    expect(el.querySelectorAll('[data-layer="board"]')).toHaveLength(1);
  });

  it("puts the board where the pose puts it, not on the fix", () => {
    const el = svg({ color: "red", shape: board, pxPerMm: 1, footprintPx: 95 });
    const points = el
      .querySelector('[data-layer="board"]')!
      .getAttribute("points")!;
    // The rear edge of a bot facing heading 0 is 76.5 mm back from its fix.
    expect(points).toContain("-76.5");
    // The photodiode is the origin, so the dot needs no placing at all.
    const dot = el.querySelector("circle")!;
    expect(dot.getAttribute("cx")).toBeNull();
    expect(dot.getAttribute("cy")).toBeNull();
  });

  it("draws a mark at the board's centre, ticked toward its nose", () => {
    const el = svg({ color: "red", shape: { kind: "mark", body }, pxPerMm: 0.1, footprintPx: 9.5 });
    expect(el.querySelectorAll("polygon")).toHaveLength(0);
    const rect = el.querySelector("rect")!;
    // Centred 29 mm behind the fix, so a mark stands where the robot does.
    expect(parseFloat(rect.getAttribute("y")!)).toBeCloseTo(-2.9 - 9.5 / 2, 6);
    const tick = el.querySelector('[data-layer="heading-tick"]')!;
    expect(parseFloat(tick.getAttribute("y1")!)).toBeCloseTo(-2.9, 6);
    // Heading 0 puts the nose toward +y.
    expect(parseFloat(tick.getAttribute("y2")!)).toBeGreaterThan(-2.9);
  });

  it("draws the disc about the board's centre, with its heading and photodiode", () => {
    const el = svg({ color: "red", shape: { kind: "disc", body, radiusPx: 20 }, pxPerMm: 0.4, footprintPx: 40 });
    const disc = el.querySelector('[data-layer="disc"]')!;
    expect(parseFloat(disc.getAttribute("cy")!)).toBeCloseTo(-29 * 0.4, 6);
    expect(el.querySelector('[data-layer="heading"]')).not.toBeNull();
    expect(el.querySelector('[data-layer="photodiode"]')).not.toBeNull();
  });

  it("draws the sensor point at a fixed size, rimmed in white", () => {
    for (const pxPerMm of [0.05, 2]) {
      const el = svg({
        color: "red",
        shape: { kind: "sensor", ringPx: null, corePx: null, crowded: false },
        pxPerMm,
        footprintPx: BOT_MIN_PX,
      });
      expect(el.querySelectorAll("polygon")).toHaveLength(0);
      expect(el.querySelectorAll("circle")).toHaveLength(1);
      const point = el.querySelector('[data-layer="sensor"]')!;
      const r = parseFloat(point.getAttribute("r")!);
      const rim = parseFloat(point.getAttribute("stroke-width")!);
      expect(2 * r + rim).toBe(SENSOR_POINT_PX);
      cleanup();
    }
  });

  it("draws the ring dashed and the core solid around the point", () => {
    const el = svg({
      color: "red",
      shape: { kind: "sensor", ringPx: 60, corePx: 12, crowded: false },
      pxPerMm: 1,
      footprintPx: 120,
    });
    expect(el.querySelector('[data-layer="reach"]')!.getAttribute("stroke-dasharray")).toBeTruthy();
    expect(el.querySelector('[data-layer="core"]')!.getAttribute("stroke-dasharray")).toBeNull();
    expect(el.querySelector('[data-layer="sensor"]')).not.toBeNull();
  });

  it("lays the dashed ring over a solid casing of the same radius", () => {
    const el = svg({
      color: "red",
      shape: { kind: "sensor", ringPx: 60, corePx: null, crowded: false },
      pxPerMm: 1,
      footprintPx: 120,
    });
    const circles = [...el.querySelectorAll("circle")];
    const casing = el.querySelector('[data-layer="reach-casing"]')!;
    const ring = el.querySelector('[data-layer="reach"]')!;
    expect(circles.indexOf(casing as SVGCircleElement)).toBeLessThan(
      circles.indexOf(ring as SVGCircleElement),
    );
    expect(casing.getAttribute("r")).toBe(ring.getAttribute("r"));
    expect(casing.getAttribute("stroke")).toBe("var(--footprint-casing)");
    expect(casing.getAttribute("stroke-dasharray")).toBeNull();
    expect(parseFloat(casing.getAttribute("stroke-width")!)).toBeGreaterThan(
      parseFloat(ring.getAttribute("stroke-width")!),
    );
  });
});
