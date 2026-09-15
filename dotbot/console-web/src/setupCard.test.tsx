import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CalibrationPoint, CalibrationPreview, Site } from "./types";
import type { Calibration } from "./useCalibration";

vi.mock("./api", () => ({
  previewCalibrationPoints: vi.fn(),
}));

import { previewCalibrationPoints } from "./api";
import { SetupCard } from "./SetupCard";

const site: Site = {
  name: "c405-arena",
  anchor: "the arena's top-left corner",
  extent_mm: [3330, 4000],
  areas: [
    { x: 0, y: 0, w: 3330, h: 2000, name: "arena" },
    { x: 0, y: 2000, w: 3330, h: 2000, name: "annex" },
  ],
};

// What the controller resolves `arena:corners` to: the four corners in CORNERS
// order, each inset by the photodiode's distance to the two edges it rests on.
const point = (index: number, corner: string, x: number, y: number): CalibrationPoint => ({
  index,
  x,
  y,
  corner,
  area: "arena",
  where: `${corner} corner of arena`,
  how: "robot inside the rectangle",
  nose: corner.startsWith("top") ? "top" : "bottom",
  captured: false,
  reads: [],
  dropped: 0,
});

const CORNERS: CalibrationPreview = {
  reads: 25,
  points: [
    point(0, "top-left", 47, 18.5),
    point(1, "top-right", 3283, 18.5),
    point(2, "bottom-left", 47, 1981.5),
    point(3, "bottom-right", 3283, 1981.5),
  ],
};

const calibration = (): Calibration => ({
  busy: false,
  error: "",
  pushed: "",
  start: vi.fn(async () => {}),
  capture: vi.fn(async () => {}),
  redo: vi.fn(async () => {}),
  save: vi.fn(async () => {}),
  push: vi.fn(async () => {}),
  abandon: vi.fn(async () => {}),
});

const preview = vi.mocked(previewCalibrationPoints);

beforeEach(() => {
  vi.clearAllMocks();
  preview.mockResolvedValue(CORNERS);
});

describe("the Calibrate tab before a session", () => {
  it("opens on the site's arena and asks the controller for its corners", async () => {
    render(<SetupCard site={site} calibration={calibration()} device="" />);

    expect(screen.getByLabelText("Rectangle")).toHaveValue("arena");
    await waitFor(() =>
      expect(preview).toHaveBeenCalledWith(["arena:corners"]),
    );
  });

  it("shows the four resolved corners in capture order, in frame mm", async () => {
    render(<SetupCard site={site} calibration={calibration()} device="" />);

    await screen.findByText("top-left");
    expect(
      ["top-left", "top-right", "bottom-left", "bottom-right"].map(
        (name) => screen.getByText(name).textContent,
      ),
    ).toEqual(["top-left", "top-right", "bottom-left", "bottom-right"]);
    expect(screen.getByText("47, 19 mm")).toBeInTheDocument();
    expect(screen.getByText("3283, 1982 mm")).toBeInTheDocument();
  });

  it("seeds reads per point from the controller's own default", async () => {
    render(<SetupCard site={site} calibration={calibration()} device="" />);
    await waitFor(() =>
      expect(screen.getByLabelText("Reads per point")).toHaveValue("25"),
    );
  });

  it("starts a session over the chosen area, its reads and the chosen robot", async () => {
    const cal = calibration();
    render(<SetupCard site={site} calibration={cal} device="ABCD" />);
    await waitFor(() =>
      expect(screen.getByLabelText("Reads per point")).toHaveValue("25"),
    );

    fireEvent.change(screen.getByLabelText("Rectangle"), {
      target: { value: "annex" },
    });
    await waitFor(() => expect(preview).toHaveBeenCalledWith(["annex:corners"]));
    fireEvent.change(screen.getByLabelText("Reads per point"), {
      target: { value: "40" },
    });
    fireEvent.click(screen.getByText("Start"));

    expect(cal.start).toHaveBeenCalledWith(["annex:corners"], "annex", "ABCD", 40);
  });

  it("starts a session over a typed rectangle, which names no area", async () => {
    const cal = calibration();
    render(<SetupCard site={site} calibration={cal} device="" />);
    await waitFor(() =>
      expect(screen.getByLabelText("Reads per point")).toHaveValue("25"),
    );

    fireEvent.change(screen.getByLabelText("Rectangle"), {
      target: { value: "typed" },
    });
    fireEvent.change(screen.getByLabelText("x, y, w, h in frame mm"), {
      target: { value: "750,750,500,500" },
    });
    await waitFor(() =>
      expect(preview).toHaveBeenCalledWith(["750,750,500,500:corners"]),
    );

    fireEvent.click(screen.getByText("Start"));
    expect(cal.start).toHaveBeenCalledWith(
      ["750,750,500,500:corners"],
      "",
      "",
      25,
    );
  });

  it("does not start while the typed rectangle is incomplete", async () => {
    const cal = calibration();
    render(<SetupCard site={site} calibration={cal} device="" />);
    await waitFor(() =>
      expect(screen.getByLabelText("Reads per point")).toHaveValue("25"),
    );

    fireEvent.change(screen.getByLabelText("Rectangle"), {
      target: { value: "typed" },
    });
    fireEvent.change(screen.getByLabelText("x, y, w, h in frame mm"), {
      target: { value: "750,750" },
    });
    await screen.findByText(/Type four whole millimetres/);
    fireEvent.click(screen.getByText("Start"));

    expect(cal.start).not.toHaveBeenCalled();
    expect(screen.getByText(/Type four whole millimetres/)).toBeInTheDocument();
  });

  it("shows the controller's refusal rather than an empty list", async () => {
    preview.mockRejectedValue(new Error("unknown area 'balcony'"));
    render(<SetupCard site={site} calibration={calibration()} device="" />);

    expect(await screen.findByText("unknown area 'balcony'")).toBeInTheDocument();
  });
});
