import React from "react";
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import {
  BOT_MIN_PX,
  BotGlyph,
  FOOTPRINT_MIN_PX,
  LED_OFF,
  GLYPH_CROWD_BOTS,
  GLYPH_DETAIL_PX,
  SENSOR_POINT_PX,
  botBody,
  botFootprintPx,
  glyphLevel,
  ledFill,
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

  it("drops the board to a mark in a crowd, where detail is lost anyway", () => {
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
    expect(d.battery).toBe(true);
  });

  it("is drawn fainter as an estimate only when built on the travel bearing", () => {
    expect(robotDraw(pose(), BODY, NEAR, 1).estimate).toBe(true);
    expect(robotDraw(pose(0, { heading_source: "ekf" }), BODY, NEAR, 1).estimate).toBe(false);
  });

  it("is the mark below the size the board reads at", () => {
    const d = robotDraw(pose(), BODY, FAR, 1);
    expect(d.shape.kind).toBe("mark");
    expect(d.footprintPx).toBeLessThan(GLYPH_DETAIL_PX);
    expect(d.battery).toBe(false);
  });

  it("is the envelope disc where a crowd hides a board big enough to read", () => {
    const d = robotDraw(pose(), BODY, NEAR, GLYPH_CROWD_BOTS + 1);
    expect(d.shape.kind).toBe("disc");
    expect(d.shape.kind === "disc" && d.shape.radiusPx).toBeCloseTo(47.5, 6);
    expect(d.centre).toEqual({ x: 0, y: -29 });
  });

  it("is the mark in a crowd too, once the board is too small anyway", () => {
    expect(robotDraw(pose(), BODY, FAR, GLYPH_CROWD_BOTS + 1).shape.kind).toBe("mark");
  });

  it("is the sensor point for a robot with no heading, whatever the zoom", () => {
    for (const scale of [NEAR, FAR]) {
      const d = robotDraw(pose(0, { heading_source: "none" }), BODY, scale, 1);
      expect(d.shape.kind).toBe("sensor");
      expect(d.centre).toEqual({ x: 0, y: 0 });
    }
  });

  it("is the sensor point for every robot in Sensor mode", () => {
    expect(robotDraw(pose(), SENSOR_MODE, NEAR, 1).shape.kind).toBe("sensor");
  });

  it("rings the sensor point with the host's reach and core", () => {
    const { shape, footprintPx } = robotDraw(pose(), SENSOR_MODE, NEAR, 1);
    expect(shape).toMatchObject({ kind: "sensor", ringPx: 89.33, corePx: 18.5, crowded: false });
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

  it("gives a known heading a bar out to the ring, at the heading's angle", () => {
    for (const [heading, dx, dy] of [
      [0, 0, 1],
      [90, -1, 0],
      [-135, Math.SQRT1_2, -Math.SQRT1_2],
    ]) {
      const { shape } = robotDraw(pose(heading), SENSOR_MODE, NEAR, 1);
      const bar = shape.kind === "sensor" ? shape.bar : null;
      expect(bar).not.toBeNull();
      expect(bar!.dir.x).toBeCloseTo(dx, 6);
      expect(bar!.dir.y).toBeCloseTo(dy, 6);
      expect(bar!.lengthPx).toBeCloseTo(89.33, 6);
    }
  });

  it("gives no bar to a robot whose heading is unknown, in either mode", () => {
    for (const mode of [BODY, SENSOR_MODE]) {
      const { shape } = robotDraw(pose(0, { heading_source: "none" }), mode, NEAR, 1);
      expect(shape).toMatchObject({ kind: "sensor", bar: null });
    }
    expect(robotDraw(null, SENSOR_MODE, NEAR, 1).shape).toMatchObject({ bar: null });
  });

  it("keeps the bar past the point when the ring is too small to draw", () => {
    const { shape } = robotDraw(pose(), SENSOR_MODE, 0.01, 1);
    expect(shape).toMatchObject({ ringPx: null });
    expect(shape.kind === "sensor" && shape.bar!.lengthPx).toBe(SENSOR_POINT_PX);
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
    const el = svg({ state: "red", led: null, shape: board, pxPerMm: 1, footprintPx: 95 });
    // The tyres, the board over them and the sensor mark: no heading line,
    // since the board's own shape carries it.
    expect(el.querySelectorAll('[data-layer="wheel"]')).toHaveLength(2);
    expect(el.querySelectorAll('[data-layer="board"]')).toHaveLength(1);
    expect(el.querySelectorAll("line")).toHaveLength(0);
    expect(el.querySelectorAll('[data-layer="sensor-mark"]')).toHaveLength(1);
  });

  it("draws each tyre where the pose puts it, at the size it was sent", () => {
    const el = svg({ state: "red", led: null, shape: board, pxPerMm: 1, footprintPx: 95 });
    const wheels = [...el.querySelectorAll('[data-layer="wheel"]')].map((w) =>
      w.getAttribute("points"),
    );
    expect(wheels[0]).toBe("30.25,-31.5 47.75,-31.5 47.75,-75.5 30.25,-75.5");
    expect(wheels[1]).toBe("-47.75,-31.5 -30.25,-31.5 -30.25,-75.5 -47.75,-75.5");
  });

  it("puts the board where the pose puts it, not on the fix", () => {
    const el = svg({ state: "red", led: null, shape: board, pxPerMm: 1, footprintPx: 95 });
    const points = el
      .querySelector('[data-layer="board"]')!
      .getAttribute("points")!;
    // The rear edge of a bot facing heading 0 is 76.5 mm back from its fix.
    expect(points).toContain("-76.5");
    // The photodiode is the origin, so the mark needs no placing at all.
    for (const dot of el.querySelectorAll('[data-layer="sensor-mark"] circle')) {
      expect(dot.getAttribute("cx")).toBeNull();
      expect(dot.getAttribute("cy")).toBeNull();
    }
  });

  it("draws the small fallback as a rimless disc at the board's centre", () => {
    const el = svg({ state: "red", led: null, shape: { kind: "mark", body }, pxPerMm: 0.1, footprintPx: 9.5 });
    expect(el.querySelectorAll("polygon")).toHaveLength(0);
    expect(el.querySelector("rect")).toBeNull();
    const mark = el.querySelector('[data-layer="mark"]')!;
    expect(mark.tagName).toBe("circle");
    expect(parseFloat(mark.getAttribute("r")!)).toBeCloseTo(9.5 / 2, 6);
    // Centred 29 mm behind the fix, so a mark stands where the robot does.
    expect(parseFloat(mark.getAttribute("cy")!)).toBeCloseTo(-2.9, 6);
    // No rim: the white rim is what marks out a sensor point.
    expect(mark.getAttribute("stroke")).toBeNull();
  });

  it("turns the small fallback's heading bar with the robot", () => {
    for (const [heading, dx, dy] of [
      [0, 0, 1],
      [90, -1, 0],
      [-90, 1, 0],
      [180, 0, -1],
    ]) {
      const turned = botBody(pose(heading))!;
      const el = svg({ state: "red", led: null, shape: { kind: "mark", body: turned }, pxPerMm: 0.1, footprintPx: 12 });
      const bar = el.querySelector('[data-layer="heading"]')!;
      const vx = parseFloat(bar.getAttribute("x2")!) - parseFloat(bar.getAttribute("x1")!);
      const vy = parseFloat(bar.getAttribute("y2")!) - parseFloat(bar.getAttribute("y1")!);
      const n = Math.hypot(vx, vy);
      expect(vx / n).toBeCloseTo(dx, 6);
      expect(vy / n).toBeCloseTo(dy, 6);
      // From the disc's centre to its edge.
      expect(n).toBeGreaterThan(4);
      expect(n).toBeLessThanOrEqual(6);
      cleanup();
    }
  });

  it("draws the disc about the board's centre, with its heading and sensor mark", () => {
    const el = svg({ state: "red", led: null, shape: { kind: "disc", body, radiusPx: 20 }, pxPerMm: 0.4, footprintPx: 40 });
    const disc = el.querySelector('[data-layer="disc"]')!;
    expect(parseFloat(disc.getAttribute("cy")!)).toBeCloseTo(-29 * 0.4, 6);
    expect(el.querySelector('[data-layer="heading"]')).not.toBeNull();
    expect(el.querySelector('[data-layer="sensor-mark"]')).not.toBeNull();
  });

  it("draws the sensor point at a fixed size", () => {
    for (const pxPerMm of [0.05, 2]) {
      const el = svg({
        state: "red", led: null,
        shape: { kind: "sensor", ringPx: null, corePx: null, crowded: false, bar: null },
        pxPerMm,
        footprintPx: BOT_MIN_PX,
      });
      expect(el.querySelectorAll("polygon")).toHaveLength(0);
      const point = el.querySelector('[data-layer="sensor"]')!;
      expect(2 * parseFloat(point.getAttribute("r")!)).toBe(SENSOR_POINT_PX);
      cleanup();
    }
  });

  it("draws the ring dashed and the core solid around the point", () => {
    const el = svg({
      state: "red", led: null,
      shape: { kind: "sensor", ringPx: 60, corePx: 12, crowded: false, bar: null },
      pxPerMm: 1,
      footprintPx: 120,
    });
    expect(el.querySelector('[data-layer="reach"]')!.getAttribute("stroke-dasharray")).toBeTruthy();
    expect(el.querySelector('[data-layer="core"]')!.getAttribute("stroke-dasharray")).toBeNull();
    expect(el.querySelector('[data-layer="sensor"]')).not.toBeNull();
  });

  it("draws a known heading as a white bar from the point, under it", () => {
    const el = svg({
      state: "red", led: null,
      shape: {
        kind: "sensor",
        ringPx: 60,
        corePx: null,
        crowded: false,
        bar: { dir: { x: -1, y: 0 }, lengthPx: 60 },
      },
      pxPerMm: 1,
      footprintPx: 120,
    });
    const bar = el.querySelector('[data-layer="sensor-heading"]')!;
    expect(bar.getAttribute("x1")).toBe("0");
    expect(parseFloat(bar.getAttribute("x2")!)).toBeCloseTo(-60, 6);
    expect(parseFloat(bar.getAttribute("y2")!)).toBeCloseTo(0, 6);
    const all = [...el.querySelectorAll("[data-layer]")].map((n) => n.getAttribute("data-layer"));
    expect(all.indexOf("sensor-heading")).toBeLessThan(all.indexOf("sensor"));
  });

  it("draws no bar on a point whose heading is unknown", () => {
    const el = svg({
      state: "red", led: null,
      shape: { kind: "sensor", ringPx: 60, corePx: null, crowded: false, bar: null },
      pxPerMm: 1,
      footprintPx: 120,
    });
    expect(el.querySelectorAll("line")).toHaveLength(0);
  });

  it("lays the dashed ring over a solid casing of the same radius", () => {
    const el = svg({
      state: "red", led: null,
      shape: { kind: "sensor", ringPx: 60, corePx: null, crowded: false, bar: null },
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

describe("the colour rule, the same at every level", () => {
  const STATE = "#22c55e";
  const RED = { red: 255, green: 0, blue: 0 };
  const svg = (props: Parameters<typeof BotGlyph>[0]) =>
    render(<BotGlyph {...props} />).container.querySelector("svg")!;
  const body = botBody(pose())!;
  const sensor = (bar: boolean) =>
    ({
      kind: "sensor",
      ringPx: 60,
      corePx: null,
      crowded: false,
      bar: bar ? { dir: { x: 0, y: 1 }, lengthPx: 60 } : null,
    }) as const;
  // Every level, as the map draws it: the board, the small circle at 11 and
  // 16 px, the crowd disc, and the sensor point with and without a heading.
  const levels = [
    ["board", { shape: { kind: "board", body } as const, pxPerMm: 1, footprintPx: 95 }],
    ["circle at 11 px", { shape: { kind: "mark", body } as const, pxPerMm: 11 / 95, footprintPx: 11 }],
    ["circle at 16 px", { shape: { kind: "mark", body } as const, pxPerMm: 16 / 95, footprintPx: 15.9 }],
    ["disc", { shape: { kind: "disc", body, radiusPx: 20 } as const, pxPerMm: 0.4, footprintPx: 40 }],
    ["sensor point", { shape: sensor(false), pxPerMm: 1, footprintPx: 120 }],
    ["sensor point with a heading", { shape: sensor(true), pxPerMm: 1, footprintPx: 120 }],
  ] as const;
  const FILL_LAYER = { board: "board", mark: "mark", disc: "disc", sensor: "sensor" } as const;

  for (const [name, level] of levels) {
    it(`fills the ${name} in the state colour`, () => {
      const el = svg({ state: STATE, led: RED, ...level });
      const fill = el.querySelector(`[data-layer="${FILL_LAYER[level.shape.kind]}"]`)!;
      expect(fill.getAttribute("fill")).toBe(STATE);
    });

    it(`carries exactly one LED mark on the ${name}, at the photodiode`, () => {
      const el = svg({ state: STATE, led: RED, ...level });
      const marks = el.querySelectorAll('[data-layer="sensor-mark"]');
      expect(marks).toHaveLength(1);
      expect(marks[0].getAttribute("data-led")).toBe("rgb(255,0,0)");
      for (const c of marks[0].querySelectorAll("circle")) {
        expect(c.getAttribute("cx")).toBeNull();
        expect(c.getAttribute("cy")).toBeNull();
      }
      // A white rim inside a dark one: it reads on a fill of its own colour.
      const [halo, dot] = [...marks[0].querySelectorAll("circle")];
      expect(dot.getAttribute("stroke")).toBe("rgba(255,255,255,.95)");
      expect(parseFloat(halo.getAttribute("r")!)).toBeGreaterThan(parseFloat(dot.getAttribute("r")!));
    });

    it(`draws the ${name}'s mark hollow when the LED colour is unknown`, () => {
      const el = svg({ state: STATE, led: null, ...level });
      const mark = el.querySelector('[data-layer="sensor-mark"]')!;
      expect(mark.getAttribute("data-led")).toBe("unknown");
      for (const c of mark.querySelectorAll("circle")) expect(c.getAttribute("fill")).toBe("none");
    });

    it(`draws the ${name}'s mark near-black for an LED commanded off`, () => {
      const el = svg({ state: STATE, led: { red: 0, green: 0, blue: 0 }, ...level });
      expect(el.querySelector('[data-layer="sensor-mark"]')!.getAttribute("data-led")).toBe(LED_OFF);
    });

    it(`draws no centre dot on the ${name}`, () => {
      const el = svg({ state: STATE, led: RED, ...level });
      expect(el.querySelector('[data-layer="photodiode"]')).toBeNull();
    });
  }

  it("carries a known heading as a white bar, except on the board, whose shape does", () => {
    for (const [name, level] of levels) {
      const el = svg({ state: STATE, led: RED, ...level });
      const bars = [...el.querySelectorAll("line")].filter(
        (l) => !l.getAttribute("data-layer")!.endsWith("casing"),
      );
      const expected = name === "board" || name === "sensor point" ? 0 : 1;
      expect(bars, name).toHaveLength(expected);
      for (const bar of bars) expect(bar.getAttribute("stroke")).toBe("rgba(255,255,255,.95)");
      cleanup();
    }
  });

  it("puts the circle's and the disc's mark on the bar", () => {
    for (const [, level] of levels.filter(([, l]) => l.shape.kind === "mark" || l.shape.kind === "disc")) {
      const el = svg({ state: STATE, led: RED, ...level });
      const bar = el.querySelector('[data-layer="heading"]')!;
      const [x1, y1, x2, y2] = ["x1", "y1", "x2", "y2"].map((k) => parseFloat(bar.getAttribute(k)!));
      // The photodiode is the origin: it lies on the segment from the centre.
      const cross = x1 * (y2 - y1) - y1 * (x2 - x1);
      const along = -(x1 * (x2 - x1) + y1 * (y2 - y1)) / ((x2 - x1) ** 2 + (y2 - y1) ** 2);
      expect(Math.abs(cross)).toBeLessThan(1e-6);
      expect(along).toBeGreaterThan(0);
      expect(along).toBeLessThan(1);
      cleanup();
    }
  });

  it("keeps the small circle's mark small, so the fill and the bar still show", () => {
    for (const footprintPx of [11, 16]) {
      const el = svg({ state: STATE, led: RED, shape: { kind: "mark", body }, pxPerMm: footprintPx / 95, footprintPx });
      const halo = el.querySelector('[data-layer="sensor-mark"] circle')!;
      expect(2 * parseFloat(halo.getAttribute("r")!)).toBeLessThan(footprintPx * 0.4);
      cleanup();
    }
  });

  it("rims the sensor point in the state colour around the LED mark", () => {
    const el = svg({ state: STATE, led: RED, shape: sensor(false), pxPerMm: 1, footprintPx: 120 });
    const point = el.querySelector('[data-layer="sensor"]')!;
    const halo = el.querySelector('[data-layer="sensor-mark"] circle')!;
    expect(parseFloat(point.getAttribute("r")!)).toBeGreaterThan(parseFloat(halo.getAttribute("r")!) + 1);
  });

  it("colours the ring and the core by state, not by LED", () => {
    const el = svg({ state: STATE, led: RED, shape: { ...sensor(false), corePx: 20 }, pxPerMm: 1, footprintPx: 120 });
    expect(el.querySelector('[data-layer="reach"]')!.getAttribute("stroke")).toBe(STATE);
    expect(el.querySelector('[data-layer="core"]')!.getAttribute("fill")).toBe(STATE);
  });
});

describe("the LED colour a mark is filled with", () => {
  it("is the commanded colour, near-black when off, and nothing when unknown", () => {
    expect(ledFill({ red: 1, green: 2, blue: 3 })).toBe("rgb(1,2,3)");
    expect(ledFill({ red: 0, green: 0, blue: 0 })).toBe(LED_OFF);
    expect(ledFill(null)).toBeNull();
  });
});
