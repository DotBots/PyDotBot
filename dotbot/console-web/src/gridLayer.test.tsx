import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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

const EXTENT: Area = { x: 0, y: 0, w: 2000, h: 4000, name: C405.name };

const Harness: React.FC<{ cam: Camera; siteExtent?: Area | null }> = ({
  cam,
  siteExtent = EXTENT,
}) => (
  <MapView
    bots={[]}
    viewport={VIEWPORT}
    siteAreas={C405.areas}
    hiddenAreas={new Set()}
    siteExtent={siteExtent}
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

describe("the ruler on the canvas", () => {
  // jsdom measures every element as zero, so the map would have no canvas to
  // put a ruler on and every label would be filtered off the edge.
  let rectSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    rectSpy = vi
      .spyOn(HTMLElement.prototype, "getBoundingClientRect")
      .mockReturnValue({
        width: 900,
        height: 600,
        top: 0,
        left: 0,
        right: 900,
        bottom: 600,
        x: 0,
        y: 0,
        toJSON: () => ({}),
      } as DOMRect);
  });

  afterEach(() => rectSpy.mockRestore());

  const labels = (cam: Camera, siteExtent?: Area | null) => {
    render(<Harness cam={cam} siteExtent={siteExtent} />);
    return Array.from(
      screen.getByLabelText("Metre ruler").querySelectorAll("span"),
    ).map((s) => s.textContent ?? "");
  };

  it("prints no negative metre, at any zoom", () => {
    [1, 2, 4].forEach((scale) => {
      const printed = labels({ scale, tx: 0, ty: 0 });
      expect(printed.length).toBeGreaterThan(0);
      printed.forEach((text) => expect(text).not.toContain("-"));
      cleanup();
    });
  });

  it("names the site's own metres and stops at its far edge", () => {
    // 2 x 4 m of site: the margin around it carries no numbers.
    const printed = labels({ scale: 1, tx: 0, ty: 0 });
    expect(printed).toContain("0 m");
    expect(printed).toContain("2 m");
    expect(printed).toContain("4 m");
    expect(printed).not.toContain("5 m");
  });

  it("still counts from zero when the site has no measured extent", () => {
    const printed = labels({ scale: 1, tx: 0, ty: 0 }, null);
    expect(printed.length).toBeGreaterThan(0);
    printed.forEach((text) => expect(text).not.toContain("-"));
  });
});
