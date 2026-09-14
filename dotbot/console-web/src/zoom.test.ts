import { describe, expect, it } from "vitest";

import { areaToFraction } from "./frame";
import { frameMm } from "./grid";
import {
  CANVAS_INSET_PX,
  SITE_CAMERA,
  SITE_ZOOM,
  ZOOM_MAX_FLOOR,
  cameraForArea,
  cameraForZoom,
  clampCam,
  fitScale,
  padArea,
  viewCentre,
  viewGeom,
  zoomAbout,
  zoomFromSearch,
  zoomMax,
  zoomNames,
} from "./zoom";
import type { Camera } from "./zoom";
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
const GEOM = viewGeom(900, 600, VIEWPORT);
const MAX = zoomMax(C405, VIEWPORT, GEOM);

// Where a frame point lands on the canvas once the camera has run.
function onCanvas(p: { x: number; y: number }, cam: { scale: number; tx: number; ty: number }) {
  const { fx, fy } = areaToFraction(p, VIEWPORT);
  const px = (GEOM.w - GEOM.boxW) / 2 + fx * GEOM.boxW;
  const py = (GEOM.h - GEOM.boxH) / 2 + fy * GEOM.boxH;
  return {
    x: GEOM.w / 2 + (px - GEOM.w / 2) * cam.scale + cam.tx,
    y: GEOM.h / 2 + (py - GEOM.h / 2) * cam.scale + cam.ty,
  };
}

describe("the drawn box", () => {
  // 20 x 30 m of site, so 24 x 34 m of drawn frame: the case a square box
  // squashes by half a pixel per millimetre on one axis.
  const TALL: Area = { x: -2000, y: -2000, w: 24000, h: 34000 };

  it("carries the viewport's own aspect ratio", () => {
    const geom = viewGeom(1280, 720, TALL);
    expect(geom.boxW / geom.boxH).toBeCloseTo(TALL.w / TALL.h, 9);
  });

  it("spans one millimetre by the same pixels on both axes", () => {
    const geom = viewGeom(1280, 720, TALL);
    expect(geom.boxW / TALL.w).toBeCloseTo(geom.boxH / TALL.h, 12);
  });

  it("fits the canvas, inset, whichever axis is the tight one", () => {
    [
      viewGeom(1280, 720, TALL),
      viewGeom(720, 1280, TALL),
      viewGeom(900, 600, VIEWPORT),
    ].forEach((geom) => {
      expect(geom.boxW).toBeLessThanOrEqual(geom.w - CANVAS_INSET_PX + 1e-9);
      expect(geom.boxH).toBeLessThanOrEqual(geom.h - CANVAS_INSET_PX + 1e-9);
      // One axis is the one that fits exactly; the other is letterboxed.
      expect(
        Math.min(
          geom.w - CANVAS_INSET_PX - geom.boxW,
          geom.h - CANVAS_INSET_PX - geom.boxH,
        ),
      ).toBeCloseTo(0, 6);
    });
  });

  it("keeps a box to draw into on a canvas too small to inset", () => {
    const geom = viewGeom(40, 30, TALL);
    expect(Math.min(geom.boxW, geom.boxH)).toBeGreaterThan(0);
    expect(geom.boxW / geom.boxH).toBeCloseTo(TALL.w / TALL.h, 9);
  });
});

describe("panning", () => {
  it("keeps the site reachable rather than flinging it off-canvas", () => {
    const TALL: Area = { x: -2000, y: -2000, w: 24000, h: 34000 };
    const geom = viewGeom(1280, 720, TALL);
    const far = clampCam({ scale: 3, tx: 99999, ty: -99999 }, geom);
    // The clamp never pushes the box's own centre outside the canvas.
    expect(Math.abs(far.tx)).toBeLessThanOrEqual(
      (geom.boxW * 3 - geom.w) / 2 + Math.max(0, (geom.w - geom.boxW) / 2) + 1e-9,
    );
    expect(Math.abs(far.ty)).toBeLessThanOrEqual(
      (geom.boxH * 3 - geom.h) / 2 + Math.max(0, (geom.h - geom.boxH) / 2) + 1e-9,
    );
  });
});

