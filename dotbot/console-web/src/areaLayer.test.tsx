import React, { useState } from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { saveHiddenAreas, toggleHidden } from "./areas";
import { MapView } from "./MapView";
import { RightPane, RightTab } from "./RightPane";
import type { Area, Site } from "./types";
import type { Calibration } from "./useCalibration";

const ARENA: Area = { x: 0, y: 0, w: 2000, h: 2000, name: "arena" };
const ANNEX: Area = { x: 0, y: 2000, w: 2000, h: 2000, name: "annex" };
const C405: Site = {
  name: "c405-arena",
  anchor: "the arena's top-left corner",
  extent_mm: [2000, 4000],
  areas: [ARENA, ANNEX],
};
const VIEWPORT: Area = { x: -2000, y: -2000, w: 6000, h: 8000 };

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

// The map and the Layers tab over one hidden set, exactly as App wires them.
const Harness: React.FC = () => {
  const [hiddenAreas, setHiddenAreas] = useState<Set<string>>(new Set());
  const [tab, setTab] = useState<RightTab>("layers");
  return (
    <>
      <div data-testid="map">
        <MapView
          bots={[]}
          viewport={VIEWPORT}
          siteAreas={C405.areas}
          hiddenAreas={hiddenAreas}
          siteExtent={{ x: 0, y: 0, w: 2000, h: 4000, name: C405.name }}
          selection={new Set()}
          layers={{
            batteryBars: true,
            waypoints: true,
            hotSpots: false,
            dotBots: true,
            trails: false,
            crashedOnly: false,
          }}
          plannedMissions={[]}
          cam={{ scale: 1, tx: 0, ty: 0 }}
          setCam={() => {}}
          onGeom={() => {}}
          onSelect={() => {}}
          onAddWaypoint={() => {}}
          site={C405}
          onZoom={() => {}}
        />
      </div>
      <div data-testid="pane">
        <RightPane
          tab={tab}
          setTab={setTab}
          collapsed={false}
          setCollapsed={() => {}}
          bots={[]}
          site={C405}
          hiddenAreas={hiddenAreas}
          onAreaToggle={(name) =>
            setHiddenAreas((prev) => {
              const next = toggleHidden(prev, name);
              saveHiddenAreas(next);
              return next;
            })
          }
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
          session={null}
          calibration={calibration}
          device=""
          onDeviceChange={() => {}}
          onCalibrationDone={() => {}}
        />
      </div>
    </>
  );
};

afterEach(() => {
  window.localStorage.clear();
  vi.restoreAllMocks();
});

describe("Layers > Areas", () => {
  it("hides one outline and leaves the other, without any controller call", () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    render(<Harness />);

    const map = screen.getByTestId("map");
    expect(within(map).getByText("arena")).toBeInTheDocument();
    expect(within(map).getByText("annex")).toBeInTheDocument();

    fireEvent.click(within(screen.getByTestId("pane")).getByText("annex"));

    expect(within(map).queryByText("annex")).not.toBeInTheDocument();
    expect(within(map).getByText("arena")).toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("remembers the hidden set in this browser", () => {
    render(<Harness />);
    fireEvent.click(within(screen.getByTestId("pane")).getByText("annex"));
    expect(window.localStorage.getItem("dotbot.console.hiddenAreas")).toBe(
      '["annex"]',
    );
  });
});
