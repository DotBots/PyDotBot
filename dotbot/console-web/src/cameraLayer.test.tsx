import React, { useState } from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  CameraOffset,
  CameraOpacity,
  DEFAULT_CAMERA_OPACITY,
  NO_OFFSET,
  fadeMm,
  loadCameraOffset,
  loadCameraOpacity,
  offsetFor,
  offsetTransform,
  opacityFor,
  polygonPoints,
  reachMm,
  saveCameraOffset,
  saveCameraOpacity,
  spanMask,
  spanSizeMm,
  withOffset,
  withOpacity,
} from "./cameraLayer";
import { areaToFraction } from "./frame";
import { MapView } from "./MapView";
import { RightPane, RightTab } from "./RightPane";
import type { Area, RegisteredCamera, Site } from "./types";
import type { Calibration } from "./useCalibration";

const ARENA: Area = { x: 0, y: 0, w: 2000, h: 2000, name: "arena" };
const DEV_CORNER: Area = { x: 1000, y: 0, w: 1000, h: 1000, name: "dev-corner" };
const C405: Site = {
  name: "c405-arena",
  anchor: "the arena's top-left corner",
  extent_mm: [2000, 4000],
  areas: [ARENA, DEV_CORNER],
};
const VIEWPORT: Area = { x: -2000, y: -2000, w: 6000, h: 8000 };

// The four sheets stood in dev-corner's corners, so the span is the area
// inset by the sheet geometry: Figure 1 of the plan, and what Phase 2 writes.
const SPAN: number[][] = [
  [1030, 73.5],
  [1970, 73.5],
  [1970, 926.5],
  [1030, 926.5],
];

// The bench's GoPro, looking down on dev-corner from well outside it: its
// frame's rectangle through the homography swallows the area whole.
const COVERAGE: number[][] = [
  [355.3, 2473.0],
  [446.5, -1554.1],
  [2443.2, -538.4],
  [2276.0, 1851.2],
];

// A camera aimed short of the area: it sees the left two thirds and stops.
const PART_COVERAGE: number[][] = [
  [900, -200],
  [1700, -200],
  [1700, 1200],
  [900, 1200],
];

const CAMERA: RegisteredCamera = {
  area: "dev-corner",
  source: "/tmp/synthetic.png",
  mm_per_px: 2,
  width: 500,
  height: 500,
  span_mm: SPAN,
  coverage_mm: COVERAGE,
  residual_mm: 0.1495,
  id: "7b21c0d9f3a1",
  lens: "linear",
};

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

const LAYERS = {
  batteryBars: true,
  waypoints: true,
  hotSpots: false,
  dotBots: true,
  trails: false,
  crashedOnly: false,
};

