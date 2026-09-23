import { describe, expect, it } from "vitest";

import { GLYPH_DETAIL_PX, botFootprintPx, glyphLevel } from "./BotGlyph";
import { areaToFraction, siteViewport } from "./frame";
import { frameMm, pxPerMm } from "./grid";
import {
  CANVAS_INSET_PX,
  SITE_CAMERA,
  SITE_ZOOM,
  ZOOM_MAX_FLOOR,
  ZOOM_MAX_PX_PER_MM,
  ZOOM_MIN,
  ZOOM_STEP,
  cameraForArea,
  cameraForZoom,
  clampCam,
  clampScale,
  fitScale,
  padArea,
  scaleForFraction,
  steppedScale,
  viewCentre,
  viewGeom,
  zoomAbout,
  zoomFraction,
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
// The span a v3 body reports, for the questions the zoom ladder asks about how
// big a robot lands on screen. The console never computes this; the controller
// ships it inside each body pose.
const V3_SPAN_MM = 95;
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

describe("the zoom range", () => {
  it("starts at the whole site, which is the map's own camera", () => {
    expect(ZOOM_MIN).toBe(1);
    expect(SITE_CAMERA.scale).toBe(ZOOM_MIN);
    expect(zoomFraction(SITE_CAMERA.scale, 11.4)).toBe(0);
  });

  it("holds a scale between the site and the ceiling", () => {
    expect(clampScale(4, 11.4)).toBe(4);
    expect(clampScale(0.2, 11.4)).toBe(ZOOM_MIN);
    expect(clampScale(999, 11.4)).toBe(11.4);
    // A ceiling below the site view, or no ceiling at all, still leaves a
    // scale the map can draw.
    expect(clampScale(4, 0.5)).toBe(ZOOM_MIN);
    expect(clampScale(4, Number.NaN)).toBe(ZOOM_MIN);
    expect(clampScale(Number.NaN, 11.4)).toBe(ZOOM_MIN);
  });

  it("steps a press by the same ratio wherever it starts", () => {
    expect(steppedScale(1, 1, 11.4)).toBeCloseTo(ZOOM_STEP, 9);
    expect(steppedScale(4, 1, 11.4)).toBeCloseTo(4 * ZOOM_STEP, 9);
    expect(steppedScale(4, -1, 11.4)).toBeCloseTo(4 / ZOOM_STEP, 9);
    expect(steppedScale(1, 3, 11.4)).toBeCloseTo(ZOOM_STEP ** 3, 9);
  });

  it("stops a press at both ends rather than running past them", () => {
    expect(steppedScale(ZOOM_MIN, -1, 11.4)).toBe(ZOOM_MIN);
    expect(steppedScale(11.4, 1, 11.4)).toBe(11.4);
  });

  it("comes back to the scale it left, in and out again", () => {
    let scale = 2;
    for (let i = 0; i < 3; i += 1) scale = steppedScale(scale, 1, 40);
    for (let i = 0; i < 3; i += 1) scale = steppedScale(scale, -1, 40);
    expect(scale).toBeCloseTo(2, 9);
  });

  it("puts the ends of the range at the ends of the slider", () => {
    expect(zoomFraction(ZOOM_MIN, 11.4)).toBe(0);
    expect(zoomFraction(11.4, 11.4)).toBeCloseTo(1, 12);
    // Past either end reads as that end, never off the track.
    expect(zoomFraction(0.1, 11.4)).toBe(0);
    expect(zoomFraction(999, 11.4)).toBeCloseTo(1, 12);
  });

  it("spends the same travel on the same magnification", () => {
    // Half the track is the square root of the whole range, not half of it:
    // a press is worth the same handful of pixels wherever the handle is.
    const max = 16;
    expect(scaleForFraction(0.5, max)).toBeCloseTo(Math.sqrt(max), 9);
    const step = (from: number) =>
      zoomFraction(from * ZOOM_STEP, max) - zoomFraction(from, max);
    expect(step(1)).toBeCloseTo(step(4), 12);
  });

  it("reads a position back as the scale it stands for", () => {
    [0, 0.17, 0.5, 0.83, 1].forEach((f) => {
      expect(zoomFraction(scaleForFraction(f, 11.4), 11.4)).toBeCloseTo(f, 12);
    });
    // A position off the track, or none at all, still names a scale.
    expect(scaleForFraction(-1, 11.4)).toBe(ZOOM_MIN);
    expect(scaleForFraction(2, 11.4)).toBeCloseTo(11.4, 9);
    expect(scaleForFraction(Number.NaN, 11.4)).toBe(ZOOM_MIN);
  });

  it("leaves a degenerate range at the whole site", () => {
    expect(zoomFraction(4, 1)).toBe(0);
    expect(scaleForFraction(0.5, 1)).toBe(ZOOM_MIN);
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

  it("fits the area exactly rather than landing near it", () => {
    const cam = cameraForArea(padArea(ARENA), VIEWPORT, GEOM, MAX);
    expect(cam.scale).toBeCloseTo(
      fitScale(padArea(ARENA), VIEWPORT, GEOM),
      9,
    );
  });

  it("fills the canvas with the area, edges and all", () => {
    const cam = cameraForArea(padArea(ARENA), VIEWPORT, GEOM, MAX);
    const tl = onCanvas({ x: ARENA.x, y: ARENA.y }, cam);
    const br = onCanvas({ x: ARENA.x + ARENA.w, y: ARENA.y + ARENA.h }, cam);
    expect(tl.x).toBeGreaterThanOrEqual(0);
    expect(tl.y).toBeGreaterThanOrEqual(0);
    expect(br.x).toBeLessThanOrEqual(GEOM.w);
    expect(br.y).toBeLessThanOrEqual(GEOM.h);
    // And it is the canvas it fills, not a corner of it.
    expect(Math.min(br.x - tl.x, br.y - tl.y)).toBeGreaterThan(
      Math.min(GEOM.w, GEOM.h) / 2,
    );
  });

  it("leaves room around the area rather than cropping its edges", () => {
    const padded = padArea(ARENA);
    expect(padded).toEqual({ x: -300, y: -300, w: 2600, h: 2600, name: "arena" });
  });

  it("never zooms past the ceiling", () => {
    const speck: Area = { x: 1000, y: 1000, w: 1, h: 1, name: "speck" };
    expect(cameraForArea(speck, VIEWPORT, GEOM, MAX).scale).toBe(MAX);
  });

  it("leaves the camera alone for a name the site does not define", () => {
    expect(cameraForZoom("balcony", C405, VIEWPORT, GEOM)).toBeNull();
  });
});

describe("the zoom ceiling", () => {
  it("clears whatever the site's smallest area needs, pad included", () => {
    const small: Area = { x: 100, y: 100, w: 800, h: 800, name: "pen" };
    const site: Site = { ...C405, areas: [ARENA, ANNEX, small] };
    expect(zoomMax(site, VIEWPORT, GEOM)).toBeGreaterThanOrEqual(
      fitScale(padArea(small), VIEWPORT, GEOM),
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
    expect(zoomMax(floor, viewport, GEOM)).toBeGreaterThanOrEqual(
      fitScale(padArea(floor.areas[0]), viewport, GEOM),
    );
  });

  it("always reaches a pixel to the millimetre, whatever the areas are", () => {
    // A site whose areas are all floor-sized: nothing in it asks for zoom,
    // so without this the map stops before a robot is more than a mark.
    const plain: Site = { ...C405, areas: [ARENA, ANNEX] };
    const max = zoomMax(plain, VIEWPORT, GEOM);
    expect(pxPerMm("x", VIEWPORT, GEOM, { scale: max, tx: 0, ty: 0 })).toBeGreaterThanOrEqual(
      ZOOM_MAX_PX_PER_MM - 1e-9,
    );
    // Which is a 95 mm robot at very nearly its own size in pixels.
    expect(
      V3_SPAN_MM * pxPerMm("x", VIEWPORT, GEOM, { scale: max, tx: 0, ty: 0 }),
    ).toBeGreaterThanOrEqual(V3_SPAN_MM - 1e-6);
  });

  it("still clears an area that asks for more than that", () => {
    const speck: Area = { x: 100, y: 100, w: 60, h: 60, name: "pen" };
    const site: Site = { ...C405, areas: [ARENA, speck] };
    expect(zoomMax(site, VIEWPORT, GEOM)).toBeCloseTo(
      fitScale(padArea(speck), VIEWPORT, GEOM),
      9,
    );
  });

  it("falls back no lower than the floor when the site defines no area", () => {
    [zoomMax({ ...C405, areas: [] }, VIEWPORT, GEOM), zoomMax(null, VIEWPORT, GEOM)].forEach(
      (max) => expect(max).toBeGreaterThanOrEqual(ZOOM_MAX_FLOOR),
    );
  });

  it("ignores an area with no extent to fit", () => {
    const site: Site = {
      ...C405,
      areas: [{ x: 0, y: 0, w: 0, h: 0, name: "point" }],
    };
    expect(zoomMax(site, VIEWPORT, GEOM)).toBe(
      zoomMax({ ...C405, areas: [] }, VIEWPORT, GEOM),
    );
  });
});

describe("how far in the glyph ladder reaches", () => {
  // The two sites that differ: one with a small area to zoom to, one with
  // nothing but room-sized ones. The ceiling has to serve both.
  const plain: Site = { ...C405, areas: [ARENA, ANNEX] };
  const withPen: Site = {
    ...C405,
    areas: [ARENA, ANNEX, { x: 100, y: 100, w: 800, h: 800, name: "pen" }],
  };
  // A bot's size on screen, sampled right across a site's zoom range.
  const footprints = (site: Site) => {
    const max = zoomMax(site, VIEWPORT, GEOM);
    return Array.from({ length: 41 }, (_, i) =>
      botFootprintPx(
        pxPerMm("x", VIEWPORT, GEOM, {
          scale: scaleForFraction(i / 40, max),
          tx: 0,
          ty: 0,
        }),
        V3_SPAN_MM,
      ),
    );
  };

  it("turns the board on at a size on screen, not at a zoom level", () => {
    [plain, withPen].forEach((site) => {
      footprints(site).forEach((px) => {
        expect(glyphLevel(px, 1)).toBe(
          px >= GLYPH_DETAIL_PX ? "detail" : "dot",
        );
      });
    });
  });

  it("reaches the board on any site, and keeps it to the top", () => {
    [plain, withPen].forEach((site) => {
      const levels = footprints(site).map((px) => glyphLevel(px, 1));
      const detail = levels.filter((l) => l === "detail").length;
      expect(detail).toBeGreaterThan(0);
      // Once it is the board it stays the board, all the way to the ceiling.
      expect(levels.slice(-detail).every((l) => l === "detail")).toBe(true);
    });
  });

  it("shows the same robot at the same size on either site", () => {
    expect(footprints(plain)).toEqual(footprints(withPen));
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

describe("the whole-site view", () => {
  // The map canvas a 1600 x 950 window leaves once both panes are open.
  const arena: Site = { ...C405, extent_mm: [2000, 2000], areas: [ARENA] };
  const viewport = siteViewport(arena, ARENA);
  const geom = viewGeom(936, 740, viewport);
  const sitePerMm = pxPerMm("x", viewport, geom, SITE_CAMERA);

  it("is mostly site: the arena fills most of the drawn box", () => {
    expect((ARENA.w * sitePerMm) / geom.boxW).toBeGreaterThan(0.75);
  });

  it("shows a 2 x 2 m arena's robots as full outlines on a normal screen", () => {
    expect(glyphLevel(botFootprintPx(sitePerMm, V3_SPAN_MM), 12)).toBe("detail");
  });
});
