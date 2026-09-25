import React from "react";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
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
    { x: 900, y: 1200, heading_deg: 90 },
  ],
});
const finished = bot("FEEDFACE44444444", {
  waypoints: [
    { x: 100, y: 100 },
    { x: 300, y: 300 },
  ],
  mission: { state: "arrived", index: 1, reason: null, code: null },
});

vi.mock("./useFleet", () => ({
  useFleet: () => ({
    bots: [idle, underWay, finished],
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

const openMissions = (sel = "") =>
  window.history.replaceState({}, "", `/?rail=missions${sel ? `&sel=${sel}` : ""}`);
const cleared = () => vi.mocked(putWaypoints).mock.calls.map(([id, , , points]) => [id, points]);

describe("the waypoints on the controller", () => {
  it("lists every robot holding a batch, whoever sent it, under way first", () => {
    openMissions();
    render(<App />);
    const list = screen.getByRole("region", { name: "Waypoints on the controller" });
    expect(within(list).getByText("On the controller · 2")).toBeInTheDocument();
    const rows = within(list).getAllByTestId(/^held-/).map((r) => r.dataset.testid);
    expect(rows).toEqual([`held-${underWay.id}`, `held-${finished.id}`]);
    expect(within(list).getByText("arrived")).toBeInTheDocument();
    fireEvent.click(within(list).getByLabelText("Show the points of 2222"));
    expect(within(list).getByText("900, 1200 @ 90°")).toBeInTheDocument();
  });

  it("clears one robot with its own button, as an empty batch", () => {
    openMissions();
    render(<App />);
    fireEvent.click(screen.getByLabelText("Clear the waypoints of 2222"));
    expect(cleared()).toEqual([[underWay.id, []]]);
    expect(screen.getByText("Waypoints cleared · 1 bot")).toBeInTheDocument();
  });

  it("clears every robot holding a batch at once", () => {
    openMissions();
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Clear all" }));
    expect(cleared()).toEqual([
      [underWay.id, []],
      [finished.id, []],
    ]);
  });

  it("clears only the selection's", () => {
    openMissions("4444,1111");
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Clear selected (1)" }));
    expect(cleared()).toEqual([[finished.id, []]]);
  });

  it("draws every robot's waypoints on the map on request, not only the selection's", () => {
    openMissions("1111");
    render(<App />);
    expect(screen.queryByTestId(`waypoint-${underWay.id}-1`)).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Show every robot's waypoints on the map"));
    expect(screen.getByTestId(`waypoint-${underWay.id}-1`)).toBeInTheDocument();
    expect(screen.getByTestId(`waypoint-${finished.id}-1`)).toBeInTheDocument();
  });
});
