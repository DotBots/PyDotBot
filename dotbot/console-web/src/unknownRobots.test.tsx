import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearWaypoints, putWaypointBatches } from "./api";
import type { Site, UnifiedBot } from "./types";

const site: Site = {
  name: "c405-arena",
  anchor: "the arena's top-left corner",
  extent_mm: [2000, 4000],
  areas: [{ x: 0, y: 0, w: 2000, h: 2000, name: "arena" }],
};

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
  waypoints: [{ x: 500, y: 500 }, { x: 900, y: 900 }],
  trail: [],
  image: null,
  resetCause: null,
  severity: "normal",
  batteryPct: 80,
  batteryLevel: "ok",
  swarmit: null,
  ...extra,
});

const bots = [
  bot("BADCAFE111111111"),
  bot("DEADBEEF22222222"),
  bot("B0B0F00D33333333", { nav: "auto" }),
];

vi.mock("./useFleet", () => ({
  useFleet: () => ({
    bots,
    site,
    session: null,
    setSession: () => {},
    viewport: { x: -2000, y: -2000, w: 6000, h: 8000 },
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
  putWaypointBatches: vi.fn(),
  clearWaypoints: vi.fn(),
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
  rectSpy = vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
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
});
afterEach(() => {
  rectSpy.mockRestore();
  cleanup();
  window.history.replaceState({}, "", "/");
  window.localStorage.clear();
});

const select = (suffixes: string) => window.history.replaceState({}, "", `/?sel=${suffixes}`);

describe("robots the controller does not know", () => {
  it("are named in a notice after a bulk send", async () => {
    vi.mocked(putWaypointBatches).mockResolvedValue({
      applied: ["BADCAFE111111111"],
      unknown: ["DEADBEEF22222222"],
    });
    select("1111,2222");
    render(<App />);

    fireEvent.click(screen.getByTestId("redo-mission"));

    expect(await screen.findByText("1 robot not found: 2222")).toBeInTheDocument();
  });

  it("are named in a notice after a stop", async () => {
    vi.mocked(clearWaypoints).mockResolvedValue({
      applied: [],
      unknown: ["B0B0F00D33333333"],
    });
    select("3333");
    render(<App />);

    fireEvent.click(screen.getByText("■ Stop nav"));

    expect(await screen.findByText("1 robot not found: 3333")).toBeInTheDocument();
  });

  it("leave the usual message alone when every robot is known", async () => {
    vi.mocked(putWaypointBatches).mockResolvedValue({
      applied: ["BADCAFE111111111", "DEADBEEF22222222"],
      unknown: [],
    });
    select("1111,2222");
    render(<App />);

    fireEvent.click(screen.getByTestId("redo-mission"));

    expect(await screen.findByText("Mission re-sent to 2 bots")).toBeInTheDocument();
    expect(screen.queryByText(/not found/)).not.toBeInTheDocument();
  });
});
