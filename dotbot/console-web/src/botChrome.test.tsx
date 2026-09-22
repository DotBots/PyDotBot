import React, { useState } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { botFootprintPx } from "./BotGlyph";
import { pxPerMm } from "./grid";
import { MapView } from "./MapView";
import type { Area, BotPose, LH2Position, Site, UnifiedBot } from "./types";
import { Camera, SITE_CAMERA, viewGeom } from "./zoom";

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
    axle: place({ x: 0, y: -53.5 }),
    centre: place({ x: 0, y: -29 }),
    nose: place({ x: 0, y: 18.5 }),
    led: place({ x: 0, y: 5.5 }),
    outline: V3_AT_ORIGIN.map(place),
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
  planned?: { ids: string[]; waypoints: LH2Position[]; led: string | null }[];
  robotShapes?: boolean;
}

const Harness: React.FC<HarnessProps> = ({
  bots,
  selection = new Set(),
  from = SITE_CAMERA,
  planned = [],
  robotShapes,
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
      robotShapes={robotShapes}
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
    const planned = [{ ids: ["b"], waypoints: [{ x: 100, y: 100 }], led: null }];
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
    for (const cam of [SITE_CAMERA, near]) {
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

  it("draws the battery bar and drive dot on a board, not on a dot", () => {
    render(<Harness bots={fleet()} from={near} />);
    expect(screen.getByTestId("battery-a")).toBeInTheDocument();
    expect(screen.getByTestId("drive-a")).toBeInTheDocument();
    cleanup();
    render(<Harness bots={fleet()} />);
    expect(screen.queryByTestId("battery-a")).not.toBeInTheDocument();
    expect(screen.queryByTestId("drive-a")).not.toBeInTheDocument();
  });

  it("keeps the reset badge on a dot, where a crash still has to be found", () => {
    render(<Harness bots={[bot("a", { x: 500, y: 500 }, { severity: "crashed", resetCause: "hard fault" })]} />);
    expect(screen.getByTitle("Last reset: hard fault")).toBeInTheDocument();
  });

  it("sizes a waypoint diamond to the robot it belongs to", () => {
    const fleet = [bot("a", { x: 500, y: 500 }, { waypoints: [{ x: 600, y: 600 }] })];
    render(<Harness bots={fleet} selection={new Set(["a"])} />);
    expect(parseFloat(screen.getByTestId("waypoint-a-0").style.width)).toBe(5);
    cleanup();
    render(<Harness bots={fleet} selection={new Set(["a"])} from={near} />);
    const footprint = botFootprintPx(pxPerMm("x", VIEWPORT, GEOM, near), V3_SPAN_MM);
    expect(parseFloat(screen.getByTestId("waypoint-a-0").style.width)).toBeCloseTo(footprint * 0.35, 3);
  });
});

describe("what the map draws a robot from", () => {
  const glyph = (id: string) => screen.getByTestId(`glyph-${id}`);
  const near: Camera = { scale: 20, tx: 0, ty: 0 };

  it("is the body the controller shipped, in its three layers", () => {
    render(<Harness bots={[bot("a", { x: 500, y: 500 })]} from={near} />);
    const svg = glyph("a").querySelector("svg")!;
    expect(svg.querySelectorAll("polygon")).toHaveLength(1);
    expect(svg.querySelectorAll("line")).toHaveLength(1);
    expect(svg.querySelectorAll("circle")).toHaveLength(1);
  });

  it("is a plain sensor dot for a bot whose heading the robot never reported", () => {
    const headingless = bot("a", { x: 500, y: 500 }, {
      heading: null,
      pose: { ...bodyPose({ x: 500, y: 500 }, 0), heading_source: "none" },
    });
    render(<Harness bots={[headingless]} from={near} />);
    const svg = glyph("a").querySelector("svg")!;
    expect(svg.querySelectorAll("polygon")).toHaveLength(0);
    expect(svg.querySelectorAll("circle")).toHaveLength(1);
  });

  it("is a plain sensor dot for a bot with no body at all", () => {
    render(<Harness bots={[bot("a", { x: 500, y: 500 }, { pose: null })]} from={near} />);
    expect(glyph("a").querySelector("polygon")).toBeNull();
  });

  it("is a plain mark for every bot when robot shapes are turned off", () => {
    render(
      <Harness
        bots={[bot("a", { x: 500, y: 500 }), bot("b", { x: 900, y: 900 })]}
        robotShapes={false}
        from={near}
      />,
    );
    for (const id of ["a", "b"]) {
      expect(glyph(id).querySelector("polygon")).toBeNull();
      expect(glyph(id).querySelector("circle")).not.toBeNull();
    }
  });
});
