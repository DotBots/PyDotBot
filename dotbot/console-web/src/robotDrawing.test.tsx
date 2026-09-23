import React, { useState } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  DEFAULT_ROBOT_DRAWING,
  RobotDrawing,
  loadRobotDrawing,
  saveRobotDrawing,
} from "./robotDrawing";
import { RightPane } from "./RightPane";
import type { Calibration } from "./useCalibration";

const KEY = "dotbot.console.robotDrawing";

beforeEach(() => window.localStorage.clear());
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("the robot drawing choice, per browser", () => {
  it("defaults to Body with the possible footprint on", () => {
    expect(loadRobotDrawing()).toEqual({ mode: "body", footprint: true });
  });

  it("reads back what was saved", () => {
    saveRobotDrawing({ mode: "sensor", footprint: false });
    expect(loadRobotDrawing()).toEqual({ mode: "sensor", footprint: false });
  });

  it("keeps each field that is valid and defaults the other", () => {
    window.localStorage.setItem(KEY, JSON.stringify({ mode: "sensor", footprint: "yes" }));
    expect(loadRobotDrawing()).toEqual({ mode: "sensor", footprint: true });
    window.localStorage.setItem(KEY, JSON.stringify({ mode: "robot", footprint: false }));
    expect(loadRobotDrawing()).toEqual({ mode: "body", footprint: false });
  });

  it("reads anything but a stored record as the default", () => {
    for (const raw of ["not json", "true", "[]", "null"]) {
      window.localStorage.setItem(KEY, raw);
      expect(loadRobotDrawing()).toEqual(DEFAULT_ROBOT_DRAWING);
    }
  });

  it("falls back to the default when storage refuses", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(loadRobotDrawing()).toEqual(DEFAULT_ROBOT_DRAWING);
  });

  it("forgets quietly when storage refuses a save", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(() => saveRobotDrawing({ mode: "sensor", footprint: true })).not.toThrow();
  });
});

const Harness: React.FC = () => {
  const [drawing, setDrawing] = useState<RobotDrawing>(DEFAULT_ROBOT_DRAWING);
  return (
    <>
      <div data-testid="drawing">{JSON.stringify(drawing)}</div>
      <RightPane
        tab="layers"
        setTab={() => {}}
        collapsed={false}
        setCollapsed={() => {}}
        bots={[]}
        site={null}
        hiddenAreas={new Set()}
        onAreaToggle={() => {}}
        layers={{
          batteryBars: true,
          waypoints: true,
          hotSpots: false,
          dotBots: true,
          trails: false,
          crashedOnly: false,
        }}
        layerRows={[]}
        onLayerToggle={() => {}}
        robotDrawing={drawing}
        onRobotDrawing={setDrawing}
        session={null}
        calibration={{} as Calibration}
        device=""
        onDeviceChange={() => {}}
        onCalibrationDone={() => {}}
      />
    </>
  );
};

describe("the robot drawing control on the Layers tab", () => {
  const state = () => JSON.parse(screen.getByTestId("drawing").textContent!);
  const hint = () => screen.getByTestId("robot-drawing-hint").textContent;

  it("switches between Body and Sensor", () => {
    render(<Harness />);
    expect(screen.getByRole("radio", { name: "Body" })).toHaveAttribute("aria-checked", "true");
    fireEvent.click(screen.getByRole("radio", { name: "Sensor" }));
    expect(state()).toEqual({ mode: "sensor", footprint: true });
    expect(screen.getByRole("radio", { name: "Sensor" })).toHaveAttribute("aria-checked", "true");
    fireEvent.click(screen.getByRole("radio", { name: "Body" }));
    expect(state().mode).toBe("body");
  });

  it("flips the possible footprint", () => {
    render(<Harness />);
    fireEvent.click(screen.getByText("Possible footprint"));
    expect(state()).toEqual({ mode: "body", footprint: false });
  });

  it("gives a different hint for each mode and checkbox", () => {
    render(<Harness />);
    const seen = new Set<string | null>([hint()]);
    fireEvent.click(screen.getByText("Possible footprint"));
    seen.add(hint());
    fireEvent.click(screen.getByRole("radio", { name: "Sensor" }));
    seen.add(hint());
    fireEvent.click(screen.getByText("Possible footprint"));
    seen.add(hint());
    expect(seen.size).toBe(4);
  });
});
