import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MapView } from "./MapView";
import type { Site } from "./types";

const SITE: Site = {
  name: "c405-arena",
  anchor: "",
  extent_mm: [2000, 4000],
  areas: [],
  walls: [{ name: "door", points: [[0, 0], [0, 4000]] }],
  obstacles: [{ name: "", points: [[1500, 2500], [1700, 2500], [1700, 2700]] }],
};

describe("MapView barriers", () => {
  it("draws the site's walls and obstacles", () => {
    render(
      <MapView
        bots={[]}
        viewport={{ x: -500, y: -500, w: 3000, h: 5000 }}
        siteAreas={[]}
        hiddenAreas={new Set()}
        siteExtent={{ x: 0, y: 0, w: 2000, h: 4000, name: SITE.name }}
        selection={new Set()}
        layers={{
          batteryBars: true,
          waypoints: true,
          hotSpots: false,
          dotBots: true,
          trails: false,
          crashedOnly: false,
          lostBots: false,
          allWaypoints: false,
          calibratedSpan: true,
        }}
        plannedMissions={[]}
        cam={{ scale: 1, tx: 0, ty: 0 }}
        setCam={() => {}}
        onGeom={() => {}}
        onSelect={() => {}}
        onAddWaypoint={() => {}}
        site={SITE}
        onZoom={() => {}}
      />,
    );
    expect(screen.getByTestId("wall-door").getAttribute("points")?.split(" ")).toHaveLength(2);
    expect(screen.getByTestId("obstacle-0").getAttribute("points")?.split(" ")).toHaveLength(3);
  });
});
