import React, { useState } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { botFootprintPx } from "./BotGlyph";
import { pxPerMm } from "./grid";
import { MapView, WAYPOINT_MAX_PX, WAYPOINT_MIN_PX, WAYPOINT_OF_BODY } from "./MapView";
import type { RobotDrawing } from "./robotDrawing";
import type { Area, BotPose, LH2Position, Site, UnifiedBot } from "./types";
import { Camera, FRAME_CAMERA, viewGeom } from "./zoom";

const ARENA: Area = { x: 0, y: 0, w: 2000, h: 2000, name: "arena" };
const C405: Site = {
  name: "c405-arena",
  anchor: "the arena's top-left corner",
  extent_mm: [2000, 4000],
  areas: [ARENA],
};
const VIEWPORT: Area = { x: -2000, y: -2000, w: 6000, h: 8000 };
const CANVAS = { w: 900, h: 600 };
const GEOM = viewGeom(CANVAS.w, CANVAS.h, VIEWPORT);

// A v3 body as the controller ships it: the board path around a fix, already
// rotated, in frame millimetres. 95 mm long and 94 wide, so at heading 45 it
// is the awkward case the chrome has to keep hugging.
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
const V3_SPAN_MM = 95;

// The body of a bot standing at `at` facing `heading`, rotated the way the
// controller rotates it.
const bodyPose = (at: LH2Position, heading = 45): BotPose => {
  const theta = (heading * Math.PI) / 180;
  const place = (p: LH2Position): LH2Position => ({
    x: at.x + p.x * Math.cos(theta) - p.y * Math.sin(theta),
    y: at.y + p.x * Math.sin(theta) + p.y * Math.cos(theta),
  });
  return {
    heading_deg: heading,
    heading_source: "travel",
    photodiode: at,
    axle: place({ x: 0, y: -53.5 }),
    centre: place({ x: 0, y: -29 }),
    nose: place({ x: 0, y: 18.5 }),
    led: place({ x: 0, y: 5.5 }),
    outline: V3_AT_ORIGIN.map(place),
    wheels: [],
    // The radii the controller ships with every pose, whatever its heading.
    reach_mm: 89.33,
    core_mm: 18.5,
    envelope_mm: 95,
  };
};

const bot = (id: string, position: LH2Position, extra: Partial<UnifiedBot> = {}): UnifiedBot => ({
  id,
  state: "Running",
  link: "active",
  position,
  heading: 45,
  pose: bodyPose(position),
  battery: 2.9,
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
  batteryPct: 80,
  batteryLevel: "ok",
  swarmit: null,
  ...extra,
});

interface HarnessProps {
  bots: UnifiedBot[];
  selection?: Set<string>;
  from?: Camera;
  planned?: { key: string; ids: string[]; waypoints: LH2Position[]; led: string | null }[];
  robotDrawing?: RobotDrawing;
}

const Harness: React.FC<HarnessProps> = ({
  bots,
  selection = new Set(),
  from = FRAME_CAMERA,
  planned = [],
  robotDrawing,
}) => {
  const [cam, setCam] = useState<Camera>(from);
  return (
    <MapView
      bots={bots}
      viewport={VIEWPORT}
      siteAreas={C405.areas}
      hiddenAreas={new Set()}
      siteExtent={{ x: 0, y: 0, w: 2000, h: 4000, name: C405.name }}
      selection={selection}
      layers={{
        batteryBars: true,
        waypoints: true,
        hotSpots: false,
        dotBots: true,
        trails: false,
        crashedOnly: false,
      }}
      robotDrawing={robotDrawing}
      plannedMissions={planned}
      cam={cam}
      setCam={setCam}
      onGeom={() => {}}
      onSelect={() => {}}
      onAddWaypoint={() => {}}
      site={C405}
      onZoom={() => {}}
    />
  );
};

// jsdom measures every element as zero, so the canvas is given a size.
let rectSpy: ReturnType<typeof vi.spyOn>;
beforeEach(() => {
  rectSpy = vi
    .spyOn(HTMLElement.prototype, "getBoundingClientRect")
    .mockReturnValue({
      width: CANVAS.w,
      height: CANVAS.h,
      top: 0,
      left: 0,
      right: CANVAS.w,
      bottom: CANVAS.h,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    } as DOMRect);
});
afterEach(() => {
  rectSpy.mockRestore();
  cleanup();
});

