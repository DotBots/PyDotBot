import React from "react";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { barLabel, pxPerMm, scaleBar } from "./grid";
import type { Site } from "./types";
import {
  ZOOM_MAX_FLOOR,
  ZOOM_MIN,
  ZOOM_STEP,
  fitScale,
  padArea,
  scaleForFraction,
  viewGeom,
  zoomFraction,
  zoomMax,
} from "./zoom";

// A floor-sized site with a room-sized area in it: the case a ceiling fixed
// at a small multiple could not frame.
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
const VIEWPORT = { x: -2000, y: -2000, w: 7330, h: 8000 };
const CANVAS = { width: 900, height: 600 };

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
// nothing and every camera would collapse onto the same degenerate scale.
let rectSpy: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  rectSpy = vi
    .spyOn(HTMLElement.prototype, "getBoundingClientRect")
    .mockReturnValue({
      width: CANVAS.width,
      height: CANVAS.height,
      top: 0,
      left: 0,
      right: CANVAS.width,
      bottom: CANVAS.height,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    } as DOMRect);
  window.history.replaceState({}, "", "/");
});

afterEach(() => {
  rectSpy.mockRestore();
  window.history.replaceState({}, "", "/");
  window.localStorage.clear();
});

const camera = () => screen.getByTestId("camera-layer").style.transform;

const scaleOf = (transform: string) =>
  Number(/scale\(([-\d.]+)\)/.exec(transform)?.[1]);

describe("zooming to an area", () => {
  it("lands on the same camera from the menu, the label and ?zoom=", () => {
    // The menu.
    render(<App />);
    fireEvent.click(screen.getByTitle("Zoom to"));
    fireEvent.click(
      within(screen.getByRole("menu", { name: "Zoom to" })).getByRole(
        "menuitem",
        { name: "dock" },
      ),
    );
    const fromMenu = camera();
    cleanup();

    // The area's row under Layers > Areas, where its name lives.
    render(<App />);
    fireEvent.click(screen.getByTitle("Zoom to dock"));
    const fromRow = camera();
    cleanup();

    // The URL preset.
    window.history.replaceState({}, "", "/?zoom=dock");
    render(<App />);
    const fromSearch = camera();

    expect(fromRow).toBe(fromMenu);
    expect(fromSearch).toBe(fromMenu);
    expect(fromMenu).not.toBe("translate(0px, 0px) scale(1)");
  });

  it("fills the canvas with the area rather than stopping short of it", () => {
    render(<App />);
    fireEvent.click(screen.getByTitle("Zoom to dock"));

    const scale = scaleOf(camera());
    // The dock is about a tenth of the drawn viewport's short side, so it
    // takes far more than the fallback ceiling to fill the canvas.
    expect(scale).toBeGreaterThan(ZOOM_MAX_FLOOR);
    const geom = viewGeom(CANVAS.width, CANVAS.height, VIEWPORT);
    // Exactly the fit it asked for, not the nearest scale to it.
    expect(scale).toBeCloseTo(
      fitScale(padArea(site.areas[2]), VIEWPORT, geom),
      6,
    );
  });

  it("says what the zoom is worth on the floor", () => {
    render(<App />);
    const geom = viewGeom(CANVAS.width, CANVAS.height, VIEWPORT);
    const barAt = (scale: number) =>
      scaleBar(pxPerMm("x", VIEWPORT, geom, { scale, tx: 0, ty: 0 }));
    const scaleText = () => screen.getByLabelText("Map scale").textContent ?? "";

    expect(scaleText()).toBe(barLabel(barAt(1).mm));

    // Zoomed in, the same length of canvas stands for less floor.
    for (let i = 0; i < 3; i += 1) fireEvent.click(screen.getByTitle("Zoom in"));
    const closer = barAt(ZOOM_STEP ** 3);
    expect(scaleText()).toBe(barLabel(closer.mm));
    expect(closer.mm).toBeLessThan(barAt(1).mm);
  });

  it("shows where in the range the map is, however it got there", () => {
    render(<App />);
    const geom = viewGeom(CANVAS.width, CANVAS.height, VIEWPORT);
    const max = zoomMax(site, VIEWPORT, geom);
    const slider = () => screen.getByLabelText("Zoom") as HTMLInputElement;

    // The whole site is the far end of the range.
    expect(Number(slider().value)).toBeCloseTo(0, 9);

    // The buttons and the handle agree on where a press lands.
    fireEvent.click(screen.getByTitle("Zoom in"));
    expect(Number(slider().value)).toBeCloseTo(
      zoomFraction(ZOOM_STEP, max),
      6,
    );

    // And so does a named zoom, which does not go through either.
    fireEvent.click(screen.getByTitle("Zoom to dock"));
    expect(Number(slider().value)).toBeCloseTo(
      zoomFraction(scaleOf(camera()), max),
      6,
    );
  });

  it("moves the camera to the scale the handle is dragged to", () => {
    render(<App />);
    const geom = viewGeom(CANVAS.width, CANVAS.height, VIEWPORT);
    const max = zoomMax(site, VIEWPORT, geom);
    const slider = screen.getByLabelText("Zoom") as HTMLInputElement;

    fireEvent.change(slider, { target: { value: "0.5" } });
    expect(scaleOf(camera())).toBeCloseTo(scaleForFraction(0.5, max), 6);

    fireEvent.change(slider, { target: { value: "1" } });
    expect(scaleOf(camera())).toBeCloseTo(max, 6);

    fireEvent.change(slider, { target: { value: "0" } });
    expect(scaleOf(camera())).toBeCloseTo(ZOOM_MIN, 6);
  });

  it("takes the arrow and page keys, and the ends of the range", () => {
    render(<App />);
    const geom = viewGeom(CANVAS.width, CANVAS.height, VIEWPORT);
    const max = zoomMax(site, VIEWPORT, geom);
    const slider = screen.getByLabelText("Zoom") as HTMLInputElement;

    fireEvent.keyDown(slider, { key: "ArrowRight" });
    expect(scaleOf(camera())).toBeCloseTo(ZOOM_STEP, 6);
    fireEvent.keyDown(slider, { key: "ArrowLeft" });
    expect(scaleOf(camera())).toBeCloseTo(ZOOM_MIN, 6);

    fireEvent.keyDown(slider, { key: "PageUp" });
    expect(scaleOf(camera())).toBeCloseTo(ZOOM_STEP ** 3, 6);

    fireEvent.keyDown(slider, { key: "End" });
    expect(scaleOf(camera())).toBeCloseTo(max, 6);
    fireEvent.keyDown(slider, { key: "Home" });
    expect(scaleOf(camera())).toBeCloseTo(ZOOM_MIN, 6);
  });

  it("speaks its position as floor, not as a bare number", () => {
    render(<App />);
    const slider = screen.getByLabelText("Zoom") as HTMLInputElement;
    const spoken = () => slider.getAttribute("aria-valuetext") ?? "";

    expect(spoken()).toMatch(/^[\d.]+ m of floor across the map$/);
    const wide = parseFloat(spoken());
    fireEvent.click(screen.getByTitle("Zoom in"));
    expect(parseFloat(spoken())).toBeLessThan(wide);
  });
});
