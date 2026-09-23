import React from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  SavedViews,
  VIEW_SETTLE_MS,
  loadSavedViews,
  saveSavedViews,
  viewFor,
  withView,
} from "./savedView";
import type { Area, Site } from "./types";
import {
  Camera,
  FRAME_CAMERA,
  cameraForArea,
  SITE_ZOOM,
  cameraForZoom,
  padArea,
  viewGeom,
  visibleArea,
  zoomMax,
} from "./zoom";

// The same floor the zoom tests use: a room-sized site with a small dock in
// one corner, which is the view worth coming back to.
const site: Site = {
  name: "c405-arena",
  anchor: "the arena's top-left corner",
  extent_mm: [3330, 4000],
  areas: [
    { x: 0, y: 0, w: 3330, h: 2000, name: "arena" },
    { x: 0, y: 2000, w: 3330, h: 2000, name: "annex" },
    { x: 2400, y: 3200, w: 900, h: 700, name: "dock" },
  ],
};
const VIEWPORT: Area = { x: -2000, y: -2000, w: 7330, h: 8000 };
const KEY = "dotbot.console.mapView";

vi.mock("./useFleet", () => ({
  useFleet: () => ({
    bots: [],
    site,
    session: null,
    setSession: () => {},
    viewport: VIEWPORT,
    wsUp: true,
  }),
}));

vi.mock("./useOrchestration", () => ({
  useOrchestration: () => ({
    logs: [],
    jobs: [],
    queue: {},
    fleetPct: 0,
    flashing: false,
    clearLogs: vi.fn(),
    flash: vi.fn(),
    act: vi.fn(),
  }),
}));

vi.mock("./useMrta", () => ({
  useMrta: () => ({ status: { available: false, on: false }, toggle: vi.fn() }),
}));

vi.mock("./api", () => ({
  fetchConnection: vi.fn(async () => null),
  fetchBuild: vi.fn(async () => null),
  putWaypoints: vi.fn(async () => {}),
  abandonCalibration: vi.fn(async () => {}),
  captureCalibrationPoint: vi.fn(),
  previewCalibrationPoints: vi.fn(async () => ({ points: [], reads: 25 })),
  pushCalibration: vi.fn(),
  redoCalibrationPoint: vi.fn(),
  saveCalibration: vi.fn(),
  startCalibration: vi.fn(),
}));

import { App } from "./App";

// jsdom measures every element as zero, so the map would size its canvas from
// nothing; a canvas is what this whole feature is about surviving a change of.
const asRect = (width: number, height: number) =>
  ({
    width,
    height,
    top: 0,
    left: 0,
    right: width,
    bottom: height,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  }) as DOMRect;

let rectSpy: ReturnType<typeof vi.spyOn>;
const sizeCanvas = (width: number, height: number) =>
  rectSpy.mockReturnValue(asRect(width, height));

beforeEach(() => {
  rectSpy = vi
    .spyOn(HTMLElement.prototype, "getBoundingClientRect")
    .mockReturnValue(asRect(900, 600));
  window.history.replaceState({}, "", "/");
});

afterEach(() => {
  rectSpy.mockRestore();
  window.history.replaceState({}, "", "/");
  window.localStorage.clear();
});

const transform = () => screen.getByTestId("camera-layer").style.transform;

// The camera the site view lands on in a 900 x 600 canvas.
const siteTransform = () => {
  const c = cameraForZoom(SITE_ZOOM, site, VIEWPORT, viewGeom(900, 600, VIEWPORT))!;
  return `translate(${c.tx}px, ${c.ty}px) scale(${c.scale})`;
};

const camOf = (): Camera => {
  const moved = /translate\(([-\d.e+]+)px, ([-\d.e+]+)px\)/.exec(transform())!;
  const scaled = /scale\(([-\d.e+]+)\)/.exec(transform())!;
  return {
    tx: Number(moved[1]),
    ty: Number(moved[2]),
    scale: Number(scaled[1]),
  };
};

/** The floor the rendered map is showing, in a canvas of this size. */
const shown = (width: number, height: number) =>
  visibleArea(camOf(), VIEWPORT, viewGeom(width, height, VIEWPORT));

const centre = (a: Area) => ({ x: a.x + a.w / 2, y: a.y + a.h / 2 });

describe("a view stated as floor rather than as a camera", () => {
  const geom = viewGeom(900, 600, VIEWPORT);
  const max = zoomMax(site, VIEWPORT, geom);

  it("takes a camera to the floor it frames and back again", () => {
    const cam = cameraForArea(padArea(site.areas[2]), VIEWPORT, geom, max);
    const back = cameraForArea(visibleArea(cam, VIEWPORT, geom), VIEWPORT, geom, max);

    expect(back.scale).toBeCloseTo(cam.scale, 9);
    expect(back.tx).toBeCloseTo(cam.tx, 6);
    expect(back.ty).toBeCloseTo(cam.ty, 6);
  });

  it("reaches past the drawn frame at the site camera, as the canvas does", () => {
    const rect = visibleArea(FRAME_CAMERA, VIEWPORT, geom);

    // The box carries the viewport's aspect and the canvas has slack on one
    // axis, so the view is the whole frame and then some on both.
    expect(rect.w).toBeGreaterThan(VIEWPORT.w);
    expect(rect.h).toBeGreaterThan(VIEWPORT.h);
    expect(centre(rect).x).toBeCloseTo(centre(VIEWPORT).x, 6);
    expect(centre(rect).y).toBeCloseTo(centre(VIEWPORT).y, 6);
  });
});

