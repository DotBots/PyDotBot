import React, { useState } from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { areaToFraction } from "./frame";
import { frameMm } from "./grid";
import { MapView } from "./MapView";
import { MAP_MODIFIER, Modifier } from "./shortcuts";
import type { Area, LH2Position, Site, UnifiedBot } from "./types";
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
}

const Harness: React.FC<HarnessProps> = ({
  bots = [],
  selection = new Set(),
  from = FRAME_CAMERA,
  onSelect = () => {},
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
      plannedMissions={[]}
      cam={cam}
      setCam={setCam}
      onGeom={() => {}}
      onSelect={onSelect}
      onAddWaypoint={() => {}}
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
