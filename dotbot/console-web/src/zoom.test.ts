import { describe, expect, it } from "vitest";

import { areaToFraction } from "./frame";
import {
  SITE_CAMERA,
  SITE_ZOOM,
  ZOOM_MAX,
  cameraForArea,
  cameraForZoom,
  padArea,
  zoomFromSearch,
  zoomNames,
} from "./zoom";
import type { Area, Site } from "./types";

const ARENA: Area = { x: 0, y: 0, w: 2000, h: 2000, name: "arena" };
const ANNEX: Area = { x: 0, y: 2000, w: 2000, h: 2000, name: "annex" };
const C405: Site = {
  name: "c405-arena",
  anchor: "the arena's top-left corner",
  extent_mm: [2000, 4000],
  areas: [ARENA, ANNEX],
};
// The site extent plus the 2 m margin, which is what the map draws.
const VIEWPORT: Area = { x: -2000, y: -2000, w: 6000, h: 8000 };
const GEOM = { w: 900, h: 600, side: 552 };

// Where a frame point lands on the canvas once the camera has run.
function onCanvas(p: { x: number; y: number }, cam: { scale: number; tx: number; ty: number }) {
  const { fx, fy } = areaToFraction(p, VIEWPORT);
  const px = (GEOM.w - GEOM.side) / 2 + fx * GEOM.side;
  const py = (GEOM.h - GEOM.side) / 2 + fy * GEOM.side;
  return {
    x: GEOM.w / 2 + (px - GEOM.w / 2) * cam.scale + cam.tx,
    y: GEOM.h / 2 + (py - GEOM.h / 2) * cam.scale + cam.ty,
  };
}

describe("the named zooms", () => {
  it("lists the site first, then one per area", () => {
    expect(zoomNames(C405)).toEqual([SITE_ZOOM, "arena", "annex"]);
  });

  it("offers the site alone before the controller answers", () => {
    expect(zoomNames(null)).toEqual([SITE_ZOOM]);
  });
});

describe("zooming to the site", () => {
  it("is the map's own default view", () => {
    expect(cameraForZoom(SITE_ZOOM, C405, VIEWPORT, GEOM)).toEqual(SITE_CAMERA);
  });
});

describe("zooming to an area", () => {
  it("puts the area's centre at the centre of the canvas", () => {
    const cam = cameraForZoom("annex", C405, VIEWPORT, GEOM)!;
    const centre = onCanvas({ x: 1000, y: 3000 }, cam);
    expect(centre.x).toBeCloseTo(GEOM.w / 2, 6);
    expect(centre.y).toBeCloseTo(GEOM.h / 2, 6);
  });

  it("fills the canvas with the area and its pad, and no more", () => {
    const padded = padArea(ARENA);
    const cam = cameraForArea(padded, VIEWPORT, GEOM);
    const tl = onCanvas({ x: padded.x, y: padded.y }, cam);
    const br = onCanvas({ x: padded.x + padded.w, y: padded.y + padded.h }, cam);
    // The short axis is the one that fits exactly; the long one has slack.
    expect(Math.min(br.x - tl.x, br.y - tl.y)).toBeCloseTo(
      Math.min(GEOM.w, GEOM.h),
      6,
    );
    expect(br.x - tl.x).toBeLessThanOrEqual(GEOM.w + 1e-6);
    expect(br.y - tl.y).toBeLessThanOrEqual(GEOM.h + 1e-6);
  });

  it("leaves room around the area rather than cropping its edges", () => {
    const padded = padArea(ARENA);
    expect(padded).toEqual({ x: -300, y: -300, w: 2600, h: 2600, name: "arena" });
  });

  it("never zooms past the manual ceiling", () => {
    const speck: Area = { x: 1000, y: 1000, w: 1, h: 1, name: "speck" };
    expect(cameraForArea(speck, VIEWPORT, GEOM).scale).toBe(ZOOM_MAX);
  });

  it("leaves the camera alone for a name the site does not define", () => {
    expect(cameraForZoom("balcony", C405, VIEWPORT, GEOM)).toBeNull();
  });
});

describe("the ?zoom= preset", () => {
  it("takes the site", () => {
    expect(zoomFromSearch("?zoom=site", C405)).toBe(SITE_ZOOM);
  });

  it("takes an area the site defines", () => {
    expect(zoomFromSearch("?theme=dark&zoom=annex", C405)).toBe("annex");
  });

  it("ignores a name the site does not define", () => {
    expect(zoomFromSearch("?zoom=balcony", C405)).toBeNull();
  });

  it("is absent when nothing asked", () => {
    expect(zoomFromSearch("?view=map", C405)).toBeNull();
  });
});