describe("waypoints on the map", () => {
  const wp = [{ x: 600, y: 600 }, { x: 900, y: 900 }];
  const fleet = () => [
    bot("a", { x: 500, y: 500 }, { waypoints: wp }),
    bot("b", { x: 700, y: 900 }, { waypoints: wp }),
  ];
  const drawn = () =>
    Array.from(document.querySelectorAll('[data-testid^="waypoint-"]')).map(
      (el) => el.getAttribute("data-testid"),
    );

  it("are not drawn at all with nothing selected", () => {
    render(<Harness bots={fleet()} />);
    expect(drawn()).toEqual([]);
  });

  it("are drawn for the selected robots only", () => {
    render(<Harness bots={fleet()} selection={new Set(["a"])} />);
    expect(drawn()).toEqual(["waypoint-a-0", "waypoint-a-1"]);
  });

  it("show a queued mission only while one of its robots is selected", () => {
    const planned = [{ key: "b", ids: ["b"], waypoints: [{ x: 100, y: 100 }], led: null }];
    render(<Harness bots={fleet()} planned={planned} />);
    expect(screen.queryByTestId("planned-b-0")).not.toBeInTheDocument();
    cleanup();
    render(<Harness bots={fleet()} planned={planned} selection={new Set(["b"])} />);
    expect(screen.getByTestId("planned-b-0")).toBeInTheDocument();
  });
});

describe("what is drawn around a robot", () => {
  // At the whole-site zoom a robot here is the 8 px floor, a dot; at this
  // scale it is more than a hundred pixels, a board.
  const near: Camera = { scale: 20, tx: 0, ty: 0 };
  const fleet = () => [bot("a", { x: 500, y: 500 })];

  it("hugs the selected robot's footprint with the ring, at any zoom", () => {
    for (const cam of [FRAME_CAMERA, near]) {
      render(<Harness bots={fleet()} selection={new Set(["a"])} from={cam} />);
      const footprint = botFootprintPx(pxPerMm("x", VIEWPORT, GEOM, cam), V3_SPAN_MM);
      const ring = screen.getByTestId("selection-a");
      expect(parseFloat(ring.style.width)).toBeCloseTo(footprint + 6, 3);
      expect(parseFloat(ring.style.height)).toBeCloseTo(footprint + 6, 3);
      cleanup();
    }
  });

  it("turns the ring with the board", () => {
    render(<Harness bots={fleet()} selection={new Set(["a"])} from={near} />);
    expect(screen.getByTestId("selection-a").style.transform).toContain("rotate(225deg)");
  });

  it("draws the battery bar on a board, not on a dot", () => {
    render(<Harness bots={fleet()} from={near} />);
    expect(screen.getByTestId("battery-a")).toBeInTheDocument();
    cleanup();
    render(<Harness bots={fleet()} />);
    expect(screen.queryByTestId("battery-a")).not.toBeInTheDocument();
  });

  it("keeps the reset badge on a dot, where a crash still has to be found", () => {
    render(<Harness bots={[bot("a", { x: 500, y: 500 }, { severity: "crashed", resetCause: "hard fault" })]} />);
    expect(screen.getByTitle("Last reset: hard fault")).toBeInTheDocument();
  });

  it("sizes a waypoint diamond to the robot's body, between a floor and a cap", () => {
    const fleet = [bot("a", { x: 500, y: 500 }, { waypoints: [{ x: 600, y: 600 }] })];
    const width = () => parseFloat(screen.getByTestId("waypoint-a-0").style.width);
    render(<Harness bots={fleet} selection={new Set(["a"])} />);
    expect(width()).toBe(WAYPOINT_MIN_PX);
    cleanup();
    // A scale where the body is between the two bounds.
    const mid: Camera = { scale: 5, tx: 0, ty: 0 };
    render(<Harness bots={fleet} selection={new Set(["a"])} from={mid} />);
    const body = botFootprintPx(pxPerMm("x", VIEWPORT, GEOM, mid), V3_SPAN_MM);
    expect(width()).toBeCloseTo(body * WAYPOINT_OF_BODY, 3);
    cleanup();
    render(<Harness bots={fleet} selection={new Set(["a"])} from={near} />);
    expect(width()).toBe(WAYPOINT_MAX_PX);
  });

  it("sizes a waypoint from the body, not the ring, for a robot drawn as its sensor", () => {
    const fleet = [bot("a", { x: 500, y: 500 }, { waypoints: [{ x: 600, y: 600 }] })];
    const width = () => parseFloat(screen.getByTestId("waypoint-a-0").style.width);
    const mid: Camera = { scale: 5, tx: 0, ty: 0 };
    render(<Harness bots={fleet} selection={new Set(["a"])} from={mid} />);
    const asBody = width();
    cleanup();
    render(
      <Harness
        bots={fleet}
        selection={new Set(["a"])}
        from={mid}
        robotDrawing={{ mode: "sensor", footprint: true }}
      />,
    );
    expect(width()).toBeCloseTo(asBody, 3);
    expect(width()).toBeLessThan(WAYPOINT_MAX_PX);
  });
});

