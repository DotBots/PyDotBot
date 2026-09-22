import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { putWaypoints } from "./api";
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
  isDotBot: true,
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

const TARGETS = [
  { x: 900, y: 900 },
  { x: 1200, y: 300 },
];
// Arrived: MANUAL again, with the list the controller kept - own start first.
const arrived = bot("BADCAFE111111111", {
  waypoints: [{ x: 500, y: 500 }, ...TARGETS],
});
const never = bot("DEADBEEF22222222");
const underWay = bot("B0B0F00D33333333", {
  nav: "auto",
  waypoints: [{ x: 500, y: 500 }, ...TARGETS],
});
// What stopping leaves behind: the bot's own position and nothing else.
const stopped = bot("C0FFEE4444444444", { waypoints: [{ x: 700, y: 700 }] });
const OTHER_TARGETS = [{ x: 150, y: 250 }];
const arrivedElsewhere = bot("F00DFACE55555555", {
  waypoints: [{ x: 100, y: 100 }, ...OTHER_TARGETS],
});

vi.mock("./useFleet", () => ({
  useFleet: () => ({
    bots: [arrived, never, underWay, stopped, arrivedElsewhere],
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

const select = (suffix: string) => window.history.replaceState({}, "", `/?sel=${suffix}`);
const redo = () => screen.getByTestId("redo-mission");

describe("redo mission", () => {
  it("sends the bot the targets of the mission it just ran", () => {
    select("1111");
    render(<App />);

    fireEvent.click(redo());

    expect(putWaypoints).toHaveBeenCalledTimes(1);
    expect(putWaypoints).toHaveBeenCalledWith(
      arrived.id,
      arrived.application,
      expect.any(Number),
      TARGETS,
    );
    expect(screen.getByText("Mission re-sent to 1 bot")).toBeInTheDocument();
  });

  it("is unavailable, and silent, for a bot that has run none", () => {
    select("2222");
    render(<App />);

    expect(redo()).toHaveAttribute("title", "No previous mission to repeat");
    fireEvent.click(redo());

    expect(putWaypoints).not.toHaveBeenCalled();
  });

  it("is not offered while the bot is still under way", () => {
    select("3333");
    render(<App />);

    expect(screen.queryByTestId("redo-mission")).not.toBeInTheDocument();
    expect(screen.getByText("■ Stop nav")).toBeInTheDocument();
  });

  it("gives each bot of a selection its own last mission", () => {
    select("1111,5555");
    render(<App />);

    fireEvent.click(redo());

    expect(putWaypoints).toHaveBeenCalledTimes(2);
    expect(putWaypoints).toHaveBeenCalledWith(
      arrived.id,
      arrived.application,
      expect.any(Number),
      TARGETS,
    );
    expect(putWaypoints).toHaveBeenCalledWith(
      arrivedElsewhere.id,
      arrivedElsewhere.application,
      expect.any(Number),
      OTHER_TARGETS,
    );
    expect(screen.getByText("Mission re-sent to 2 bots")).toBeInTheDocument();
  });

  it("does not repeat the position a stop left behind", () => {
    select("4444");
    render(<App />);

    expect(redo()).toHaveAttribute("title", "No previous mission to repeat");
    fireEvent.click(redo());

    expect(putWaypoints).not.toHaveBeenCalled();
  });
});
