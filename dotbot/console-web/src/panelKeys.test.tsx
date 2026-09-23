import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ACTION_KEY } from "./shortcuts";
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

const press = (key: string, target: Element = document.body) =>
  fireEvent.keyDown(target, { key });
const toggle = (verb: "Collapse" | "Expand", side: "left" | "right") =>
  screen.queryByRole("button", { name: `${verb} the ${side} panel` });

describe("the side panel keys", () => {
  it("collapse and expand the left panel", () => {
    render(<App />);
    expect(toggle("Collapse", "left")).toBeInTheDocument();
    press(ACTION_KEY.leftPanel);
    expect(toggle("Expand", "left")).toBeInTheDocument();
    expect(toggle("Collapse", "right")).toBeInTheDocument();
    press(ACTION_KEY.leftPanel);
    expect(toggle("Collapse", "left")).toBeInTheDocument();
  });

  it("collapse and expand the right panel", () => {
    render(<App />);
    press(ACTION_KEY.rightPanel);
    expect(toggle("Expand", "right")).toBeInTheDocument();
    expect(toggle("Collapse", "left")).toBeInTheDocument();
    press(ACTION_KEY.rightPanel);
    expect(toggle("Collapse", "right")).toBeInTheDocument();
  });

  it("are left alone while a field has focus", () => {
    render(<App />);
    const slider = screen.getByLabelText("Zoom");
    slider.focus();
    press(ACTION_KEY.leftPanel, slider);
    press(ACTION_KEY.rightPanel, slider);
    const input = document.createElement("input");
    document.body.appendChild(input);
    press(ACTION_KEY.leftPanel, input);
    press(ACTION_KEY.rightPanel, input);
    input.remove();
    expect(toggle("Collapse", "left")).toBeInTheDocument();
    expect(toggle("Collapse", "right")).toBeInTheDocument();
  });

  it("do what the buttons do, which name their key", () => {
    render(<App />);
    const left = toggle("Collapse", "left")!;
    expect(left).toHaveAttribute("title", `Collapse the left panel (${ACTION_KEY.leftPanel})`);
    fireEvent.click(left);
    fireEvent.click(toggle("Collapse", "right")!);
    expect(toggle("Expand", "left")).toBeInTheDocument();
    expect(toggle("Expand", "right")).toBeInTheDocument();
    press(ACTION_KEY.leftPanel);
    expect(toggle("Collapse", "left")).toBeInTheDocument();
  });

  it("start the left panel collapsed from ?rail=collapsed", () => {
    window.history.replaceState({}, "", "/?rail=collapsed");
    render(<App />);
    expect(toggle("Expand", "left")).toBeInTheDocument();
  });
});