// The map and the Layers tab over one opacity map and one offset map, exactly
// as App wires them.
const Harness: React.FC<{ cameras?: RegisteredCamera[] }> = ({
  cameras = [CAMERA],
}) => {
  const [cameraOpacity, setCameraOpacity] = useState<CameraOpacity>(
    loadCameraOpacity,
  );
  const [cameraOffset, setCameraOffset] =
    useState<CameraOffset>(loadCameraOffset);
  const [tab, setTab] = useState<RightTab>("layers");
  return (
    <>
      <div data-testid="map">
        <MapView
          bots={[]}
          viewport={VIEWPORT}
          siteAreas={C405.areas}
          hiddenAreas={new Set()}
          cameras={cameras}
          cameraOpacity={cameraOpacity}
          cameraOffset={cameraOffset}
          siteExtent={{ x: 0, y: 0, w: 2000, h: 4000, name: C405.name }}
          selection={new Set()}
          layers={LAYERS}
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
          hiddenAreas={new Set()}
          onAreaToggle={() => {}}
          layers={LAYERS}
          layerRows={[]}
          onLayerToggle={() => {}}
          cameras={cameras}
          cameraOpacity={cameraOpacity}
          onCameraOpacity={(area, value) =>
            setCameraOpacity((prev) => {
              const next = withOpacity(prev, area, value);
              saveCameraOpacity(next);
              return next;
            })
          }
          cameraOffset={cameraOffset}
          onCameraOffset={(area, value) =>
            setCameraOffset((prev) => {
              const next = withOffset(prev, area, value);
              saveCameraOffset(next);
              return next;
            })
          }
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

describe("Layers > Camera", () => {
  it("renders one row per registered camera, with its residual", () => {
    render(<Harness />);
    const pane = screen.getByTestId("pane");
    expect(within(pane).getByText("Camera")).toBeInTheDocument();
    expect(
      within(pane).getAllByLabelText(/^Camera opacity on /),
    ).toHaveLength(1);
    const row = within(pane).getByTestId("camera-row-dev-corner");
    expect(row.textContent).toContain("dev-corner");
    expect(row.textContent).toContain("0.1 mm");
  });

  it("renders no heading at all when no camera is registered", () => {
    render(<Harness cameras={[]} />);
    const pane = screen.getByTestId("pane");
    expect(within(pane).queryByText("Camera")).not.toBeInTheDocument();
    expect(
      within(pane).queryByLabelText(/^Camera opacity on /),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("camera-layer-dev-corner"),
    ).not.toBeInTheDocument();
  });

  it("drives the image's opacity from the slider, and remembers it here", () => {
    render(<Harness />);
    const layer = screen.getByTestId("camera-layer-dev-corner");
    expect(layer.style.opacity).toBe(String(DEFAULT_CAMERA_OPACITY));

    fireEvent.change(screen.getByLabelText("Camera opacity on dev-corner"), {
      target: { value: "20" },
    });

    expect(layer.style.opacity).toBe("0.2");
    expect(screen.getByText("20%")).toBeInTheDocument();
    expect(window.localStorage.getItem("dotbot.console.cameraOpacity")).toBe(
      '{"dev-corner":0.2}',
    );
  });
});

describe("the camera as a map layer", () => {
  it("draws the stream on the area's own box, the one pctArea gives", () => {
    render(<Harness />);
    const layer = screen.getByTestId("camera-layer-dev-corner");
    const tl = areaToFraction({ x: DEV_CORNER.x, y: DEV_CORNER.y }, VIEWPORT);
    const br = areaToFraction(
      { x: DEV_CORNER.x + DEV_CORNER.w, y: DEV_CORNER.y + DEV_CORNER.h },
      VIEWPORT,
    );

    expect(parseFloat(layer.style.left)).toBeCloseTo(tl.fx * 100, 9);
    expect(parseFloat(layer.style.top)).toBeCloseTo(tl.fy * 100, 9);
    expect(parseFloat(layer.style.width)).toBeCloseTo((br.fx - tl.fx) * 100, 9);
    expect(parseFloat(layer.style.height)).toBeCloseTo((br.fy - tl.fy) * 100, 9);

    const image = screen.getByTestId("camera-image-dev-corner");
    expect(image).toHaveAttribute(
      "src",
      "/controller/cameras/dev-corner/stream",
    );
    expect(image.style.width).toBe("100%");
    expect(image.style.height).toBe("100%");
  });

  it("draws no square through the markers, which the photograph shows", () => {
    render(<Harness />);
    expect(
      screen.queryByTestId("camera-span-dev-corner"),
    ).not.toBeInTheDocument();
    // The mapping the mask is drawn through is still this one: the box is
    // the area, so the span's frame millimetres land as the area's own, and
    // 1030 mm of frame is 30 mm into a dev-corner starting at 1000.
    expect(polygonPoints(SPAN, DEV_CORNER)).toBe(
      "30,73.5 970,73.5 970,926.5 30,926.5",
    );
  });

  it("draws the image whole out to the area's edge, with no falloff", () => {
    render(<Harness />);
    const mask = decodeURIComponent(
      screen.getByTestId("camera-image-dev-corner").style.maskImage,
    );
    expect(mask).toContain(`viewBox="0 0 ${DEV_CORNER.w} ${DEV_CORNER.h}"`);
    expect(mask).not.toContain("feMorphology");
    expect(mask).toContain(`<rect width="1000" height="1000" fill="#fff"/>`);
  });

  it("cuts the image to the floor the camera can see", () => {
    render(<Harness cameras={[{ ...CAMERA, coverage_mm: PART_COVERAGE }]} />);
    const mask = decodeURIComponent(
      screen.getByTestId("camera-image-dev-corner").style.maskImage,
    );
    expect(mask).toContain(
      `<clipPath id="c"><polygon points="` +
        `${polygonPoints(PART_COVERAGE, DEV_CORNER)}"/></clipPath>`,
    );
    expect(mask).toContain(`<g clip-path="url(#c)">`);
  });

  it("draws the whole box when the camera reports no coverage polygon", () => {
    render(<Harness cameras={[{ ...CAMERA, coverage_mm: [] }]} />);
    expect(
      screen.getByTestId("camera-image-dev-corner").style.maskImage,
    ).toBe("");
    expect(
      screen.queryByTestId("camera-coverage-dev-corner"),
    ).not.toBeInTheDocument();
  });

  it("draws the edge of the camera's view where it falls inside the area", () => {
    render(<Harness cameras={[{ ...CAMERA, coverage_mm: PART_COVERAGE }]} />);
    expect(
      screen.getByTestId("camera-coverage-dev-corner").getAttribute("points"),
    ).toBe(polygonPoints(PART_COVERAGE, DEV_CORNER));
  });

  it("puts that edge outside the box for a camera covering the area whole", () => {
    // The svg clips to the area, so an outline whose corners all sit well
    // clear of it draws no line: full coverage reads as a clean area rather
    // than as one more boundary to interpret.
    render(<Harness />);
    const points = screen
      .getByTestId("camera-coverage-dev-corner")
      .getAttribute("points")!
      .split(" ")
      .map((p) => p.split(",").map(Number));
    expect(points).toHaveLength(4);
    for (const [x, y] of points) {
      expect(x < 0 || x > DEV_CORNER.w || y < 0 || y > DEV_CORNER.h).toBe(true);
    }
  });

  it("lies under the grid, so the grid and the glyphs stay on top", () => {
    render(<Harness />);
    const layer = screen.getByTestId("camera-layer-dev-corner");
    const grid = screen.getByTestId("map-grid");
    expect(layer.parentElement).toBe(grid.parentElement);
    const drawn = Array.from(layer.parentElement!.children);
    expect(drawn.indexOf(layer)).toBeLessThan(drawn.indexOf(grid));
  });

  it("draws nothing for a camera on an area the site does not define", () => {
    render(<Harness cameras={[{ ...CAMERA, area: "gone" }]} />);
    expect(screen.queryByTestId("camera-layer-gone")).not.toBeInTheDocument();
    // The row still lists it: the controller is warping it, and a silent
    // omission on both surfaces would hide the mismatch.
    expect(
      screen.getByLabelText("Camera opacity on gone"),
    ).toBeInTheDocument();
  });
});

// Four sheets in the middle of the 2 x 2 m arena: a 400 mm span with 1.3 m
// of area beyond it in every direction, so the extrapolation runs to 300%.
const PATCH_SPAN: number[][] = [
  [800, 800],
  [1200, 800],
  [1200, 1200],
  [800, 1200],
];

describe("the falloff past the span", () => {
  it("is measured in the span's own size, not the room left over", () => {
    expect(spanSizeMm(SPAN)).toBeCloseTo(853, 9);
    expect(fadeMm(SPAN)).toEqual({ start: 213.25, end: 853 });
    expect(spanSizeMm(PATCH_SPAN)).toBeCloseTo(400, 9);
    expect(fadeMm(PATCH_SPAN)).toEqual({ start: 100, end: 400 });
  });

  it("leaves a span that nearly fills its area whole to the edge", () => {
    // The area corner is 73.5 mm past an 853 mm span, a 9% extrapolation.
    expect(reachMm(SPAN, DEV_CORNER)).toBeCloseTo(Math.hypot(30, 73.5), 9);
    expect(reachMm(SPAN, DEV_CORNER)).toBeLessThan(fadeMm(SPAN).start);
    expect(spanMask(SPAN, DEV_CORNER)).toBe("");
  });

  it("still takes a small patch in a big area to nothing inside it", () => {
    expect(reachMm(PATCH_SPAN, ARENA)).toBeCloseTo(Math.hypot(800, 800), 9);
    expect(fadeMm(PATCH_SPAN).end).toBeLessThan(reachMm(PATCH_SPAN, ARENA));
    const mask = decodeURIComponent(spanMask(PATCH_SPAN, ARENA));
    // Dilated to the middle of the falloff, then blurred three standard
    // deviations either side of it: whole at 100 mm, gone by 400 mm.
    expect(mask).toContain(`<feMorphology operator="dilate" radius="250"`);
    expect(mask).toContain(`<feGaussianBlur stdDeviation="50"`);
    expect(mask).toContain(`viewBox="0 0 2000 2000"`);
    expect(mask).toContain(
      `<filter id="f" filterUnits="userSpaceOnUse" x="0" y="0"` +
        ` width="2000" height="2000">`,
    );
  });

  it("clips a faded span to the coverage as well", () => {
    const mask = decodeURIComponent(
      spanMask(PATCH_SPAN, ARENA, PART_COVERAGE),
    );
    expect(mask).toContain("feMorphology");
    expect(mask).toContain(`<g clip-path="url(#c)">`);
  });

  it("masks nothing when the camera reports neither polygon", () => {
    expect(spanMask([], DEV_CORNER)).toBe("");
    expect(spanMask([], DEV_CORNER, [])).toBe("");
  });

  it("cuts to the coverage even with no span to fade from", () => {
    const mask = decodeURIComponent(spanMask([], DEV_CORNER, PART_COVERAGE));
    expect(mask).not.toContain("feMorphology");
    expect(mask).toContain(`<g clip-path="url(#c)">`);
    expect(mask).toContain(`<rect width="1000" height="1000" fill="#fff"/>`);
  });
});

describe("the opacity this browser remembers", () => {
  it("starts every camera at the default", () => {
    expect(opacityFor({}, "dev-corner")).toBe(DEFAULT_CAMERA_OPACITY);
  });

  it("round-trips through storage", () => {
    saveCameraOpacity({ "dev-corner": 0.25 });
    expect(opacityFor(loadCameraOpacity(), "dev-corner")).toBe(0.25);
  });

  it("ignores a stored value that is not an opacity", () => {
    window.localStorage.setItem(
      "dotbot.console.cameraOpacity",
      '{"dev-corner": "half", "arena": 2, "annex": 0.5}',
    );
    expect(loadCameraOpacity()).toEqual({ annex: 0.5 });
  });

  it("falls back to the default when storage refuses to answer", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("storage blocked");
    });
    expect(loadCameraOpacity()).toEqual({});
  });

  it("keeps working when storage refuses to remember", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("storage blocked");
    });
    expect(() => saveCameraOpacity({ "dev-corner": 0.25 })).not.toThrow();
  });

  it("clamps what a caller sets, and leaves the other areas alone", () => {
    expect(withOpacity({ arena: 0.4 }, "dev-corner", 1.4)).toEqual({
      arena: 0.4,
      "dev-corner": 1,
    });
    expect(withOpacity({}, "dev-corner", -1)).toEqual({ "dev-corner": 0 });
  });
});

