import React, { useState } from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { areaToFraction } from "./frame";
import { frameMm } from "./grid";
import { MapView } from "./MapView";
import { MAP_MODIFIER, Modifier } from "./shortcuts";
import type { Area, BotPose, LH2Position, Site, UnifiedBot, Waypoint } from "./types";
import { HOLD_MS } from "./poseGesture";
import {
  Camera,
  FRAME_CAMERA,
  ZOOM_STEP,
  cameraForArea,
  viewGeom,
  zoomMax,
} from "./zoom";

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
const MAX = zoomMax(C405, VIEWPORT, GEOM);

const bot = (id: string, position: LH2Position, extra: Partial<UnifiedBot> = {}): UnifiedBot => ({
  id,
  state: "Running",
  link: "active",
  position,
  heading: 45,
  battery: 2.9,
  led: null,
  deviceType: "DotBotV3",
  application: 0,
  pose: null,
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

// The keys an event holds for one of the table's modifiers, so a test presses
// whatever the table says rather than a key of its own.
const held = (modifier: Modifier | null) => ({
  shiftKey: modifier === "shift",
  ctrlKey: modifier === "ctrl",
  metaKey: false,
  altKey: modifier === "alt",
});

interface HarnessProps {
  bots?: UnifiedBot[];
  selection?: Set<string>;
  from?: Camera;
  onSelect?: (ids: string[], mode: "replace" | "toggle" | "add") => void;
  onAddWaypoint?: (w: Waypoint) => void;
  planned?: { key: string; ids: string[]; waypoints: Waypoint[]; led: string | null }[];
  onSetHeading?: (key: string, index: number, heading: number | null) => void;
  poseMode?: boolean;
}

const Harness: React.FC<HarnessProps> = ({
  bots = [],
  selection = new Set(),
  from = FRAME_CAMERA,
  onSelect = () => {},
  onAddWaypoint = () => {},
  planned = [],
  onSetHeading,
  poseMode,
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
      plannedMissions={planned}
      cam={cam}
      setCam={setCam}
      onGeom={() => {}}
      onSelect={onSelect}
      onAddWaypoint={onAddWaypoint}
      onSetHeading={onSetHeading}
      poseMode={poseMode}
      site={C405}
      onZoom={() => {}}
    />
  );
};

// jsdom measures every element as zero, so the canvas is given a size and,
// with it, every robot sits at the canvas centre.
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

const canvas = () => screen.getByTestId("camera-layer").parentElement!;
const camera = (): Camera => {
  const t = screen.getByTestId("camera-layer").style.transform;
  const [, tx, ty, scale] =
    /translate\(([-\d.]+)px, ([-\d.]+)px\) scale\(([-\d.]+)\)/.exec(t) ?? [];
  return { scale: Number(scale), tx: Number(tx), ty: Number(ty) };
};
const under = (px: number, py: number, cam: Camera) => ({
  x: frameMm("x", px, VIEWPORT, GEOM, cam),
  y: frameMm("y", py, VIEWPORT, GEOM, cam),
});
const expectCamera = (got: Camera, want: Camera) => {
  expect(got.scale).toBeCloseTo(want.scale, 4);
  expect(got.tx).toBeCloseTo(want.tx, 2);
  expect(got.ty).toBeCloseTo(want.ty, 2);
};
const drag = (
  modifier: Modifier | null,
  from: [number, number],
  to: [number, number],
) => {
  const el = canvas();
  fireEvent.pointerDown(el, { button: 0, clientX: from[0], clientY: from[1], ...held(modifier) });
  fireEvent.pointerMove(el, { clientX: to[0], clientY: to[1], ...held(modifier) });
  fireEvent.pointerUp(el, { clientX: to[0], clientY: to[1], ...held(modifier) });
};

describe("the wheel", () => {
  it("zooms about the pointer with the zoom modifier held", () => {
    render(<Harness />);
    const at = [300, 200] as const;
    const was = under(at[0], at[1], camera());

    fireEvent.wheel(canvas(), {
      deltaY: -100,
      clientX: at[0],
      clientY: at[1],
      ...held(MAP_MODIFIER.zoom),
    });

    const now = camera();
    expect(now.scale).toBeCloseTo(ZOOM_STEP, 6);
    // The point under the pointer is still under the pointer, to well under
    // a screen pixel of floor.
    const mmPerPx = VIEWPORT.w / GEOM.boxW;
    const still = under(at[0], at[1], now);
    expect(Math.abs(still.x - was.x)).toBeLessThan(mmPerPx);
    expect(Math.abs(still.y - was.y)).toBeLessThan(mmPerPx);
  });

  it("zooms out again scrolled the other way, and holds the range", () => {
    render(<Harness from={{ scale: ZOOM_STEP, tx: 0, ty: 0 }} />);
    fireEvent.wheel(canvas(), { deltaY: 100, clientX: 450, clientY: 300, ...held(MAP_MODIFIER.zoom) });
    expect(camera().scale).toBeCloseTo(1, 6);
    fireEvent.wheel(canvas(), { deltaY: 100, clientX: 450, clientY: 300, ...held(MAP_MODIFIER.zoom) });
    expect(camera().scale).toBeCloseTo(1, 6);
  });

  it("does nothing with no modifier, or with another one", () => {
    render(<Harness />);
    fireEvent.wheel(canvas(), { deltaY: -100, clientX: 300, clientY: 200 });
    expectCamera(camera(), FRAME_CAMERA);
    fireEvent.wheel(canvas(), { deltaY: -100, clientX: 300, clientY: 200, ...held(MAP_MODIFIER.select) });
    expectCamera(camera(), FRAME_CAMERA);
  });
});

describe("a gesture the browser cancels", () => {
  it("is dropped rather than left following the cursor", () => {
    const onSelect = vi.fn();
    render(<Harness bots={[bot("a", { x: 500, y: 500 })]} onSelect={onSelect} />);
    const before = camera();
    const el = canvas();

    // A select drag the browser takes over part-way: no pointerup ever comes.
    fireEvent.pointerDown(el, { button: 0, clientX: 100, clientY: 100, ...held(MAP_MODIFIER.select) });
    fireEvent.pointerMove(el, { clientX: 300, clientY: 300, ...held(MAP_MODIFIER.select) });
    fireEvent.pointerCancel(el, { clientX: 300, clientY: 300 });

    // Moving afterwards with nothing held must neither select nor pan.
    fireEvent.pointerMove(el, { clientX: 700, clientY: 500 });

    // The rectangle is the symptom: without a cancel path it stays painted
    // and keeps tracking a cursor with no button held.
    expect(screen.queryByTestId("drag-select")).toBeNull();
    expect(onSelect).not.toHaveBeenCalled();
    expectCamera(camera(), before);
  });
});

describe("a drag with the zoom modifier", () => {
  it("frames the rectangle it drew", () => {
    const onSelect = vi.fn();
    render(<Harness onSelect={onSelect} />);
    const tl = under(300, 200, FRAME_CAMERA);
    const br = under(500, 400, FRAME_CAMERA);

    drag(MAP_MODIFIER.zoom, [300, 200], [500, 400]);

    expectCamera(
      camera(),
      cameraForArea(
        { x: tl.x, y: tl.y, w: br.x - tl.x, h: br.y - tl.y },
        VIEWPORT,
        GEOM,
        MAX,
      ),
    );
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("frames the same rectangle drawn from any corner", () => {
    render(<Harness />);
    drag(MAP_MODIFIER.zoom, [500, 400], [300, 200]);
    const fromBottomRight = camera();
    cleanup();
    render(<Harness />);
    drag(MAP_MODIFIER.zoom, [300, 200], [500, 400]);
    expectCamera(fromBottomRight, camera());
  });

  it("steps in on the point when it does not move", () => {
    render(<Harness />);
    const was = under(300, 200, camera());
    drag(MAP_MODIFIER.zoom, [300, 200], [302, 201]);
    const now = camera();
    expect(now.scale).toBeCloseTo(ZOOM_STEP, 6);
    const mmPerPx = VIEWPORT.w / GEOM.boxW;
    const still = under(300, 200, now);
    expect(Math.abs(still.x - was.x)).toBeLessThan(mmPerPx);
    expect(Math.abs(still.y - was.y)).toBeLessThan(mmPerPx);
  });

  it("is the floor's gesture even when it starts on a robot", () => {
    const onSelect = vi.fn();
    render(
      <Harness bots={[bot("a", { x: 500, y: 500 })]} onSelect={onSelect} />,
    );
    const el = document.getElementById("bot-a")!;
    fireEvent.pointerDown(el, { button: 0, clientX: 450, clientY: 300, ...held(MAP_MODIFIER.zoom) });
    fireEvent.pointerUp(canvas(), { clientX: 450, clientY: 300, ...held(MAP_MODIFIER.zoom) });
    expect(camera().scale).toBeCloseTo(ZOOM_STEP, 6);
    expect(onSelect).not.toHaveBeenCalled();
  });
});

describe("a drag with the select modifier", () => {
  it("adds every robot inside the rectangle to the selection", () => {
    const onSelect = vi.fn();
    render(
      <Harness
        bots={[bot("a", { x: 500, y: 500 }), bot("b", { x: 700, y: 900 })]}
        onSelect={onSelect}
      />,
    );
    // Every robot measures at the canvas centre here, so a rectangle around
    // the centre takes them all and one off to the side takes none.
    drag(MAP_MODIFIER.select, [400, 250], [500, 350]);
    expect(onSelect).toHaveBeenLastCalledWith(["a", "b"], "add");
    drag(MAP_MODIFIER.select, [10, 10], [60, 60]);
    expect(onSelect).toHaveBeenLastCalledWith([], "add");
    expectCamera(camera(), FRAME_CAMERA);
  });

  it("leaves the selection alone when it does not move", () => {
    const onSelect = vi.fn();
    render(<Harness bots={[bot("a", { x: 500, y: 500 })]} onSelect={onSelect} />);
    drag(MAP_MODIFIER.select, [400, 250], [401, 251]);
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("toggles one robot clicked with the same modifier", () => {
    const onSelect = vi.fn();
    render(<Harness bots={[bot("a", { x: 500, y: 500 })]} onSelect={onSelect} />);
    fireEvent.pointerDown(document.getElementById("bot-a")!, { button: 0, ...held(MAP_MODIFIER.select) });
    expect(onSelect).toHaveBeenCalledWith(["a"], "toggle");
  });
});

describe("a plain press", () => {
  it("pans when it moves and clears the selection when it does not", () => {
    const onSelect = vi.fn();
    render(<Harness from={{ scale: 2, tx: 0, ty: 0 }} onSelect={onSelect} />);
    drag(null, [400, 300], [440, 320]);
    expect(camera().tx).toBeCloseTo(40, 6);
    expect(camera().ty).toBeCloseTo(20, 6);
    expect(onSelect).not.toHaveBeenCalled();
    drag(null, [400, 300], [400, 300]);
    expect(onSelect).toHaveBeenCalledWith([], "replace");
  });
});

describe("a panel toggle", () => {
  // The map between both panes, then with the rail or the right pane
  // collapsed: the canvas grows into the space the pane gave up, and its left
  // edge moves with the rail.
  const RAIL_PX = 288;
  const PANE_PX = 272;
  interface Rect {
    left: number;
    w: number;
    h: number;
  }
  const BOTH: Rect = { left: RAIL_PX, w: 420, h: 860 };
  const NO_RAIL: Rect = { left: 0, w: BOTH.w + RAIL_PX, h: BOTH.h };
  const NO_PANE: Rect = { left: RAIL_PX, w: BOTH.w + PANE_PX, h: BOTH.h };
  const size = (c: Rect) =>
    ({
      width: c.w,
      height: c.h,
      top: 0,
      left: c.left,
      right: c.left + c.w,
      bottom: c.h,
      x: c.left,
      y: 0,
      toJSON: () => ({}),
    }) as DOMRect;
  // Where a floor point lands in client pixels, for this canvas and camera.
  const onScreen = (p: LH2Position, c: Rect, cam: Camera) => {
    const g = viewGeom(c.w, c.h, VIEWPORT);
    const { fx, fy } = areaToFraction(p, VIEWPORT);
    return {
      x: c.left + c.w / 2 + cam.tx + cam.scale * g.boxW * (fx - 0.5),
      y: c.h / 2 + cam.ty + cam.scale * g.boxH * (fy - 0.5),
    };
  };
  const FLOOR: LH2Position[] = [
    { x: 1000, y: 1000 },
    { x: 200, y: 1700 },
    { x: 1900, y: 150 },
  ];

  let fire: (() => void) | null = null;
  const Real = globalThis.ResizeObserver;
  beforeEach(() => {
    globalThis.ResizeObserver = class {
      constructor(cb: () => void) {
        fire = cb;
      }
      observe() {}
      unobserve() {}
      disconnect() {}
    } as unknown as typeof ResizeObserver;
  });
  afterEach(() => {
    globalThis.ResizeObserver = Real;
    fire = null;
  });

  for (const [name, open] of [
    ["rail", NO_RAIL],
    ["right pane", NO_PANE],
  ] as const) {
    it(`leaves every floor point where it was on screen when the ${name} toggles`, () => {
      rectSpy.mockReturnValue(size(BOTH));
      const g = viewGeom(BOTH.w, BOTH.h, VIEWPORT);
      const from = cameraForArea(ARENA, VIEWPORT, g, zoomMax(C405, VIEWPORT, g));
      render(<Harness from={from} />);
      const before = camera();

      for (const [was, now] of [
        [BOTH, open],
        [open, BOTH],
      ]) {
        const c0 = camera();
        rectSpy.mockReturnValue(size(now));
        act(() => fire!());
        const c1 = camera();
        for (const p of FLOOR) {
          const a = onScreen(p, was, c0);
          const b = onScreen(p, now, c1);
          expect(b.x - a.x).toBeCloseTo(0, 2);
          expect(b.y - a.y).toBeCloseTo(0, 2);
        }
      }
      expectCamera(camera(), before);
    });
  }
});

// --- placing a waypoint, and a pose -------------------------------------------

// A v3-sized body facing down the map, axle at (500, 500), photodiode ahead.
const POSE: BotPose = {
  heading_deg: 0,
  heading_source: "ekf",
  photodiode: { x: 500, y: 553.5 },
  axle: { x: 500, y: 500 },
  centre: { x: 500, y: 520 },
  nose: { x: 500, y: 570 },
  led: { x: 500, y: 560 },
  outline: [
    { x: 470, y: 460 },
    { x: 530, y: 460 },
    { x: 530, y: 570 },
    { x: 470, y: 570 },
  ],
  wheels: [],
  reach_mm: 90,
  core_mm: 25,
  envelope_mm: 110,
};

const alt = held(MAP_MODIFIER.waypoint);
const rounded = (p: LH2Position) => ({ x: Math.round(p.x), y: Math.round(p.y) });
// A point `r` px out from (x, y), facing `heading` in the robot convention.
const out = (x: number, y: number, heading: number, r = 100) => ({
  clientX: x - r * Math.sin((heading * Math.PI) / 180),
  clientY: y + r * Math.cos((heading * Math.PI) / 180),
});
const placing = () => screen.queryByTestId("placing");

describe("placing a waypoint with the waypoint modifier", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("queues a position on a quick click, on release rather than on press", () => {
    const onAdd = vi.fn();
    render(<Harness onAddWaypoint={onAdd} />);
    fireEvent.pointerDown(canvas(), { button: 0, clientX: 450, clientY: 300, ...alt });
    expect(onAdd).not.toHaveBeenCalled();
    expect(placing()).toHaveAttribute("data-phase", "pressing");
    act(() => vi.advanceTimersByTime(HOLD_MS - 50));
    fireEvent.pointerUp(canvas(), { clientX: 451, clientY: 301, ...alt });
    expect(onAdd).toHaveBeenCalledWith(rounded(under(450, 300, FRAME_CAMERA)));
    expect(onAdd.mock.calls[0][0]).not.toHaveProperty("heading_deg");
    expect(placing()).toBeNull();
  });

  it("turns into a pose held still, which then faces the cursor", () => {
    const onAdd = vi.fn();
    render(<Harness onAddWaypoint={onAdd} />);
    fireEvent.pointerDown(canvas(), { button: 0, clientX: 450, clientY: 300, ...alt });
    act(() => vi.advanceTimersByTime(HOLD_MS));
    expect(placing()).toHaveAttribute("data-phase", "silhouette");
    fireEvent.pointerMove(canvas(), { clientX: 550, clientY: 300 });
    expect(placing()).toHaveAttribute("data-phase", "rotating");
    expect(screen.getByTestId("placing-pose")).toHaveAttribute("data-heading", "270");
    expect(screen.getByTestId("placing-readout")).toHaveTextContent("270°");
    fireEvent.pointerUp(canvas(), { clientX: 550, clientY: 300 });
    expect(onAdd).toHaveBeenCalledWith({
      ...rounded(under(450, 300, FRAME_CAMERA)),
      heading_deg: 270,
    });
  });

  it("queues a position when a drag is released inside the arming radius", () => {
    const onAdd = vi.fn();
    render(<Harness onAddWaypoint={onAdd} />);
    fireEvent.pointerDown(canvas(), { button: 0, clientX: 450, clientY: 300, ...alt });
    fireEvent.pointerMove(canvas(), { clientX: 456, clientY: 300 });
    expect(placing()).toHaveAttribute("data-phase", "silhouette");
    fireEvent.pointerUp(canvas(), { clientX: 470, clientY: 300 });
    expect(onAdd.mock.calls[0][0]).not.toHaveProperty("heading_deg");
  });

  it("snaps to 15 degrees with Shift", () => {
    const onAdd = vi.fn();
    render(<Harness onAddWaypoint={onAdd} />);
    fireEvent.pointerDown(canvas(), { button: 0, clientX: 450, clientY: 300, ...alt });
    fireEvent.pointerMove(canvas(), { ...out(450, 300, 52) });
    expect(Number(screen.getByTestId("placing-pose").dataset.heading)).toBe(52);
    fireEvent.keyDown(window, { key: "Shift", shiftKey: true });
    expect(screen.getByTestId("placing-pose")).toHaveAttribute("data-heading", "45");
    fireEvent.pointerUp(canvas(), { ...out(450, 300, 52), shiftKey: true });
    expect(onAdd.mock.calls[0][0].heading_deg).toBe(45);
  });

  it("queues nothing when Esc, the other button or the browser cancels it", () => {
    const onAdd = vi.fn();
    render(<Harness onAddWaypoint={onAdd} />);
    const begin = () => {
      fireEvent.pointerDown(canvas(), { button: 0, clientX: 450, clientY: 300, ...alt });
      fireEvent.pointerMove(canvas(), { clientX: 550, clientY: 300 });
    };
    begin();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(placing()).toBeNull();
    fireEvent.pointerUp(canvas(), { clientX: 550, clientY: 300 });
    begin();
    fireEvent.contextMenu(canvas());
    fireEvent.pointerUp(canvas(), { clientX: 550, clientY: 300 });
    begin();
    fireEvent.pointerMove(canvas(), { clientX: 560, clientY: 300, buttons: 3 });
    fireEvent.pointerUp(canvas(), { clientX: 560, clientY: 300 });
    begin();
    fireEvent.pointerCancel(canvas());
    fireEvent.pointerUp(canvas(), { clientX: 550, clientY: 300 });
    expect(onAdd).not.toHaveBeenCalled();
  });

  it("draws the selected robot's own body, axle on the point", () => {
    const b = bot("a", { x: 500, y: 553.5 }, { pose: POSE });
    render(<Harness bots={[b]} selection={new Set(["a"])} from={{ scale: 8, tx: 0, ty: 0 }} />);
    fireEvent.pointerDown(canvas(), { button: 0, clientX: 300, clientY: 200, ...alt });
    fireEvent.pointerMove(canvas(), { clientX: 300, clientY: 300 });
    const pose = screen.getByTestId("placing-pose");
    expect(pose).toHaveAttribute("data-pose-shape", "board");
    expect(pose.querySelector('[data-layer="board"]')).not.toBeNull();
    expect(pose.querySelector('[data-layer="axle"]')).not.toBeNull();
  });

  it("falls back to a diamond and a tick with no body to borrow", () => {
    render(<Harness />);
    fireEvent.pointerDown(canvas(), { button: 0, clientX: 450, clientY: 300, ...alt });
    fireEvent.pointerMove(canvas(), { clientX: 450, clientY: 400 });
    expect(screen.getByTestId("placing-pose")).toHaveAttribute("data-pose-shape", "arrow");
  });

  it("turns a robot in place when started on it: the pose is its own axle", () => {
    const onAdd = vi.fn();
    const b = bot("a", { x: 500, y: 553.5 }, { pose: POSE });
    render(<Harness bots={[b]} selection={new Set(["a"])} onAddWaypoint={onAdd} />);
    // jsdom puts every robot at the canvas origin; the press lands on it.
    fireEvent.pointerDown(document.getElementById("bot-a")!, { button: 0, clientX: 450, clientY: 300, ...alt });
    fireEvent.pointerMove(canvas(), { clientX: 900, clientY: 0 });
    fireEvent.pointerUp(canvas(), { clientX: 900, clientY: 0 });
    expect(onAdd).toHaveBeenCalledTimes(1);
    expect(onAdd.mock.calls[0][0]).toMatchObject({ x: 500, y: 500 });
    expect(typeof onAdd.mock.calls[0][0].heading_deg).toBe("number");
  });
});

describe("turning a robot in place", () => {
  it("pivots on the robot's own axle estimate when it reports one", () => {
    const onAdd = vi.fn();
    const b = bot("a", { x: 500, y: 553.5 }, { pose: POSE, axle: { x: 510, y: 505 } });
    render(<Harness bots={[b]} selection={new Set(["a"])} onAddWaypoint={onAdd} />);
    fireEvent.pointerDown(document.getElementById("bot-a")!, { button: 0, clientX: 450, clientY: 300, ...alt });
    fireEvent.pointerMove(canvas(), { clientX: 900, clientY: 0 });
    fireEvent.pointerUp(canvas(), { clientX: 900, clientY: 0 });
    expect(onAdd.mock.calls[0][0]).toMatchObject({ x: 510, y: 505 });
  });
});

describe("pose mode", () => {
  it("places with a plain press: a click is a position, a drag a pose", () => {
    const onAdd = vi.fn();
    render(<Harness onAddWaypoint={onAdd} poseMode />);
    expect(screen.getByTestId("pose-mode-chip")).toBeInTheDocument();
    fireEvent.pointerDown(canvas(), { button: 0, clientX: 450, clientY: 300 });
    fireEvent.pointerUp(canvas(), { clientX: 450, clientY: 300 });
    fireEvent.pointerDown(canvas(), { button: 0, clientX: 450, clientY: 300 });
    fireEvent.pointerMove(canvas(), { clientX: 450, clientY: 200 });
    fireEvent.pointerUp(canvas(), { clientX: 450, clientY: 200 });
    expect(onAdd.mock.calls[0][0]).not.toHaveProperty("heading_deg");
    expect(onAdd.mock.calls[1][0].heading_deg).toBeCloseTo(180);
  });

  it("pans with two fingers, dropping the pose the first one started", () => {
    const onAdd = vi.fn();
    render(<Harness onAddWaypoint={onAdd} poseMode from={{ scale: 2, tx: 0, ty: 0 }} />);
    const t = (id: number, x: number, y: number) => ({ pointerId: id, pointerType: "touch", button: 0, clientX: x, clientY: y });
    fireEvent.pointerDown(canvas(), t(1, 400, 300));
    fireEvent.pointerDown(canvas(), t(2, 500, 300));
    expect(placing()).toBeNull();
    fireEvent.pointerMove(canvas(), t(1, 440, 320));
    fireEvent.pointerMove(canvas(), t(2, 540, 320));
    expect(camera().tx).toBeCloseTo(40, 6);
    expect(camera().ty).toBeCloseTo(20, 6);
    fireEvent.pointerUp(canvas(), t(1, 440, 320));
    fireEvent.pointerUp(canvas(), t(2, 540, 320));
    expect(onAdd).not.toHaveBeenCalled();
  });

  it("pans with Space held, and places nothing", () => {
    const onAdd = vi.fn();
    render(<Harness onAddWaypoint={onAdd} poseMode from={{ scale: 2, tx: 0, ty: 0 }} />);
    fireEvent.keyDown(window, { key: " " });
    drag(null, [400, 300], [440, 320]);
    fireEvent.keyUp(window, { key: " " });
    expect(camera().tx).toBeCloseTo(40, 6);
    expect(onAdd).not.toHaveBeenCalled();
  });
});

describe("a queued pose", () => {
  const cam = FRAME_CAMERA;
  const pivot = under(450, 300, cam);
  const planned = [{ key: "a", ids: ["a"], waypoints: [{ ...pivot, heading_deg: 90 }], led: null }];

  it("turns with its knob, and snaps with Shift", () => {
    const onSet = vi.fn();
    render(<Harness planned={planned} selection={new Set(["a"])} onSetHeading={onSet} />);
    expect(screen.queryByTestId("planned-a-0-knob")).toBeNull();
    fireEvent.pointerEnter(screen.getByTestId("planned-hit-a-0"));
    fireEvent.pointerDown(screen.getByTestId("planned-a-0-knob"), { button: 0 });
    fireEvent.pointerMove(canvas(), { clientX: 550, clientY: 300 });
    expect(onSet).toHaveBeenLastCalledWith("a", 0, 270);
    fireEvent.pointerMove(canvas(), { ...out(450, 300, 52), shiftKey: true });
    expect(onSet).toHaveBeenLastCalledWith("a", 0, 45);
    fireEvent.pointerUp(canvas(), { clientX: 550, clientY: 300 });
  });

  it("turns 15 degrees a wheel notch while hovered, and leaves the wheel alone otherwise", () => {
    const onSet = vi.fn();
    render(<Harness planned={planned} selection={new Set(["a"])} onSetHeading={onSet} />);
    fireEvent.wheel(canvas(), { deltaY: 120, clientX: 450, clientY: 300 });
    expect(onSet).not.toHaveBeenCalled();
    fireEvent.pointerEnter(screen.getByTestId("planned-hit-a-0"));
    fireEvent.wheel(canvas(), { deltaY: 120, clientX: 450, clientY: 300 });
    expect(onSet).toHaveBeenLastCalledWith("a", 0, 105);
    fireEvent.wheel(canvas(), { deltaY: -120, clientX: 450, clientY: 300 });
    expect(onSet).toHaveBeenLastCalledWith("a", 0, 75);
  });

  it("shows how many robots share it", () => {
    const shared = [{ ...planned[0], key: "a-b", ids: ["a", "b"] }];
    render(<Harness planned={shared} selection={new Set(["a"])} />);
    expect(screen.getByTestId("planned-a-b-0").querySelector('[data-layer="pose-shared"]')).toHaveTextContent("×2");
  });
});

describe("a plain waypoint", () => {
  it("marks where the robot's centre stops, ringed by the robot's reach once it reads", () => {
    const planned = [{ key: "a", ids: ["a"], waypoints: [{ x: 800, y: 800 }], led: null }];
    const b = bot("a", { x: 500, y: 553.5 }, { pose: POSE });
    const { unmount } = render(<Harness bots={[b]} planned={planned} selection={new Set(["a"])} from={{ scale: 8, tx: 0, ty: 0 }} />);
    expect(document.querySelectorAll('[data-layer="waypoint-centre"]')).toHaveLength(1);
    expect(document.querySelector('[data-layer="waypoint-footprint"]')).not.toBeNull();
    // and the robot marks its own centre, so the two line up
    expect(screen.getByTestId("glyph-a").querySelector('[data-layer="axle"]')).not.toBeNull();
    unmount();
    render(<Harness bots={[b]} planned={planned} selection={new Set(["a"])} />);
    expect(document.querySelector('[data-layer="waypoint-centre"]')).not.toBeNull();
    expect(document.querySelector('[data-layer="waypoint-footprint"]')).toBeNull();
  });
});

describe("a robot reporting its own axle", () => {
  it("has its body drawn about that axle rather than the geometry record's", () => {
    const at = (axle?: LH2Position) => {
      const b = bot("a", { x: 500, y: 553.5 }, { pose: POSE, axle });
      const { unmount } = render(<Harness bots={[b]} from={{ scale: 8, tx: 0, ty: 0 }} />);
      const glyph = screen.getByTestId("glyph-a");
      const cy = Number(glyph.querySelector('[data-layer="axle"]')!.getAttribute("cy"));
      const board = glyph.querySelector('[data-layer="board"]')!.getAttribute("points");
      unmount();
      return { cy, board };
    };
    const record = at();
    const own = at({ x: 500, y: 502 });
    expect(own.cy).toBeGreaterThan(record.cy);
    expect(own.board).not.toBe(record.board);
  });
});

describe("a queued pose on a robot with no heading", () => {
  // What the controller sends for a robot whose direction reads -1000: the
  // body expanded on a placeholder heading, marked "none".
  const STILL: BotPose = { ...POSE, heading_source: "none", heading_deg: 0 };
  const planned = [{ key: "a", ids: ["a"], waypoints: [{ x: 800, y: 800, heading_deg: 120 }], led: null }];

  it("is still the robot's silhouette, at the pose's own heading", () => {
    const b = bot("a", { x: 500, y: 553.5 }, { pose: STILL, heading: null });
    render(<Harness bots={[b]} planned={planned} selection={new Set(["a"])} from={{ scale: 8, tx: 0, ty: 0 }} />);
    const pose = screen.getByTestId("planned-a-0");
    expect(pose).toHaveAttribute("data-pose-shape", "board");
    expect(pose).toHaveAttribute("data-heading", "120");
    expect(pose.querySelector('[data-layer="board"]')).not.toBeNull();
    expect(pose.querySelector('[data-layer="pose-arrow"] polygon')).not.toBeNull();
  });

  it("says what it asks of the robot on hover", () => {
    const b = bot("a", { x: 500, y: 553.5 }, { pose: STILL });
    render(<Harness bots={[b]} planned={planned} selection={new Set(["a"])} />);
    expect(screen.getByTestId("planned-hit-a-0")).toHaveAttribute("title", "Pose 1: face 120°, stop within 10 mm");
  });
});
