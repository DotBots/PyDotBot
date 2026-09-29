import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { type Layers, MapView } from "./MapView";
import type { Site } from "./types";

const FIELD = { x: 0, y: 0, w: 2000, h: 2000, name: "field", role: "field" as const };
const SITE: Site = {
  name: "c405-arena",
  anchor: "",
  extent_mm: [2000, 4000],
  areas: [FIELD],
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

const LAYERS: Layers = {
  batteryBars: true,
  waypoints: true,
  hotSpots: false,
  dotBots: true,
  trails: false,
  crashedOnly: false,
  allWaypoints: false,
  calibratedSpan: true,
};

const renderMap = (site: Site, layers: Layers = LAYERS) =>
  render(
    <MapView
      bots={[]}
      viewport={{ x: -500, y: -500, w: 3000, h: 5000 }}
      siteAreas={site.areas}
      hiddenAreas={new Set()}
      siteExtent={
        site.extent_mm ? { x: 0, y: 0, w: site.extent_mm[0], h: site.extent_mm[1] } : null
      }
      selection={new Set()}
      layers={layers}
      plannedMissions={[]}
      cam={{ scale: 1, tx: 0, ty: 0 }}
      setCam={() => {}}
      onGeom={() => {}}
      onSelect={() => {}}
      onAddWaypoint={() => {}}
      site={site}
      onZoom={() => {}}
    />,
  );

describe("the calibrated span on the map", () => {
  it("outlines the span, hatches the site and says how it was calibrated", () => {
    renderMap(SITE);
    const outline = screen.getByTestId("calibration-span-0");
    expect(outline.getAttribute("points")?.split(" ")).toHaveLength(4);
    expect(outline.textContent).toContain("a 500 mm square in the field");
    expect(screen.getByTestId("calibration-hatch")).toBeTruthy();
  });

  it("outlines without a hatch on a site with no extent", () => {
    renderMap({ ...SITE, extent_mm: null });
    expect(screen.getByTestId("calibration-span-0")).toBeTruthy();
    expect(screen.queryByTestId("calibration-hatch")).toBeNull();
  });

  it("draws nothing when the layer is off or nothing is loaded", () => {
    const { unmount } = renderMap(SITE, { ...LAYERS, calibratedSpan: false });
    expect(screen.queryByTestId("calibration-span")).toBeNull();
    unmount();
    renderMap({ ...SITE, calibration: null });
    expect(screen.queryByTestId("calibration-span")).toBeNull();
  });
});
