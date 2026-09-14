import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { MapView } from "./MapView";
import type { Area, Site } from "./types";
import type { Camera } from "./zoom";

const ARENA: Area = { x: 0, y: 0, w: 2000, h: 2000, name: "arena" };
const C405: Site = {
  name: "c405-arena",
  anchor: "the arena's top-left corner",
  extent_mm: [2000, 4000],
  areas: [ARENA],
};
const VIEWPORT: Area = { x: -2000, y: -2000, w: 6000, h: 8000 };

const Harness: React.FC<{ cam: Camera }> = ({ cam }) => (
  <MapView
    bots={[]}
    viewport={VIEWPORT}
    siteAreas={C405.areas}
    hiddenAreas={new Set()}
    siteExtent={{ x: 0, y: 0, w: 2000, h: 4000, name: C405.name }}
    selection={new Set()}
    layers={{
      batteryBars: true,
      waypoints: true,
      hotSpots: false,
      dotBots: true,
      trueScale: true,
      trails: false,
      crashedOnly: false,
    }}
    plannedMissions={[]}
    cam={cam}
    setCam={() => {}}
    onGeom={() => {}}
    onSelect={() => {}}
    onAddWaypoint={() => {}}
    site={C405}
    onZoom={() => {}}
  />
);

const gridStyle = (cam: Camera) => {
  render(<Harness cam={cam} />);
  const el = screen.getByTestId("map-grid");
  return {
    image: el.style.backgroundImage,
    size: el.style.backgroundSize,
  };
};

afterEach(cleanup);

describe("the drawn grid", () => {
  it("draws one set of lines until the half-metre earns its own", () => {
    const { image } = gridStyle({ scale: 1, tx: 0, ty: 0 });
    expect(image).toContain("var(--grid)");
    expect(image).not.toContain("var(--grid-sub)");
  });

  it("adds the half-metre under the metre, weaker, once zoomed in", () => {
    const { image } = gridStyle({ scale: 4, tx: 0, ty: 0 });
    expect(image).toContain("var(--grid-sub)");
    // The metre lines are listed first, so they paint over the sub-grid.
    expect(image.indexOf("var(--grid)")).toBeLessThan(
      image.indexOf("var(--grid-sub)"),
    );
  });

  it("keeps the metre lines drawn through the half-metre ones", () => {
    const { size } = gridStyle({ scale: 4, tx: 0, ty: 0 });
    // Four tiles: the metre pair, then the half-metre pair at half the step.
    const widths = size
      .split(",")
      .map((s) => Number(s.trim().split(" ")[0].replace("px", "")))
      .filter((n) => Number.isFinite(n) && n > 0);
    expect(widths.length).toBe(2);
    expect(widths[0] / widths[1]).toBeCloseTo(2, 6);
  });
});