describe("the view this browser remembers", () => {
  const dock: Area = { x: 2400, y: 3200, w: 900, h: 700 };

  it("round-trips one view per site through storage", () => {
    let views: SavedViews = withView({}, "c405-arena", dock);
    views = withView(views, "limerick", { x: 0, y: 0, w: 100, h: 100 });
    saveSavedViews(views);

    const back = loadSavedViews();
    expect(back["c405-arena"]).toEqual({ x: 2400, y: 3200, w: 900, h: 700 });
    expect(back.limerick).toEqual({ x: 0, y: 0, w: 100, h: 100 });
    expect(viewFor(back, "c405-arena", VIEWPORT)).toEqual(dock);
  });

  it("offers nothing for a site it has never seen", () => {
    expect(viewFor(loadSavedViews(), "somewhere-else", VIEWPORT)).toBeNull();
    expect(viewFor(withView({}, "c405-arena", dock), null, VIEWPORT)).toBeNull();
  });

  it("reads nothing out of storage that holds nonsense", () => {
    window.localStorage.setItem(KEY, "{ not json");
    expect(loadSavedViews()).toEqual({});

    window.localStorage.setItem(KEY, '["a list"]');
    expect(loadSavedViews()).toEqual({});

    // A rectangle with no area, or one carrying nothing measurable, is not a
    // view: it would fit to a scale of nothing.
    window.localStorage.setItem(
      KEY,
      '{"c405-arena":{"x":0,"y":0,"w":0,"h":10},"other":{"x":null,"y":1,"w":1,"h":1}}',
    );
    expect(loadSavedViews()).toEqual({});
  });

  it("drops a view the floor no longer meets", () => {
    const away = withView({}, "c405-arena", { x: 90000, y: 90000, w: 900, h: 700 });
    expect(viewFor(away, "c405-arena", VIEWPORT)).toBeNull();

    // Touching the frame is meeting it: the clamps take it from there.
    const edge = withView({}, "c405-arena", { x: -2500, y: 0, w: 900, h: 700 });
    expect(viewFor(edge, "c405-arena", VIEWPORT)).not.toBeNull();
  });
});

describe("the view the map opens on", () => {
  it("writes the floor it is looking at once the camera settles", async () => {
    render(<App />);
    fireEvent.click(screen.getByTitle("Zoom to dock"));
    const floor = shown(900, 600);

    await waitFor(
      () => expect(loadSavedViews()[site.name]).toBeDefined(),
      { timeout: VIEW_SETTLE_MS * 8 },
    );

    const stored = loadSavedViews()[site.name];
    expect(stored.x).toBeCloseTo(floor.x, 6);
    expect(stored.y).toBeCloseTo(floor.y, 6);
    expect(stored.w).toBeCloseTo(floor.w, 6);
    expect(stored.h).toBeCloseTo(floor.h, 6);
  });

  it("comes back to the same floor in a canvas of another shape", async () => {
    render(<App />);
    fireEvent.click(screen.getByTitle("Zoom to dock"));
    const left = camOf();
    const floor = shown(900, 600);
    await waitFor(
      () => expect(loadSavedViews()[site.name]).toBeDefined(),
      { timeout: VIEW_SETTLE_MS * 8 },
    );
    cleanup();

    // The same console opened on a portrait window.
    sizeCanvas(600, 900);
    render(<App />);
    const back = shown(600, 900);

    // The floor that was in the middle is in the middle again ...
    expect(centre(back).x).toBeCloseTo(centre(floor).x, 6);
    expect(centre(back).y).toBeCloseTo(centre(floor).y, 6);
    // ... all of it is on screen, the new canvas letterboxing whichever axis
    // it has to spare ...
    expect(back.x).toBeLessThanOrEqual(floor.x + 1e-6);
    expect(back.y).toBeLessThanOrEqual(floor.y + 1e-6);
    expect(back.x + back.w).toBeGreaterThanOrEqual(floor.x + floor.w - 1e-6);
    expect(back.y + back.h).toBeGreaterThanOrEqual(floor.y + floor.h - 1e-6);
    // ... and one axis fits it exactly, so the view is the rectangle fitted
    // rather than the rectangle plus a margin.
    expect(
      Math.abs(back.w - floor.w) < 1e-6 || Math.abs(back.h - floor.h) < 1e-6,
    ).toBe(true);

    // Which is the whole reason the rectangle travels rather than the camera:
    // the camera that framed this floor frames somewhere else here.
    const raw = visibleArea(left, VIEWPORT, viewGeom(600, 900, VIEWPORT));
    expect(Math.hypot(
      centre(raw).x - centre(floor).x,
      centre(raw).y - centre(floor).y,
    )).toBeGreaterThan(100);
  });

  it("lets ?zoom= outrank what was stored", () => {
    saveSavedViews(withView({}, site.name, { x: 0, y: 2000, w: 3330, h: 2000 }));
    window.history.replaceState({}, "", "/?zoom=dock");

    render(<App />);

    const asked = cameraForZoom("dock", site, VIEWPORT, viewGeom(900, 600, VIEWPORT))!;
    expect(camOf().scale).toBeCloseTo(asked.scale, 6);
    expect(camOf().tx).toBeCloseTo(asked.tx, 6);
    expect(camOf().ty).toBeCloseTo(asked.ty, 6);
  });

  it("opens on the whole site when what was stored is unusable", () => {
    window.localStorage.setItem(KEY, "{ not json");
    render(<App />);
    expect(transform()).toBe(siteTransform());
    cleanup();

    // A view of floor this site no longer has: off the map altogether.
    saveSavedViews({ [site.name]: { x: 90000, y: 90000, w: 900, h: 700 } });
    render(<App />);
    expect(transform()).toBe(siteTransform());
  });

  it("opens on the whole site when the view belongs to another one", () => {
    saveSavedViews(withView({}, "limerick", { x: 2400, y: 3200, w: 900, h: 700 }));

    render(<App />);

    expect(transform()).toBe(siteTransform());
  });
});
