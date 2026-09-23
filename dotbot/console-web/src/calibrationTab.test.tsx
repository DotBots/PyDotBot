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

import { abandonCalibration, startCalibration } from "./api";
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
  it("is present with no session, and carries the setup card", () => {
    render(<App />);
    expect(tabNames()).toEqual(["Robot", "Layers", "Calibrate"]);

    fireEvent.click(screen.getByText("Calibrate"));
    expect(screen.getByLabelText("Rectangle")).toBeInTheDocument();
    expect(screen.getByText("Start")).toBeInTheDocument();
    expect(screen.queryByText("Capture")).not.toBeInTheDocument();
  });

  it("opens on the rail's Calibrate action rather than starting a session", () => {
    render(<App />);
    fireEvent.click(screen.getByText("Localization"));
    fireEvent.click(screen.getByText("Calibrate lighthouse"));

    expect(startCalibration).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Rectangle")).toBeInTheDocument();
  });

  it("is selected when a session starts", () => {
    const { rerender } = render(<App />);
    session = SESSION;
    act(() => {
      rerender(<App />);
    });

    expect(tabNames()).toEqual(["Robot", "Layers", "Calibrate"]);
    // The step card takes the tab over from the setup card, so the capture
    // button is on screen the moment the session opens.
    expect(screen.getByText("Capture")).toBeInTheDocument();
  });

  it("leaves Robot and Layers reachable during a session", () => {
    const { rerender } = render(<App />);
    session = SESSION;
    act(() => {
      rerender(<App />);
    });

    fireEvent.click(screen.getByText("Layers"));
    expect(screen.getByText("Areas")).toBeInTheDocument();
    // The card left with the tab; it is not stacked above the others.
    expect(screen.queryByText("Capture")).not.toBeInTheDocument();
  });

  it("hands the pane back on Done, to the tab that was open", () => {
    const { rerender } = render(<App />);
    // Robot was the tab in use before calibration.
    fireEvent.click(screen.getByText("Robot"));

    session = SESSION;
    act(() => {
      rerender(<App />);
    });
    expect(screen.getByText("Capture")).toBeInTheDocument();

    session = null;
    act(() => {
      rerender(<App />);
    });

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

// A capture from a robot's own button reaches the console only as a session
// update: point k captured, the pressing robot as the session's device.
const afterCaptures = (
  n: number,
  device: string,
  over: Partial<CalibrationSession> = {},
): CalibrationSession => ({
  ...SESSION,
  device,
  captured: n,
  outstanding: n < 4 ? n : null,
  points: SESSION.points.map((p) => ({ ...p, captured: p.index < n })),
  ...over,
});

const capturing = () =>
  screen.getByPlaceholderText(/click a robot on the map/) as HTMLInputElement;

describe("the step card following the robot's button", () => {
  it("advances the step and adopts the robot that pressed", () => {
    const { rerender } = render(<App />);
    session = SESSION;
    act(() => rerender(<App />));
    expect(screen.getByText("Step 1 of 4")).toBeInTheDocument();
    expect(capturing().value).toBe("");

    session = afterCaptures(1, "ABCD");
    act(() => rerender(<App />));

    expect(screen.getByText("Step 2 of 4")).toBeInTheDocument();
    expect(capturing().value).toBe("ABCD");
  });

  it("replaces a robot typed in the card with the one that pressed", () => {
    const { rerender } = render(<App />);
    session = SESSION;
    act(() => rerender(<App />));
    fireEvent.change(capturing(), { target: { value: "1234" } });
    expect(capturing().value).toBe("1234");

    session = afterCaptures(1, "ABCD");
    act(() => rerender(<App />));
    expect(capturing().value).toBe("ABCD");

    // A pick made after that capture stands until the next one.
    fireEvent.change(capturing(), { target: { value: "5678" } });
    session = afterCaptures(1, "ABCD");
    act(() => rerender(<App />));
    expect(capturing().value).toBe("5678");
  });

  it("moves to save and push after the last point, never a NaN step", () => {
    const { rerender } = render(<App />);
    session = afterCaptures(3, "ABCD");
    act(() => rerender(<App />));
    expect(screen.getByText("Step 4 of 4")).toBeInTheDocument();

    // The notification of a complete session, with `outstanding` absent as
    // a sparse serialisation drops a null: the card reads the points.
    const complete: Partial<CalibrationSession> = afterCaptures(4, "ABCD");
    delete complete.outstanding;
    session = complete as CalibrationSession;
    act(() => rerender(<App />));

    expect(screen.queryByText(/NaN/)).not.toBeInTheDocument();
    expect(screen.getByText("All 4 points captured")).toBeInTheDocument();
    expect(screen.getByText("After the last point")).toBeInTheDocument();
    expect(screen.getByText("Save")).toBeInTheDocument();
    expect(screen.getByText("Push")).toBeInTheDocument();
    expect(screen.queryByText("Capture")).not.toBeInTheDocument();
  });
});