describe("what the map draws a robot from", () => {
  const glyph = (id: string) => screen.getByTestId(`glyph-${id}`);
  const near: Camera = { scale: 20, tx: 0, ty: 0 };

  it("is the body the controller shipped, with its sensor mark", () => {
    render(<Harness bots={[bot("a", { x: 500, y: 500 })]} from={near} />);
    const svg = glyph("a").querySelector("svg")!;
    expect(svg.querySelectorAll('[data-layer="board"]')).toHaveLength(1);
    expect(svg.querySelectorAll("line")).toHaveLength(0);
    expect(svg.querySelectorAll('[data-layer="sensor-mark"]')).toHaveLength(1);
  });

  const headingless = (id: string, at: LH2Position) =>
    bot(id, at, {
      heading: null,
      pose: { ...bodyPose(at, 0), heading_source: "none" },
    });
  const shape = (id: string) => glyph(id).getAttribute("data-shape");
  const layer = (id: string, name: string) =>
    glyph(id).querySelector(`[data-layer="${name}"]`);
  const noFootprint: RobotDrawing = { mode: "body", footprint: false };

  it("is the sensor point alone for a bot whose heading the robot never reported", () => {
    render(
      <Harness bots={[headingless("a", { x: 500, y: 500 })]} robotDrawing={noFootprint} from={near} />,
    );
    const svg = glyph("a").querySelector("svg")!;
    expect(svg.querySelectorAll("polygon")).toHaveLength(0);
    expect(svg.querySelectorAll("line")).toHaveLength(0);
    expect(layer("a", "sensor")).not.toBeNull();
    expect(layer("a", "reach")).toBeNull();
  });

  it("is the sensor point for a bot with no body at all", () => {
    render(<Harness bots={[bot("a", { x: 500, y: 500 }, { pose: null })]} from={near} />);
    expect(glyph("a").querySelector("polygon")).toBeNull();
    expect(shape("a")).toBe("sensor");
  });

  it("marks the LED colour the controller holds, hollow when it holds none", () => {
    render(
      <Harness
        bots={[
          bot("a", { x: 500, y: 500 }, { led: { red: 255, green: 0, blue: 200 } }),
          bot("b", { x: 900, y: 900 }, { led: null }),
        ]}
        from={near}
      />,
    );
    expect(layer("a", "sensor-mark")!.getAttribute("data-led")).toBe("rgb(255,0,200)");
    expect(layer("b", "sensor-mark")!.getAttribute("data-led")).toBe("unknown");
    expect(screen.queryByTestId("drive-a")).not.toBeInTheDocument();
  });

  it("falls back to the sensor point per robot, not per fleet", () => {
    render(
      <Harness
        bots={[bot("a", { x: 500, y: 500 }), headingless("b", { x: 900, y: 900 })]}
        from={near}
      />,
    );
    expect(shape("a")).toBe("board");
    expect(shape("b")).toBe("sensor");
  });

  it("is the sensor point for every bot in Sensor mode", () => {
    render(
      <Harness
        bots={[bot("a", { x: 500, y: 500 }), bot("b", { x: 900, y: 900 })]}
        robotDrawing={{ mode: "sensor", footprint: false }}
        from={near}
      />,
    );
    for (const id of ["a", "b"]) {
      expect(glyph(id).querySelector("polygon")).toBeNull();
      expect(shape(id)).toBe("sensor");
    }
  });

  it("keeps the battery bar on a sensor point", () => {
    render(<Harness bots={[headingless("a", { x: 500, y: 500 })]} from={near} />);
    expect(screen.getByTestId("battery-a")).toBeInTheDocument();
  });
});

