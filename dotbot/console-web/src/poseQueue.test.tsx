import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { putWaypoints } from "./api";
import { ACTION_KEY, MAP_MODIFIER, Modifier, UNDO_KEY } from "./shortcuts";
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
const failed = bot("FA11ED0044444444", {
  waypoints: [{ x: 500, y: 500 }, { x: 900, y: 900, heading_deg: 90 }],
  mission: { state: "failed", index: 1, reason: "blocked", code: "PROGRESS" },
});
const leading = bot("1EAD000055555555", {
  nav: "auto",
  waypoints: [{ x: 500, y: 500 }, { x: 900, y: 900 }, { x: 900, y: 500 }, { x: 500, y: 900 }],
  mission: { state: "in_progress", index: 1, reason: null, code: null },
});

vi.mock("./useFleet", () => ({
  useFleet: () => ({
    bots: [idle, underWay, ghost, failed, leading],
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


// A pose the way the map makes one: the waypoint modifier, a drag out to the
// right, and a release, which faces the robot right (270).
const queuePose = () => {
  const mod = held(MAP_MODIFIER.waypoint);
  fireEvent.pointerDown(canvas(), { button: 0, clientX: 450, clientY: 300, ...mod });
  fireEvent.pointerMove(canvas(), { buttons: 1, clientX: 550, clientY: 300 });
  fireEvent.pointerUp(canvas(), { clientX: 550, clientY: 300 });
};
const openQueue = () => fireEvent.click(screen.getByText(/^◎ Waypoints/));
const field = (i: number) => screen.getByTestId(`heading-${i}`) as HTMLInputElement;

describe("a queued pose in the waypoint queue", () => {
  it("holds at most the firmware's 16 points", () => {
    select("1111");
    render(<App />);
    for (let i = 0; i < 17; i++) queueWaypoint();
    expect(screen.getByText(/at most 16 waypoints/)).toBeInTheDocument();
    press(ACTION_KEY.go);
    expect((putWaypoints as ReturnType<typeof vi.fn>).mock.calls[0][3]).toHaveLength(16);
  });

  it("is sent with its heading", () => {
    select("1111");
    render(<App />);
    queuePose();
    press(ACTION_KEY.go);
    expect(putWaypoints).toHaveBeenCalledWith(idle.id, idle.application, expect.any(Number), [
      { x: expect.any(Number), y: expect.any(Number), heading_deg: 270 },
    ], { intermediate_threshold: 20 });
  });

  it("shows its heading as a number the keys step and clear", () => {
    select("1111");
    render(<App />);
    queuePose();
    queueWaypoint();
    openQueue();
    expect(field(0).value).toBe("270");
    expect(field(1).value).toBe("");
    fireEvent.keyDown(field(0), { key: "ArrowUp" });
    expect(field(0).value).toBe("271");
    fireEvent.keyDown(field(0), { key: "ArrowDown", shiftKey: true });
    expect(field(0).value).toBe("256");
    fireEvent.change(field(1), { target: { value: "90" } });
    fireEvent.keyDown(field(1), { key: "Enter" });
    expect(field(1).value).toBe("90");
    fireEvent.change(field(0), { target: { value: "100" } });
    fireEvent.keyDown(field(0), { key: "ArrowUp" });
    expect(field(0).value).toBe("101");
    fireEvent.keyDown(field(0), { key: "Delete" });
    expect(field(0).value).toBe("");
    press(ACTION_KEY.go);
    expect(putWaypoints).toHaveBeenCalledWith(idle.id, idle.application, expect.any(Number), [
      { x: expect.any(Number), y: expect.any(Number) },
      { x: expect.any(Number), y: expect.any(Number), heading_deg: 90 },
    ], { intermediate_threshold: 20 });
  });
});

describe("the undo key", () => {
  it("takes back the last queued waypoint, one per press", () => {
    select("1111");
    render(<App />);
    queueWaypoint();
    queuePose();
    expect(screen.getAllByTestId(/^planned-[^h]/)).toHaveLength(2);
    press(UNDO_KEY.toLowerCase(), document.body, { ctrlKey: true });
    expect(screen.getAllByTestId(/^planned-[^h]/)).toHaveLength(1);
    press(UNDO_KEY.toLowerCase(), document.body, { metaKey: true });
    expect(screen.queryByTestId(/^planned-/)).not.toBeInTheDocument();
    press(UNDO_KEY.toLowerCase(), document.body, { ctrlKey: true });
    expect(screen.getByText("Nothing queued to take back")).toBeInTheDocument();
  });
});

describe("the pose mode key", () => {
  it("toggles pose mode, which the Footer shows and Esc turns off", () => {
    select("1111");
    render(<App />);
    expect(screen.queryByTestId("pose-mode-chip")).toBeNull();
    press(ACTION_KEY.poseMode.toLowerCase());
    expect(screen.getByTestId("pose-mode-chip")).toBeInTheDocument();
    expect(screen.getByTestId("pose-mode-toggle")).toHaveAttribute("aria-checked", "true");
    press("Escape");
    expect(screen.queryByTestId("pose-mode-chip")).toBeNull();
    fireEvent.click(screen.getByTestId("pose-mode-toggle"));
    expect(screen.getByTestId("pose-mode-chip")).toBeInTheDocument();
  });
});

describe("the robot's own report on its batch", () => {
  it("shows how the last batch ended", () => {
    select("4444");
    render(<App />);
    const badge = screen.getByTestId("mission-report");
    expect(badge).toHaveAttribute("data-state", "failed");
    expect(badge).toHaveTextContent("Failed: blocked");
  });

  it("names the waypoint being driven to", () => {
    select("5555");
    render(<App />);
    expect(screen.getByText(/waypoint 2 of 3/)).toBeInTheDocument();
    expect(screen.queryByTestId("mission-report")).toBeNull();
  });
});

describe("the waypoint settings", () => {
  const KEY = "dotbot.console.waypointSettings";
  const typeInto = (id: string, text: string) => {
    fireEvent.change(screen.getByTestId(id), { target: { value: text } });
    fireEvent.keyDown(screen.getByTestId(id), { key: "Enter" });
  };

  it("sends 10 mm, a 20 mm pass radius and the firmware's tolerance by default", () => {
    select("1111");
    render(<App />);
    queuePose();
    openQueue();
    expect(screen.getByTestId("arrival-10")).toHaveAttribute("aria-checked", "true");
    expect((screen.getByTestId("heading-tol") as HTMLInputElement).placeholder).toBe("3");
    press(ACTION_KEY.go);
    expect(putWaypoints).toHaveBeenCalledWith(idle.id, idle.application, 10, expect.any(Array), {
      intermediate_threshold: 20,
    });
  });

  it("sends a preset, then exact numbers held to their range, and remembers them", () => {
    select("1111");
    render(<App />);
    queuePose();
    openQueue();
    fireEvent.click(screen.getByTestId("arrival-2"));
    expect((screen.getByTestId("arrival-mm") as HTMLInputElement).value).toBe("2");
    typeInto("arrival-mm", "7");
    expect(screen.getByTestId("arrival-2")).toHaveAttribute("aria-checked", "false");
    typeInto("pass-mm", "9000");
    typeInto("heading-tol", "0");
    expect(JSON.parse(window.localStorage.getItem(KEY)!)).toEqual({ arrivalMm: 7, passMm: 500, headingTolDeg: 1 });
    press(ACTION_KEY.go);
    expect(putWaypoints).toHaveBeenCalledWith(idle.id, idle.application, 7, expect.any(Array), {
      intermediate_threshold: 500,
      heading_tolerance: 1,
    });
  });

  it("drops the tolerance back to the firmware's when cleared", () => {
    window.localStorage.setItem(KEY, JSON.stringify({ arrivalMm: 5, passMm: 30, headingTolDeg: 4 }));
    select("1111");
    render(<App />);
    queueWaypoint();
    openQueue();
    typeInto("heading-tol", "");
    press(ACTION_KEY.go);
    expect(putWaypoints).toHaveBeenLastCalledWith(idle.id, idle.application, 5, expect.any(Array), {
      intermediate_threshold: 30,
    });
  });
});
