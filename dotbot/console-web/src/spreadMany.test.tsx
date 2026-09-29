import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { putWaypointBatches } from "./api";
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
// More robots than one batch holds points, in a row across the arena.
const FLEET = Array.from({ length: 20 }, (_, i) =>
  bot(`BE0000000000${(0x1000 + i).toString(16).toUpperCase()}`, {
    position: { x: 100 + i * 90, y: 1000 },
  }),
);

vi.mock("./useFleet", () => ({
  useFleet: () => ({
    bots: FLEET,
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
  putWaypointBatches: vi.fn(async () => {}),
  clearWaypoints: vi.fn(async () => {}),
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
const queueWaypoint = (clientX = 450, clientY = 300) => {
  const at = { button: 0, clientX, clientY, ...held(MAP_MODIFIER.waypoint) };
  fireEvent.pointerDown(canvas(), at);
  fireEvent.pointerUp(canvas(), at);
};

describe("one target per robot, for more robots than a batch holds points", () => {
  it("places and sends one target to each of 20 robots", () => {
    select(FLEET.map((b) => b.id.slice(-4)).join(","));
    render(<App />);
    fireEvent.click(screen.getByRole("switch", { name: "One target per robot" }));
    FLEET.forEach((_, i) => queueWaypoint(300 + i * 15, 250 + (i % 4) * 30));
    expect(screen.queryByText(/at most 16 waypoints/)).not.toBeInTheDocument();
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    press(ACTION_KEY.go);
    confirm.mockRestore();
    expect(putWaypointBatches).toHaveBeenCalledTimes(1);
    const dotbots = vi.mocked(putWaypointBatches).mock.calls[0][1];
    expect(Object.keys(dotbots).sort()).toEqual(FLEET.map((b) => b.id).sort());
    expect(Object.values(dotbots).every((points) => points.length === 1)).toBe(true);
    expect(screen.getByText("20 robots sent to their own targets")).toBeInTheDocument();
  });

  it("keeps a robot's most when it turns the targets back into one route", () => {
    select(FLEET.map((b) => b.id.slice(-4)).join(","));
    render(<App />);
    const spread = () => screen.getByRole("switch", { name: "One target per robot" });
    fireEvent.click(spread());
    FLEET.forEach((_, i) => queueWaypoint(300 + i * 15, 300));
    fireEvent.click(spread());
    expect(screen.getByText("Kept the first 16 points, a robot's most")).toBeInTheDocument();
    press(ACTION_KEY.go);
    const dotbots = vi.mocked(putWaypointBatches).mock.calls[0][1];
    expect(Object.values(dotbots).every((points) => points.length === 16)).toBe(true);
  });
});
