import React from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CalibrationSession, Site } from "./types";

// The fleet hook is the one seam calibration mode turns on: the controller
// owns the session, so App only ever sees it appear and disappear.
let session: CalibrationSession | null = null;
const site: Site = {
  name: "c405-arena",
  anchor: "the arena's top-left corner",
  extent_mm: [2000, 4000],
  areas: [
    { x: 0, y: 0, w: 2000, h: 2000, name: "arena" },
    { x: 0, y: 2000, w: 2000, h: 2000, name: "annex" },
  ],
};

vi.mock("./useFleet", () => ({
  useFleet: () => ({
    bots: [],
    site,
    session,
    setSession: (next: CalibrationSession | null) => {
      session = next;
    },
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
  putWaypoints: vi.fn(async () => {}),
  abandonCalibration: vi.fn(async () => {}),
  captureCalibrationPoint: vi.fn(),
  pushCalibration: vi.fn(),
  redoCalibrationPoint: vi.fn(),
  saveCalibration: vi.fn(),
  startCalibration: vi.fn(),
}));

import { abandonCalibration } from "./api";
import { App } from "./App";

const SESSION: CalibrationSession = {
  at: "arena:corners",
  site: "c405-arena",
  area: "arena",
  device: "",
  reads: 25,
  status: "collecting",
  outstanding: 0,
  captured: 0,
  total: 4,
  expected_error_mm: null,
  points: [0, 1, 2, 3].map((index) => ({
    index,
    x: index % 2 === 0 ? 0 : 2000,
    y: index < 2 ? 0 : 2000,
    corner: "top-left",
    area: "arena",
    where: "top-left corner of arena",
    how: "robot inside the rectangle",
    nose: "top",
    captured: false,
    reads: [],
    dropped: 0,
  })),
  stations: [],
  unsolved: [],
  saved_path: null,
  saved_id: "",
  error: "",
};

const tabNames = () =>
  ["Robot", "Layers", "Calibrate"].filter((name) => screen.queryByText(name));

beforeEach(() => {
  session = null;
  vi.clearAllMocks();
});

afterEach(() => {
  window.localStorage.clear();
});

describe("the Calibrate tab", () => {
  it("is absent while no session is open", () => {
    render(<App />);
    expect(tabNames()).toEqual(["Robot", "Layers"]);
  });

  it("appears and is selected when a session starts", () => {
    const { rerender } = render(<App />);
    session = SESSION;
    act(() => {
      rerender(<App />);
    });

    expect(tabNames()).toEqual(["Robot", "Layers", "Calibrate"]);
    // The step card is the tab's whole content, so the capture button is on
    // screen the moment the session opens.
    expect(screen.getByText("Capture")).toBeInTheDocument();
  });

  it("leaves Robot and Layers reachable during a session", () => {
    const { rerender } = render(<App />);
    session = SESSION;
    act(() => {
      rerender(<App />);
    });

    fireEvent.click(screen.getByText("Layers"));
    expect(screen.getByText("Camera layer")).toBeInTheDocument();
    // The card left with the tab; it is not stacked above the others.
    expect(screen.queryByText("Capture")).not.toBeInTheDocument();
  });

  it("disappears on Done, and the pane returns to the tab that was open", () => {
    const { rerender } = render(<App />);
    // Robot was the tab in use before calibration.
    fireEvent.click(screen.getByText("Robot"));

    session = SESSION;
    act(() => {
      rerender(<App />);
    });
    expect(tabNames()).toEqual(["Robot", "Layers", "Calibrate"]);

    session = null;
    act(() => {
      rerender(<App />);
    });

    expect(tabNames()).toEqual(["Robot", "Layers"]);
    expect(screen.queryByText("Capture")).not.toBeInTheDocument();
    // Robot is selected again: its empty-state line is what the tab shows.
    expect(screen.getByText("Select a bot to inspect it.")).toBeInTheDocument();
  });

  it("asks the controller to close the session when Done is pressed", () => {
    const { rerender } = render(<App />);
    session = SESSION;
    act(() => {
      rerender(<App />);
    });

    fireEvent.click(screen.getByText("Done"));
    expect(abandonCalibration).toHaveBeenCalled();
  });
});
