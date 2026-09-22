import React from "react";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SHORTCUT_GROUPS, isKey, isModifier, modifierLabel, onMac } from "./shortcuts";
import type { Site, UnifiedBot } from "./types";

const site: Site = {
  name: "c405-arena",
  anchor: "the arena's top-left corner",
  extent_mm: [2000, 4000],
  areas: [{ x: 0, y: 0, w: 2000, h: 2000, name: "arena" }],
};
const VIEWPORT = { x: -2000, y: -2000, w: 6000, h: 8000 };

const bot: UnifiedBot = {
  id: "BADCAFE111111111",
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
};

vi.mock("./useFleet", () => ({
  useFleet: () => ({
    bots: [bot],
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
const dialog = () => screen.queryByRole("dialog");

describe("the shortcuts panel", () => {
  it("opens on its key with nothing selected, and takes focus", () => {
    render(<App />);
    expect(dialog()).not.toBeInTheDocument();
    press("?");
    const panel = screen.getByRole("dialog", { name: "Keyboard and mouse shortcuts" });
    expect(panel).toHaveAttribute("aria-modal", "true");
    expect(document.activeElement).toBe(panel);
  });

  it("stays shut while a robot is selected", () => {
    window.history.replaceState({}, "", "/?sel=1111");
    render(<App />);
    press("?");
    expect(dialog()).not.toBeInTheDocument();
  });

  it("stays shut while a field has focus, the zoom slider included", () => {
    render(<App />);
    const slider = screen.getByLabelText("Zoom");
    slider.focus();
    press("?", slider);
    expect(dialog()).not.toBeInTheDocument();
  });

  it("closes on Escape, on its own key again, and on a press outside", () => {
    render(<App />);
    press("?");
    press("Escape");
    expect(dialog()).not.toBeInTheDocument();

    press("?");
    press("?");
    expect(dialog()).not.toBeInTheDocument();

    press("?");
    fireEvent.pointerDown(screen.getByTestId("shortcuts-backdrop"));
    expect(dialog()).not.toBeInTheDocument();

    press("?");
    fireEvent.pointerDown(screen.getByRole("dialog"));
    expect(dialog()).toBeInTheDocument();
  });

  it("gives focus back to the control that had it", () => {
    render(<App />);
    const hint = screen.getByTitle("Keyboard and mouse shortcuts");
    hint.focus();
    fireEvent.click(hint);
    expect(document.activeElement).toBe(screen.getByRole("dialog"));
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(dialog()).not.toBeInTheDocument();
    expect(document.activeElement).toBe(hint);
  });

  it("opens from the hint whatever is selected", () => {
    window.history.replaceState({}, "", "/?sel=1111");
    render(<App />);
    fireEvent.click(screen.getByTitle("Keyboard and mouse shortcuts"));
    expect(dialog()).toBeInTheDocument();
  });

  it("prints every row of the table, grouped by surface, in this platform's keys", () => {
    render(<App />);
    press("?");
    const panel = screen.getByRole("dialog");
    const mac = onMac();
    for (const group of SHORTCUT_GROUPS) {
      const section = within(panel).getByRole("region", { name: `${group.surface} shortcuts` });
      expect(within(section).getByRole("heading", { name: group.surface })).toBeInTheDocument();
      const rows = within(section).getAllByRole("row");
      expect(rows).toHaveLength(group.rows.length);
      group.rows.forEach((row, i) => {
        expect(rows[i]).toHaveTextContent(row.does);
        for (const key of row.keys) {
          const label = isModifier(key) ? modifierLabel(key, mac) : key;
          expect(rows[i]).toHaveTextContent(label);
          if (isModifier(key) || isKey(key)) {
            expect(within(rows[i]).getByText(label, { selector: "kbd" })).toBeInTheDocument();
          }
        }
      });
    }
  });
});
