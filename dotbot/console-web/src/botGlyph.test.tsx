import React from "react";
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import {
  BOT_MIN_PX,
  BotGlyph,
  GLYPH_CROWD_BOTS,
  GLYPH_DETAIL_PX,
  botBody,
  botFootprintPx,
  glyphLevel,
} from "./BotGlyph";
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
    axle: place({ x: 0, y: -53.5 }),
    centre: place({ x: 0, y: -29 }),
    nose: place({ x: 0, y: 18.5 }),
    led: place({ x: 0, y: 5.5 }),
    outline: V3_AT_ORIGIN.map(place),
    ...over,
  };
};

describe("the body a pose describes", () => {
  it("is the payload's own path, put back on the fix it belongs to", () => {
    const body = botBody(pose(), SENSOR)!;
    expect(body.outline).toEqual(V3_AT_ORIGIN);
    expect(body.centre).toEqual({ x: 0, y: -29 });
    expect(body.nose).toEqual({ x: 0, y: 18.5 });
  });

  it("is the robot's own size, not the box it happens to occupy", () => {
    // 95 mm long by 94 wide, whichever way it faces. Measured in the arena
    // frame instead, a body turned 45 degrees spans 134 mm and the chrome
    // around it would breathe as the robot turned.
    for (const heading of [0, 37, 90, 180, -135]) {
      const turned = botBody(pose(heading), SENSOR)!;
      expect(turned.spanMm).toBeCloseTo(95, 6);
    }
  });

  it("is nothing at all without a heading, which is the whole rule", () => {
    expect(botBody(pose(0, { heading_source: "none" }), SENSOR)).toBeNull();
  });

  it("is nothing without a pose or without a fix to hang it on", () => {
    expect(botBody(undefined, SENSOR)).toBeNull();
    expect(botBody(null, SENSOR)).toBeNull();
    expect(botBody(pose(), null)).toBeNull();
    expect(botBody(pose(0, { outline: [] }), SENSOR)).toBeNull();
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

describe("the glyph a level draws", () => {
  const svg = (props: Parameters<typeof BotGlyph>[0]) =>
    render(<BotGlyph {...props} />).container.querySelector("svg")!;

  const body = botBody(pose(), SENSOR);

  it("draws the three layers of one robot at full detail", () => {
    const el = svg({ color: "red", body, pxPerMm: 1, footprintPx: 95 });
    // The board, the line out to its nose, and the photodiode the fix came
    // from - the same three the camera layer draws its own detection in.
    expect(el.querySelectorAll("polygon")).toHaveLength(1);
    expect(el.querySelectorAll("line")).toHaveLength(1);
    expect(el.querySelectorAll("circle")).toHaveLength(1);
  });

  it("puts the board where the pose puts it, not on the fix", () => {
    const el = svg({ color: "red", body, pxPerMm: 1, footprintPx: 95 });
    const points = el.querySelector("polygon")!.getAttribute("points")!;
    // The rear edge of a bot facing heading 0 is 76.5 mm back from its fix.
    expect(points).toContain("-76.5");
    // The photodiode is the origin, so the dot needs no placing at all.
    const dot = el.querySelector("circle")!;
    expect(dot.getAttribute("cx")).toBeNull();
    expect(dot.getAttribute("cy")).toBeNull();
  });

  it("draws a mark at the board's centre where the outline would not read", () => {
    const el = svg({
      color: "red",
      body,
      pxPerMm: 0.1,
      footprintPx: 9.5,
      level: "dot",
    });
    expect(el.querySelectorAll("polygon")).toHaveLength(0);
    const rect = el.querySelector("rect")!;
    // Centred 29 mm behind the fix, so a mark stands where the robot does.
    expect(parseFloat(rect.getAttribute("y")!)).toBeCloseTo(-2.9 - 9.5 / 2, 6);
  });

  it("draws a bot with no body as the photodiode point and nothing else", () => {
    for (const level of ["detail", "dot"] as const) {
      const el = svg({
        color: "red",
        body: null,
        pxPerMm: 1,
        footprintPx: BOT_MIN_PX,
        level,
      });
      expect(el.querySelectorAll("polygon")).toHaveLength(0);
      expect(el.querySelectorAll("rect")).toHaveLength(0);
      expect(el.querySelectorAll("circle")).toHaveLength(1);
      cleanup();
    }
  });
});
