import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { MrtaStatus } from "./mrta";
import type { Site, UnifiedBot } from "./types";

// The console shows the MRTA control only once useMrta confirms the
// controller actually proxies to an MRTA server (`--mrta-url` set); by
// default `configured` is false and the button must not render at all,
// rather than appear greyed out as "N/A". See useMrta.ts / api.ts.
//
// vi.hoisted() so this mutable stub is safe to reference from the vi.mock
// factory below, which vitest hoists above every import in this file.
const { mrtaMock } = vi.hoisted(() => ({
  mrtaMock: {
    status: { state: "unavailable", bots: null, detail: null } as MrtaStatus,
    configured: false,
    toggle: () => {},
  },
}));
vi.mock("./useMrta", () => ({
  useMrta: () => mrtaMock,
}));

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

vi.mock("./useFleet", () => ({
  useFleet: () => ({
    bots: [bot("BADCAFE111111111")],
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
  mrtaMock.configured = false;
  mrtaMock.status = { state: "unavailable", bots: null, detail: null };
});
afterEach(() => {
  rectSpy.mockRestore();
  cleanup();
  window.history.replaceState({}, "", "/");
  window.localStorage.clear();
});

describe("the MRTA control's default-off visibility", () => {
  it("renders no MRTA control when the controller has no --mrta-url set", () => {
    mrtaMock.configured = false;
    render(<App />);
    expect(screen.queryByText("MRTA")).not.toBeInTheDocument();
  });

  it("renders the MRTA control once the controller confirms it is configured", () => {
    mrtaMock.configured = true;
    mrtaMock.status = { state: "off", bots: null, detail: null };
    render(<App />);
    expect(screen.getByText("MRTA")).toBeInTheDocument();
  });
});
