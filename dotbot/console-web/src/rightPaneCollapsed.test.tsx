import React, { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { RightPane, RightTab } from "./RightPane";
import type { CalibrationSession, Site } from "./types";
import type { Calibration } from "./useCalibration";

const SITE: Site = {
  name: "c405-arena",
  anchor: "the arena's top-left corner",
  extent_mm: [2000, 4000],
  areas: [{ x: 0, y: 0, w: 2000, h: 2000, name: "arena" }],
};

const calibration = {
  busy: false,
  error: "",
  pushed: "",
  start: vi.fn(),
  capture: vi.fn(),
  redo: vi.fn(),
  save: vi.fn(),
  push: vi.fn(),
  abandon: vi.fn(),
} as unknown as Calibration;

const SESSION = {
  at: "arena:corners",
  site: "c405-arena",
  area: "arena",
  device: "",
  reads: 25,
  status: "collecting",
  outstanding: 0,
  captured: 0,
  total: 1,
  expected_error_mm: null,
  points: [
    {
      index: 0,
      x: 0,
      y: 0,
      corner: "top-left",
      area: "arena",
      where: "top-left corner of arena",
      how: "robot inside the rectangle",
      nose: "top",
      captured: false,
      reads: [],
      dropped: 0,
    },
  ],
  stations: [],
  unsolved: [],
  saved_path: null,
  saved_id: "",
  error: "",
} as CalibrationSession;

const Harness: React.FC<{ session?: CalibrationSession | null }> = ({
  session = null,
}) => {
  const [tab, setTab] = useState<RightTab>("robot");
  const [collapsed, setCollapsed] = useState(true);
  return (
    <>
      <div data-testid="state">{`${collapsed ? "collapsed" : "open"}:${tab}`}</div>
      <RightPane
        tab={tab}
        setTab={setTab}
        collapsed={collapsed}
        setCollapsed={setCollapsed}
        bots={[]}
        site={SITE}
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
        session={session}
        calibration={calibration}
        device=""
        onDeviceChange={() => {}}
        onCalibrationDone={() => {}}
      />
    </>
  );
};

const state = () => screen.getByTestId("state").textContent;

describe("the collapsed right pane", () => {
  it("shows one icon per tab, the way the rail's strip does", () => {
    render(<Harness />);
    expect(screen.getByTitle("Robot")).toBeInTheDocument();
    expect(screen.getByTitle("Layers")).toBeInTheDocument();
    expect(screen.getByTitle("Calibrate")).toBeInTheDocument();
  });

  it("keeps the Calibrate icon while a session runs", () => {
    render(<Harness session={SESSION} />);
    expect(screen.getByTitle("Calibrate")).toBeInTheDocument();
  });

  it("opens the pane on the tab whose icon was clicked", () => {
    render(<Harness />);
    expect(state()).toBe("collapsed:robot");

    fireEvent.click(screen.getByTitle("Layers"));

    expect(state()).toBe("open:layers");
    expect(screen.getByText("Camera layer")).toBeInTheDocument();
  });

  it("still collapses back from the open pane", () => {
    render(<Harness />);
    fireEvent.click(screen.getByTitle("Layers"));
    fireEvent.click(screen.getByTitle("Collapse the right pane"));
    expect(state()).toBe("collapsed:layers");
    expect(screen.getByTitle("Layers")).toBeInTheDocument();
  });
});
