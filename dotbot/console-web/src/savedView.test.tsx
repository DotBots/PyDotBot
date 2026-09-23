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
  centreOfView,
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
  const dock = { x: 2850, y: 3550, pxPerMm: 0.4 };

  it("round-trips one view per site through storage", () => {
    let views: SavedViews = withView({}, "c405-arena", dock);
    views = withView(views, "limerick", { x: 50, y: 50, pxPerMm: 2 });
    saveSavedViews(views);

    const back = loadSavedViews();
    expect(back["c405-arena"]).toEqual(dock);
    expect(back.limerick).toEqual({ x: 50, y: 50, pxPerMm: 2 });
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

    // No scale, a scale of nothing, or a rectangle stored by an older console.
    window.localStorage.setItem(
      KEY,
      '{"a":{"x":0,"y":0,"pxPerMm":0},"b":{"x":null,"y":1,"pxPerMm":1},"c":{"x":0,"y":0,"w":10,"h":10}}',
    );
    expect(loadSavedViews()).toEqual({});
  });

  it("drops a view whose centre is off the floor", () => {
    const away = withView({}, "c405-arena", { x: 90000, y: 90000, pxPerMm: 0.4 });
    expect(viewFor(away, "c405-arena", VIEWPORT)).toBeNull();
    const edge = withView({}, "c405-arena", { x: VIEWPORT.x, y: 0, pxPerMm: 0.4 });
    expect(viewFor(edge, "c405-arena", VIEWPORT)).not.toBeNull();
  });
});

describe("the view the map opens on", () => {
  // The floor point at the canvas centre and the floor's px per mm, as drawn.
  const viewShown = (width: number, height: number) =>
    centreOfView(camOf(), VIEWPORT, viewGeom(width, height, VIEWPORT));
  const expectSameView = (got: { x: number; y: number; pxPerMm: number }, want: typeof got) => {
    expect(got.pxPerMm).toBeCloseTo(want.pxPerMm, 9);
    expect(got.x).toBeCloseTo(want.x, 4);
    expect(got.y).toBeCloseTo(want.y, 4);
  };
  const leaveOnDock = async (width: number, height: number) => {
    sizeCanvas(width, height);
    render(<App />);
    fireEvent.click(screen.getByTitle("Zoom to dock"));
    const view = viewShown(width, height);
    await waitFor(
      () => expect(loadSavedViews()[site.name]).toBeDefined(),
      { timeout: VIEW_SETTLE_MS * 8 },
    );
    return view;
  };

  it("writes the centre and the scale it is looking at once the camera settles", async () => {
    const view = await leaveOnDock(900, 600);
    expectSameView(loadSavedViews()[site.name], view);
  });

  // Landscape, portrait, and a map squeezed between both panes that is
  // narrower than it is tall: every pair crosses the frame's aspect ratio
  // one way or the other.
  for (const [from, to] of [
    [[900, 600], [600, 900]],
    [[900, 600], [420, 860]],
    [[420, 860], [900, 600]],
  ] as const) {
    it(`comes back to the same centre and scale from ${from.join("x")} to ${to.join("x")}`, async () => {
      const left = await leaveOnDock(from[0], from[1]);
      cleanup();
      sizeCanvas(to[0], to[1]);
      render(<App />);
      expectSameView(viewShown(to[0], to[1]), left);
    });
  }

  it("comes back to the same centre and scale with a panel collapsed", async () => {
    const left = await leaveOnDock(420, 860);
    cleanup();
    // Reloaded with the right pane remembered collapsed: a wider canvas.
    window.localStorage.setItem("dotbot.console.panels", JSON.stringify({ left: false, right: true }));
    sizeCanvas(760, 860);
    render(<App />);
    expectSameView(viewShown(760, 860), left);
  });

  it("lets ?zoom= outrank what was stored", () => {
    saveSavedViews(withView({}, site.name, { x: 1665, y: 3000, pxPerMm: 0.1 }));
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
    saveSavedViews({ [site.name]: { x: 90000, y: 90000, pxPerMm: 0.4 } });
    render(<App />);
    expect(transform()).toBe(siteTransform());
  });

  it("opens on the whole site when the view belongs to another one", () => {
    saveSavedViews(withView({}, "limerick", { x: 2850, y: 3550, pxPerMm: 0.4 }));

    render(<App />);

    expect(transform()).toBe(siteTransform());
  });
});