describe("the offset that lines the image up with the robots", () => {
  it("translates the layer by the offset, in the box's own percentage", () => {
    render(<Harness />);
    const layer = screen.getByTestId("camera-layer-dev-corner");
    expect(layer.style.transform).toBe("");

    fireEvent.change(screen.getByLabelText("Camera offset x on dev-corner"), {
      target: { value: "36" },
    });

    // dev-corner is 1000 mm wide, so 36 mm of frame is 3.6% of the box.
    expect(layer.style.transform).toBe("translate(3.6%, 0%)");
    expect(window.localStorage.getItem("dotbot.console.cameraOffset")).toBe(
      '{"dev-corner":{"dx":36,"dy":0}}',
    );
  });

  it("moves the image and its outlines, and no other layer", () => {
    render(<Harness />);
    fireEvent.change(screen.getByLabelText("Camera offset y on dev-corner"), {
      target: { value: "-20" },
    });
    const layer = screen.getByTestId("camera-layer-dev-corner");
    expect(layer.style.transform).toBe("translate(0%, -2%)");

    // The photograph and the boundary drawn on it ride inside the nudged
    // box, so the line stays on the picture it annotates.
    for (const id of [
      "camera-image-dev-corner",
      "camera-coverage-dev-corner",
    ]) {
      expect(layer.contains(screen.getByTestId(id))).toBe(true);
    }

    // Every other layer drawn in the same box is left where it was, which is
    // what keeps the glyph reporting the measurement rather than the picture.
    const drawn = Array.from(layer.parentElement!.children) as HTMLElement[];
    expect(drawn.length).toBeGreaterThan(1);
    for (const el of drawn) {
      if (el !== layer) expect(el.style.transform).toBe("");
    }
  });

  it("resets to no nudge, and offers the reset only when there is one", () => {
    render(<Harness />);
    const reset = screen.getByLabelText("Reset camera offset on dev-corner");
    expect(reset).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Camera offset x on dev-corner"), {
      target: { value: "36" },
    });
    expect(reset).toBeEnabled();

    fireEvent.click(reset);
    expect(screen.getByTestId("camera-layer-dev-corner").style.transform).toBe(
      "",
    );
    expect(reset).toBeDisabled();
  });
});

