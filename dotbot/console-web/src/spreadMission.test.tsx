import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { putWaypointBatches } from "./api";
import { ACTION_KEY, MAP_MODIFIER, Modifier } from "./shortcuts";
import { spreadColor } from "./spread";
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
const west = bot("BADCAFE111111111", { position: { x: 200, y: 2000 } });
const east = bot("FEEDFACE44444444", { position: { x: 1800, y: 2000 } });

vi.mock("./useFleet", () => ({
  useFleet: () => ({
    bots: [west, east],
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

// Every robot's batch, across however many requests carried them.
const sent = () =>
  vi
    .mocked(putWaypointBatches)
    .mock.calls.flatMap(([, dotbots]) =>
      Object.entries(dotbots).map(([id, points]) => ({ id, points })),
    );

describe("one target per robot", () => {
  it("is not offered for a single robot", () => {
    select("1111");
    render(<App />);
    expect(screen.queryByTestId("spread-panel")).not.toBeInTheDocument();
  });

  it("leaves a shared route alone while it is off", () => {
    select("1111,4444");
    render(<App />);
    queueWaypoint(300, 300);
    queueWaypoint(600, 300);
    press(ACTION_KEY.go);
    const calls = sent();
    expect(calls).toHaveLength(2);
    expect(calls[0].points).toHaveLength(2);
    expect(calls[1].points).toEqual(calls[0].points);
  });

  it("sends each robot its own nearest target, in one request", () => {
    select("1111,4444");
    render(<App />);
    fireEvent.click(screen.getByRole("switch", { name: "One target per robot" }));
    queueWaypoint(525, 300); // x 1600 mm, the east side first
    queueWaypoint(375, 300); // x 400 mm
    expect(screen.getByTestId("spread-preview")).toBeInTheDocument();
    expect(screen.getByTestId(`spread-leg-${west.id}`)).toBeInTheDocument();
    expect(screen.queryByTestId("spread-warnings")).not.toBeInTheDocument();
    press(ACTION_KEY.go);
    expect(putWaypointBatches).toHaveBeenCalledTimes(1);
    const calls = sent();
    expect(calls.map((c) => c.id).sort()).toEqual([west.id, east.id].sort());
    const to = Object.fromEntries(calls.map((c) => [c.id, c.points]));
    expect(to[west.id]).toHaveLength(1);
    expect(to[east.id]).toHaveLength(1);
    expect(to[west.id][0].x).toBeLessThan(to[east.id][0].x);
    expect(vi.mocked(putWaypointBatches).mock.calls[0][2]).toEqual({ intermediate_threshold: 20 });
    expect(screen.getByText("2 robots sent to their own targets")).toBeInTheDocument();
    expect(screen.getByTestId("spread-run")).toBeInTheDocument();
  });

  it("follows a swap the operator makes", () => {
    select("1111,4444");
    render(<App />);
    fireEvent.click(screen.getByRole("switch", { name: "One target per robot" }));
    queueWaypoint(375, 300);
    queueWaypoint(525, 300);
    fireEvent.change(screen.getByLabelText("Robot for target 1"), { target: { value: east.id } });
    expect(screen.getByText("Back to the shortest assignment")).toBeInTheDocument();
    expect(screen.getByTestId(`spread-leg-${west.id}`)).toHaveAttribute("data-crossing", "true");
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    press(ACTION_KEY.go);
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining("paths cross"));
    const to = Object.fromEntries(sent().map((c) => [c.id, c.points]));
    expect(to[east.id][0].x).toBeLessThan(to[west.id][0].x);
    confirm.mockRestore();
  });

  it("waits for every target before it sends", () => {
    select("1111,4444");
    render(<App />);
    fireEvent.click(screen.getByRole("switch", { name: "One target per robot" }));
    queueWaypoint(375, 300);
    press(ACTION_KEY.go);
    expect(putWaypointBatches).not.toHaveBeenCalled();
    expect(screen.getByText("Place one target per robot: 1 of 2")).toBeInTheDocument();
    queueWaypoint(525, 300);
    queueWaypoint(450, 300);
    expect(screen.getByText("One target per robot: all 2 placed")).toBeInTheDocument();
  });

  it("warns before sending targets that crowd each other, and sends nothing if declined", () => {
    select("1111,4444");
    render(<App />);
    fireEvent.click(screen.getByRole("switch", { name: "One target per robot" }));
    queueWaypoint(450, 300);
    queueWaypoint(451, 300);
    expect(screen.getByTestId("spread-warnings")).toHaveTextContent("closer than");
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    press(ACTION_KEY.go);
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining("closer than"));
    expect(putWaypointBatches).not.toHaveBeenCalled();
    confirm.mockReturnValue(true);
    press(ACTION_KEY.go);
    expect(sent()).toHaveLength(2);
    confirm.mockRestore();
  });

  it("colours each queued target as its own", () => {
    select("1111,4444");
    render(<App />);
    fireEvent.click(screen.getByRole("switch", { name: "One target per robot" }));
    queueWaypoint(375, 300);
    const marker = screen.getAllByTestId(/^planned-/)[0];
    expect(marker.getAttribute("style")).toContain(spreadColor(0).slice(1, 3));
  });
});
