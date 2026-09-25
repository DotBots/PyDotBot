import React from "react";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ACTION_KEY, SHORTCUTS_KEY } from "./shortcuts";
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
    bots: [bot("BADCAFE111111111", { state: "Bootloader" }), bot("DEADBEEF22222222")],
    site,
    session: null,
    setSession: () => {},
    viewport: VIEWPORT,
    wsUp: true,
  }),
}));

const act = vi.fn();
vi.mock("./useOrchestration", () => ({
  useOrchestration: () => ({
    logs: [],
    jobs: [],
    queue: {},
    fleetPct: 0,
    flashing: false,
    clearLogs: vi.fn(),
    flash: vi.fn(),
    act,
    busy: null,
    outcome: null,
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
  act.mockReset();
  cleanup();
  window.history.replaceState({}, "", "/");
  window.localStorage.clear();
});

const press = (key: string, target: Element = document.body) =>
  fireEvent.keyDown(target, { key });

describe("the testbed controls", () => {
  it("start and stop the whole fleet from the top bar, naming their keys", () => {
    render(<App />);
    const bar = screen.getByLabelText("Testbed controls");
    const start = within(bar).getByRole("button", { name: /Start/ });
    const stop = within(bar).getByRole("button", { name: /Stop/ });
    expect(stop).toHaveAttribute("title", `Stop the sandbox app on the whole fleet (${ACTION_KEY.stop})`);
    fireEvent.click(start);
    expect(act).toHaveBeenLastCalledWith("start", undefined, {
      eligible: ["BADCAFE111111111"],
      skipped: ["DEADBEEF22222222"],
    });
    fireEvent.click(stop);
    expect(act).toHaveBeenLastCalledWith("stop", undefined, {
      eligible: ["DEADBEEF22222222"],
      skipped: ["BADCAFE111111111"],
    });
  });

  it("act on the selection when there is one", () => {
    window.history.replaceState({}, "", "/?sel=2222");
    render(<App />);
    press(ACTION_KEY.stop);
    expect(act).toHaveBeenLastCalledWith("stop", ["DEADBEEF22222222"], {
      eligible: ["DEADBEEF22222222"],
      skipped: [],
    });
  });

  it("fire from their keys, once per press", () => {
    render(<App />);
    press(ACTION_KEY.start);
    fireEvent.keyDown(document.body, { key: ACTION_KEY.start, repeat: true });
    press(ACTION_KEY.stop.toLowerCase());
    expect(act.mock.calls.map((c) => c[0])).toEqual(["start", "stop"]);
  });

  it("leave a key typed into a field or held with Ctrl alone", () => {
    render(<App />);
    const input = document.createElement("input");
    document.body.appendChild(input);
    press(ACTION_KEY.stop, input);
    input.remove();
    fireEvent.keyDown(document.body, { key: ACTION_KEY.start, ctrlKey: true });
    expect(act).not.toHaveBeenCalled();
  });

  it("stop with the shortcuts panel open, but do not start", () => {
    render(<App />);
    press(SHORTCUTS_KEY);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    press(ACTION_KEY.start);
    press(ACTION_KEY.stop);
    expect(act.mock.calls.map((c) => c[0])).toEqual(["stop"]);
  });

  it("live in the top bar only, not in the left panel open or collapsed", () => {
    const railCopies = () =>
      [...document.querySelectorAll("div")].filter((d) =>
        /^[▶■]\s*(Start|Stop)$/.test((d.textContent ?? "").replace(/\u00a0/g, " ").trim()),
      );
    const { unmount } = render(<App />);
    expect(railCopies()).toEqual([]);
    expect(screen.getAllByRole("button", { name: /^[▶■] (Start|Stop)/ })).toHaveLength(2);
    unmount();
    window.history.replaceState({}, "", "/?rail=collapsed");
    render(<App />);
    expect(document.querySelector('[title="Start"], [title="Stop"]')).toBeNull();
    expect(screen.getAllByRole("button", { name: /^[▶■] (Start|Stop)/ })).toHaveLength(2);
  });
});