describe("the offset this browser remembers", () => {
  it("starts every camera unnudged", () => {
    expect(offsetFor({}, "dev-corner")).toEqual(NO_OFFSET);
  });

  it("round-trips through storage", () => {
    saveCameraOffset({ "dev-corner": { dx: 36, dy: -7 } });
    expect(offsetFor(loadCameraOffset(), "dev-corner")).toEqual({
      dx: 36,
      dy: -7,
    });
  });

  it("ignores a stored value that is not an offset", () => {
    window.localStorage.setItem(
      "dotbot.console.cameraOffset",
      '{"dev-corner": 36, "arena": {"dx": "east", "dy": 0},' +
        ' "annex": {"dx": 1, "dy": 2}}',
    );
    expect(loadCameraOffset()).toEqual({ annex: { dx: 1, dy: 2 } });
  });

  it("clamps a stored value that is past the limit", () => {
    window.localStorage.setItem(
      "dotbot.console.cameraOffset",
      '{"dev-corner": {"dx": 9000, "dy": -9000}}',
    );
    expect(loadCameraOffset()).toEqual({
      "dev-corner": { dx: 1000, dy: -1000 },
    });
  });

  it("falls back to no nudge when storage refuses to answer", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("storage blocked");
    });
    expect(loadCameraOffset()).toEqual({});
  });

  it("keeps working when storage refuses to remember", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("storage blocked");
    });
    expect(() =>
      saveCameraOffset({ "dev-corner": { dx: 36, dy: 0 } }),
    ).not.toThrow();
  });

  it("clamps what a caller sets, and leaves the other areas alone", () => {
    expect(
      withOffset({ arena: { dx: 1, dy: 2 } }, "dev-corner", {
        dx: 4000,
        dy: -4000,
      }),
    ).toEqual({
      arena: { dx: 1, dy: 2 },
      "dev-corner": { dx: 1000, dy: -1000 },
    });
  });

  it("reads an emptied field as no nudge rather than as NaN", () => {
    expect(withOffset({}, "dev-corner", { dx: NaN, dy: 5 })).toEqual({
      "dev-corner": { dx: 0, dy: 5 },
    });
  });
});

describe("the offset as a transform", () => {
  it("is a percentage of the matching side, so a millimetre is a millimetre", () => {
    expect(offsetTransform({ dx: 36, dy: -20 }, DEV_CORNER)).toBe(
      "translate(3.6%, -2%)",
    );
  });

  it("is nothing at all when the layer is not nudged", () => {
    expect(offsetTransform(NO_OFFSET, DEV_CORNER)).toBeUndefined();
  });

  it("is nothing for an area with no size to scale against", () => {
    expect(
      offsetTransform({ dx: 36, dy: 0 }, { x: 0, y: 0, w: 0, h: 0 }),
    ).toBeUndefined();
  });
});
