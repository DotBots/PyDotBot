import React, { useState } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { frameMm } from "./grid";
import { MapView } from "./MapView";
import type { Area, Site } from "./types";
import {
  Camera,
  SITE_CAMERA,
  cameraForZoom,
  viewGeom,
  zoomFromSearch,
} from "./zoom";

const ARENA: Area = { x: 0, y: 0, w: 2000, h: 2000, name: "arena" };
const ANNEX: Area = { x: 0, y: 2000, w: 2000, h: 2000, name: "annex" };
const C405: Site = {
  name: "c405-arena",
  anchor: "the arena's top-left corner",
  extent_mm: [2000, 4000],
  areas: [ARENA, ANNEX],
};
const VIEWPORT: Area = { x: -2000, y: -2000, w: 6000, h: 8000 };
const GEOM = viewGeom(900, 600, VIEWPORT);

// The map with a camera over it, zoomed the way App zooms it.
const Harness: React.FC<{ onCam?: (c: Camera) => void; from?: Camera }> = ({
  onCam,
  from = SITE_CAMERA,
}) => {
  const [cam, setCam] = useState<Camera>(from);
  return (
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
        trails: false,
        crashedOnly: false,
      }}
      plannedMissions={[]}
      cam={cam}
      setCam={setCam}
      onGeom={() => {}}
      onSelect={() => {}}
      onAddWaypoint={() => {}}
      site={C405}
      onZoom={(name) => {
        const next = cameraForZoom(name, C405, VIEWPORT, GEOM);
        if (next) {
          setCam(next);
          onCam?.(next);
        }
      }}
    />
  );
};

describe("the fit button", () => {
  it("goes back to the whole site in one press", () => {
    const seen: Camera[] = [];
    render(<Harness onCam={(c) => seen.push(c)} />);

    fireEvent.click(screen.getByTitle("Zoom to the whole site"));

    expect(seen).toEqual([SITE_CAMERA]);
  });

  it("offers no menu: an area is zoomed from its Layers row", () => {
    render(<Harness />);
    fireEvent.click(screen.getByTitle("Zoom to the whole site"));
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });
});

describe("the zoom buttons", () => {
  // jsdom measures every element as zero, so the map would zoom about the
  // corner of a canvas with no size.
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

  const camera = (): Camera => {
    const t = screen.getByTestId("camera-layer").style.transform;
    const [, tx, ty, scale] =
      /translate\(([-\d.]+)px, ([-\d.]+)px\) scale\(([-\d.]+)\)/.exec(t) ?? [];
    return { scale: Number(scale), tx: Number(tx), ty: Number(ty) };
  };
  const centreOfFrame = (cam: Camera) => ({
    x: frameMm("x", GEOM.w / 2, VIEWPORT, GEOM, cam),
    y: frameMm("y", GEOM.h / 2, VIEWPORT, GEOM, cam),
  });
  const press = (title: string, times: number) => {
    for (let i = 0; i < times; i += 1) fireEvent.click(screen.getByTitle(title));
  };

  it("keeps what is in the middle of the map in the middle", () => {
    // Panned away from the frame's own centre: the case a zoom that only
    // rewrites the scale throws somewhere else.
    render(<Harness from={{ scale: 1, tx: 100, ty: 20 }} />);
    const was = centreOfFrame(camera());
    // One frame millimetre is well under a pixel here, so a millimetre of
    // tolerance is stricter than the pixel the assertion is about.
    const mmPerPx = VIEWPORT.w / GEOM.boxW;

    press("Zoom in", 3);
    expect(camera().scale).toBeGreaterThan(1);
    let now = centreOfFrame(camera());
    expect(Math.abs(now.x - was.x)).toBeLessThan(mmPerPx);
    expect(Math.abs(now.y - was.y)).toBeLessThan(mmPerPx);

    press("Zoom out", 3);
    now = centreOfFrame(camera());
    expect(Math.abs(now.x - was.x)).toBeLessThan(mmPerPx);
    expect(Math.abs(now.y - was.y)).toBeLessThan(mmPerPx);
  });

  it("comes back to the camera it left, in and out again", () => {
    render(<Harness from={{ scale: 1, tx: 100, ty: 20 }} />);
    press("Zoom in", 3);
    press("Zoom out", 3);
    const back = camera();
    expect(back.scale).toBeCloseTo(1, 6);
    expect(back.tx).toBeCloseTo(100, 4);
    expect(back.ty).toBeCloseTo(20, 4);
    cleanup();
  });
});

describe("an area on the map", () => {
  it("carries its name for the pointer and the screen reader, not as text", () => {
    render(<Harness />);
    const outline = screen.getByRole("img", { name: "arena" });
    expect(outline.querySelector("title")?.textContent).toBe("arena");
    // The name is the outline's tooltip and nothing else on the map.
    const printed = screen.queryAllByText("arena").map((el) => el.tagName);
    expect(printed).toEqual(["title"]);
  });
});

describe("the ?zoom= preset", () => {
  it("lands on the camera that area's name asks for", () => {
    const asked = zoomFromSearch("?zoom=annex", C405);

    expect(cameraForZoom(asked!, C405, VIEWPORT, GEOM)).toEqual(
      cameraForZoom("annex", C405, VIEWPORT, GEOM),
    );
  });
});
