import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { siteViewport } from "./frame";
import { frameMm } from "./grid";
import { Minimap } from "./Minimap";
import type { Area, Site } from "./types";
import { Camera, viewGeom } from "./zoom";

const ARENA: Area = { x: 0, y: 0, w: 2000, h: 2000, name: "arena" };
const SITE: Site = {
  name: "c405-arena",
  anchor: "the arena's top-left corner",
  extent_mm: [2000, 2000],
  areas: [ARENA],
};
const VIEWPORT = siteViewport(SITE, ARENA);
const GEOM = viewGeom(900, 600, VIEWPORT);
const MINIMAP_PX = 190;

let rectSpy: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  rectSpy = vi
    .spyOn(HTMLElement.prototype, "getBoundingClientRect")
    .mockReturnValue({
      width: MINIMAP_PX,
      height: MINIMAP_PX,
      top: 0,
      left: 0,
      right: MINIMAP_PX,
      bottom: MINIMAP_PX,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    } as DOMRect);
});

afterEach(() => rectSpy.mockRestore());

describe("the minimap", () => {
  it("centres the map on the point of the site that was pressed", () => {
    let cam: Camera = { scale: 4, tx: 0, ty: 0 };
    const setCam = (next: React.SetStateAction<Camera>) => {
      cam = typeof next === "function" ? next(cam) : next;
    };
    render(
      <Minimap
        bots={[]}
        viewport={VIEWPORT}
        site={SITE}
        hiddenAreas={new Set()}
        selection={new Set()}
        cam={cam}
        setCam={setCam}
        geom={GEOM}
      />,
    );

    // A quarter of the way into the site on both axes: frame (500, 500).
    fireEvent.pointerDown(screen.getByTitle("Drag to move the map view"), {
      button: 0,
      clientX: MINIMAP_PX / 4,
      clientY: MINIMAP_PX / 4,
      pointerId: 1,
    });

    expect(frameMm("x", GEOM.w / 2, VIEWPORT, GEOM, cam)).toBeCloseTo(500, 6);
    expect(frameMm("y", GEOM.h / 2, VIEWPORT, GEOM, cam)).toBeCloseTo(500, 6);
  });
});
