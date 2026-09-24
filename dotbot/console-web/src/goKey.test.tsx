import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { putWaypoints } from "./api";
import { ACTION_KEY, MAP_MODIFIER, Modifier } from "./shortcuts";
import type { Site, UnifiedBot } from "./types";

const site: Site = {
  name: "c405-arena",
  anchor: "the arena's top-left corner",
  extent_mm: [2000, 4000],
  areas: [{ x: 0, y: 0, w: 2000, h: 2000, name: "arena" }],
};
const VIEWPORT = { x: -2000, y: -2000, w: 6000, h: 8000 };

const bot = (id: string, extra: Partial<UnifiedBot> = {}): UnifiedBot => ({
  id,
  state: "Running",
  link: "active",
  position: { x: 500, y: 500 },
  heading: 0,
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
const idle = bot("BADCAFE111111111");
const underWay = bot("DEADBEEF22222222", {
  nav: "auto",
  waypoints: [
    { x: 500, y: 500 },
    { x: 900, y: 900 },
  ],
});
const ghost = bot("B0B0F00D33333333", { drivable: false, link: "unknown" });

vi.mock("./useFleet", () => ({
  useFleet: () => ({
    bots: [idle, underWay, ghost],
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

let rectSpy: ReturnType<typeof vi.spyOn>;
beforeEach(() => {
  vi.clearAllMocks();
  rectSpy = vi
    .spyOn(HTMLElement.prototype, "getBoundingClientRect")
    .mockReturnValue({
      width: 900,
      height: 600,
      top: 0,
      left: 0,
      right: 900,
      bottom: 600,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    } as DOMRect);
  window.history.replaceState({}, "", "/");
});
afterEach(() => {
  rectSpy.mockRestore();
  cleanup();
  window.history.replaceState({}, "", "/");
  window.localStorage.clear();
});

const press = (key: string, target: Element = document.body, over = {}) =>
  fireEvent.keyDown(target, { key, ...over });
const select = (suffix: string) => window.history.replaceState({}, "", `/?sel=${suffix}`);
const canvas = () => screen.getByTestId("camera-layer").parentElement!;
// The keys an event holds for one of the table's modifiers.
const held = (modifier: Modifier) => ({
  shiftKey: modifier === "shift",
  ctrlKey: modifier === "ctrl",
  metaKey: false,
  altKey: modifier === "alt",
});
// Queue a waypoint the way the map does: the waypoint modifier and a click,
// which queues on release.
const queueWaypoint = () => {
  const at = { button: 0, clientX: 450, clientY: 300, ...held(MAP_MODIFIER.waypoint) };
  fireEvent.pointerDown(canvas(), at);
  fireEvent.pointerUp(canvas(), at);
};

describe("the go key", () => {
  it("sends the selection to its queued waypoints, as Go does", () => {
    select("1111");
    render(<App />);
    queueWaypoint();
    expect(screen.getByTestId(/^planned-/)).toBeInTheDocument();

    press(ACTION_KEY.go.toLowerCase());

    expect(putWaypoints).toHaveBeenCalledTimes(1);
    expect(putWaypoints).toHaveBeenCalledWith(idle.id, idle.application, expect.any(Number), [
      { x: expect.any(Number), y: expect.any(Number) },
    ], 20);
    expect(screen.getByText("1 waypoint sent to 1 bot")).toBeInTheDocument();
    expect(screen.queryByTestId(/^planned-/)).not.toBeInTheDocument();
  });

  it("stops a selection already under way, as Stop nav does", () => {
    select("2222");
    render(<App />);
    press(ACTION_KEY.go);
    expect(putWaypoints).toHaveBeenCalledWith(underWay.id, underWay.application, expect.any(Number), []);
    expect(screen.getByText("Navigation stopped")).toBeInTheDocument();
  });

  it("says so with nothing selected, and sends nothing", () => {
    render(<App />);
    press("g");
    expect(screen.getByText("Nothing selected")).toBeInTheDocument();
    expect(putWaypoints).not.toHaveBeenCalled();
  });

  it("says what to do with a selection that has nothing queued", () => {
    select("1111");
    render(<App />);
    press("g");
    expect(screen.getByText(/^No waypoints queued/)).toBeInTheDocument();
    expect(putWaypoints).not.toHaveBeenCalled();
  });

  it("says so for a selection that cannot be driven", () => {
    select("3333");
    render(<App />);
    press("g");
    expect(screen.getByText("Not drivable")).toBeInTheDocument();
    expect(putWaypoints).not.toHaveBeenCalled();
  });

  it("is left alone while typing, the zoom slider included, and under a modifier", () => {
    select("2222");
    render(<App />);
    const slider = screen.getByLabelText("Zoom");
    slider.focus();
    press("g", slider);
    press("g", document.body, { metaKey: true });
    press("g", document.body, { ctrlKey: true });
    expect(putWaypoints).not.toHaveBeenCalled();
    expect(screen.queryByText("Navigation stopped")).not.toBeInTheDocument();
  });
});
