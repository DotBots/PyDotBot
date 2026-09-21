import React, { useState } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { loadRobotShapes, saveRobotShapes } from "./BotGlyph";
import { RightPane } from "./RightPane";
import type { Calibration } from "./useCalibration";

beforeEach(() => window.localStorage.clear());
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("the robot shapes choice, per browser", () => {
  it("defaults to the robot shape", () => {
    expect(loadRobotShapes()).toBe(true);
  });

  it("reads back what was saved", () => {
    saveRobotShapes(false);
    expect(loadRobotShapes()).toBe(false);
    saveRobotShapes(true);
    expect(loadRobotShapes()).toBe(true);
  });

  it("falls back to the robot shape when storage refuses", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(loadRobotShapes()).toBe(true);
  });
});

const Harness: React.FC = () => {
  const [on, setOn] = useState(true);
  return (
    <>
      <div data-testid="shapes">{String(on)}</div>
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
        robotShapes={on}
        onRobotShapesToggle={() => setOn((prev) => !prev)}
        session={null}
        calibration={{} as Calibration}
        device=""
        onDeviceChange={() => {}}
        onCalibrationDone={() => {}}
      />
    </>
  );
};

describe("the Robot shapes row on the Layers tab", () => {
  it("flips the choice when clicked", () => {
    render(<Harness />);
    fireEvent.click(screen.getByText("Robot shapes"));
    expect(screen.getByTestId("shapes").textContent).toBe("false");
    fireEvent.click(screen.getByText("Robot shapes"));
    expect(screen.getByTestId("shapes").textContent).toBe("true");
  });
});