describe("the fallback for a board that cannot be drawn", () => {
  const glyph = (id: string) => screen.getByTestId(`glyph-${id}`);
  const shape = (id: string) => glyph(id).getAttribute("data-shape");
  const near: Camera = { scale: 20, tx: 0, ty: 0 };
  const crowd = () =>
    Array.from({ length: 201 }, (_, i) => bot(`c${i}`, { x: 100 + i * 5, y: 500 }));

  it("is the disc with a heading bar where the board is too small", () => {
    render(<Harness bots={[bot("a", { x: 500, y: 500 })]} from={FRAME_CAMERA} />);
    expect(shape("a")).toBe("mark");
    expect(glyph("a").querySelector("rect")).toBeNull();
    expect(glyph("a").querySelector('circle[data-layer="mark"]')).not.toBeNull();
    expect(glyph("a").querySelector('[data-layer="heading"]')).not.toBeNull();
  });

  it("is the real-size disc with its heading where a crowd hides a readable board", () => {
    render(<Harness bots={crowd()} from={near} />);
    expect(shape("c0")).toBe("disc");
    const disc = glyph("c0").querySelector('[data-layer="disc"]')!;
    const perMm = pxPerMm("x", VIEWPORT, GEOM, near);
    expect(parseFloat(disc.getAttribute("r")!)).toBeCloseTo((95 * perMm) / 2, 3);
    expect(glyph("c0").querySelector('[data-layer="heading"]')).not.toBeNull();
    expect(glyph("c0").querySelector('[data-layer="sensor-mark"]')).not.toBeNull();
  });

  it("is still the mark in a crowd where the board would be too small anyway", () => {
    render(<Harness bots={crowd()} from={FRAME_CAMERA} />);
    expect(shape("c0")).toBe("mark");
  });
});

describe("the possible footprint", () => {
  const glyph = (id: string) => screen.getByTestId(`glyph-${id}`);
  const layer = (id: string, name: string) =>
    glyph(id).querySelector(`[data-layer="${name}"]`);
  const near: Camera = { scale: 20, tx: 0, ty: 0 };
  const headingless = (id: string, at: LH2Position) =>
    bot(id, at, {
      heading: null,
      pose: { ...bodyPose(at, 0), heading_source: "none" },
    });

  it("rings a robot drawn as its sensor with the reach and the core the host sent", () => {
    render(<Harness bots={[headingless("a", { x: 500, y: 500 })]} from={near} />);
    const perMm = pxPerMm("x", VIEWPORT, GEOM, near);
    expect(parseFloat(layer("a", "reach")!.getAttribute("r")!)).toBeCloseTo(89.33 * perMm, 3);
    expect(parseFloat(layer("a", "core")!.getAttribute("r")!)).toBeCloseTo(18.5 * perMm, 3);
  });

  it("is not drawn around a robot drawn as its body", () => {
    render(
      <Harness
        bots={[bot("a", { x: 500, y: 500 }), headingless("b", { x: 900, y: 900 })]}
        from={near}
      />,
    );
    expect(layer("a", "reach")).toBeNull();
    expect(layer("b", "reach")).not.toBeNull();
  });

  it("is drawn around every robot in Sensor mode", () => {
    render(
      <Harness
        bots={[bot("a", { x: 500, y: 500 })]}
        robotDrawing={{ mode: "sensor", footprint: true }}
        from={near}
      />,
    );
    expect(layer("a", "reach")).not.toBeNull();
  });

  it("is hidden where the ring would be too small to read", () => {
    // At the whole-site zoom the ring is about 12 px across.
    render(<Harness bots={[headingless("a", { x: 500, y: 500 })]} from={FRAME_CAMERA} />);
    expect(layer("a", "reach")).toBeNull();
    expect(layer("a", "core")).toBeNull();
    expect(layer("a", "sensor")).not.toBeNull();
  });

  it("loses its fill in a crowd", () => {
    const crowd = Array.from({ length: 201 }, (_, i) =>
      headingless(`c${i}`, { x: 100 + i * 5, y: 500 }),
    );
    render(<Harness bots={crowd} from={near} />);
    expect(layer("c0", "reach")!.getAttribute("fill")).toBe("none");
    cleanup();
    render(<Harness bots={[headingless("a", { x: 500, y: 500 })]} from={near} />);
    expect(layer("a", "reach")!.getAttribute("fill")).not.toBe("none");
  });
});
