import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Site } from "./types";

const site: Site = {
  name: "c405-arena",
  anchor: "",
  extent_mm: [2000, 2000],
  areas: [{ x: 0, y: 0, w: 2000, h: 2000, name: "field", role: "field" }],
  field: "field",
  calibration: {
    id: "ac893d2d85e3068c",
    tag: "",
    created_at: "2026-09-10T09:12:00Z",
    placements: [
      {
        points_mm: [
          [750, 750],
          [1250, 750],
          [750, 1250],
          [1250, 1250],
        ],
        points_from: { kind: "square", side_mm: 500 },
      },
    ],
  },
};

vi.mock("./useFleet", () => ({
  useFleet: () => ({
    bots: [],
    site,
    session: null,
    setSession: () => {},
    viewport: { x: 0, y: 0, w: 2000, h: 2000 },
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
}));

import { App } from "./App";

afterEach(() => {
  window.localStorage.clear();
});

describe("the calibrated span toggle", () => {
  it("is listed under Layers and on by default", () => {
    render(<App />);
    expect(screen.getByText("Calibrated span")).toBeTruthy();
    expect(screen.getByTestId("calibration-span")).toBeTruthy();
  });

  it("is remembered by this browser once switched off", () => {
    const { unmount } = render(<App />);
    fireEvent.click(screen.getByText("Calibrated span"));
    expect(screen.queryByTestId("calibration-span")).toBeNull();
    unmount();

    render(<App />);
    expect(screen.queryByTestId("calibration-span")).toBeNull();
    fireEvent.click(screen.getByText("Calibrated span"));
    expect(screen.getByTestId("calibration-span")).toBeTruthy();
  });
});