describe("zooming the map", () => {
  // The frame coordinate sitting under one canvas point.
  const under = (px: { x: number; y: number }, cam: Camera) => ({
    x: frameMm("x", px.x, VIEWPORT, GEOM, cam),
    y: frameMm("y", px.y, VIEWPORT, GEOM, cam),
  });
  // A millimetre of frame is well under a pixel here, so "within a pixel" is
  // the tolerance the assertion is actually about.
  const mmPerPx = VIEWPORT.w / GEOM.boxW;
  const centre = viewCentre(GEOM);

  it("holds the middle of the canvas still, in and out", () => {
    // Panned off the frame's own centre: the case leaving the pan alone gets
    // wrong, and gets more wrong the further it is panned.
    const start: Camera = { scale: 1, tx: 100, ty: 20 };
    const was = under(centre, start);

    let cam = start;
    for (let i = 0; i < 3; i += 1) {
      cam = zoomAbout(cam, cam.scale * 1.25, centre, GEOM);
      const now = under(centre, cam);
      expect(now.x).toBeCloseTo(was.x, 6);
      expect(now.y).toBeCloseTo(was.y, 6);
    }
    expect(cam.scale).toBeCloseTo(1.25 ** 3, 9);

    for (let i = 0; i < 3; i += 1) {
      cam = zoomAbout(cam, cam.scale / 1.25, centre, GEOM);
      const now = under(centre, cam);
      expect(Math.abs(now.x - was.x)).toBeLessThan(mmPerPx);
      expect(Math.abs(now.y - was.y)).toBeLessThan(mmPerPx);
    }
    // Three steps out from three steps in is where it started.
    expect(cam.scale).toBeCloseTo(start.scale, 9);
    expect(cam.tx).toBeCloseTo(start.tx, 6);
    expect(cam.ty).toBeCloseTo(start.ty, 6);
  });

  it("holds any canvas point still, for a cursor-anchored zoom", () => {
    const cam: Camera = { scale: 1.4, tx: -40, ty: 12 };
    const cursor = { x: GEOM.w * 0.28, y: GEOM.h * 0.71 };
    const was = under(cursor, cam);
    const zoomed = zoomAbout(cam, cam.scale * 1.5, cursor, GEOM);
    const now = under(cursor, zoomed);
    expect(now.x).toBeCloseTo(was.x, 6);
    expect(now.y).toBeCloseTo(was.y, 6);
  });

  it("leaves the camera alone rather than dividing by a scale of zero", () => {
    const cam: Camera = { scale: 0, tx: 10, ty: 10 };
    expect(zoomAbout(cam, 2, centre, GEOM)).toBe(cam);
  });

  it("still keeps the site reachable when a zoom out would strand it", () => {
    const stranded = zoomAbout(
      { scale: 6, tx: 900, ty: -600 },
      1,
      centre,
      GEOM,
    );
    expect(stranded).toEqual(clampCam(stranded, GEOM));
  });
});

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
    const cam = cameraForArea(padded, VIEWPORT, GEOM, MAX);
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

  it("never zooms past the ceiling it is given", () => {
    const speck: Area = { x: 1000, y: 1000, w: 1, h: 1, name: "speck" };
    expect(cameraForArea(speck, VIEWPORT, GEOM, MAX).scale).toBe(MAX);
  });

  it("leaves the camera alone for a name the site does not define", () => {
    expect(cameraForZoom("balcony", C405, VIEWPORT, GEOM)).toBeNull();
  });
});

describe("the zoom ceiling", () => {
  it("is whatever the site's smallest area needs, pad included", () => {
    const small: Area = { x: 100, y: 100, w: 800, h: 800, name: "pen" };
    const site: Site = { ...C405, areas: [ARENA, ANNEX, small] };
    expect(zoomMax(site, VIEWPORT, GEOM)).toBeCloseTo(
      fitScale(padArea(small), VIEWPORT, GEOM),
      9,
    );
  });

  it("is high enough to frame every area the site defines", () => {
    const small: Area = { x: 100, y: 100, w: 800, h: 800, name: "pen" };
    const site: Site = { ...C405, areas: [ARENA, ANNEX, small] };
    const max = zoomMax(site, VIEWPORT, GEOM);
    site.areas.forEach((a) => {
      expect(fitScale(padArea(a), VIEWPORT, GEOM)).toBeLessThanOrEqual(max + 1e-9);
    });
  });

  it("clears a 1 m area inside a floor-sized site", () => {
    // 3330 x 4000 mm of site, so 7330 x 8000 mm of drawn viewport: a 1 m
    // square in it needs well over the fallback to fill the canvas.
    const floor: Site = {
      ...C405,
      extent_mm: [3330, 4000],
      areas: [{ x: 1000, y: 1000, w: 1000, h: 1000, name: "pen" }],
    };
    const viewport: Area = { x: -2000, y: -2000, w: 7330, h: 8000 };
    expect(zoomMax(floor, viewport, GEOM)).toBeGreaterThan(6);
    expect(zoomMax(floor, viewport, GEOM)).toBeCloseTo(
      fitScale(padArea(floor.areas[0]), viewport, GEOM),
      9,
    );
  });

  it("falls back to the floor when the site defines no area", () => {
    expect(zoomMax({ ...C405, areas: [] }, VIEWPORT, GEOM)).toBe(ZOOM_MAX_FLOOR);
    expect(zoomMax(null, VIEWPORT, GEOM)).toBe(ZOOM_MAX_FLOOR);
  });

  it("ignores an area with no extent to fit", () => {
    const site: Site = {
      ...C405,
      areas: [{ x: 0, y: 0, w: 0, h: 0, name: "point" }],
    };
    expect(zoomMax(site, VIEWPORT, GEOM)).toBe(ZOOM_MAX_FLOOR);
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
