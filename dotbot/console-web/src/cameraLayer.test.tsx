import React, { useState } from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  CameraOpacity,
  DEFAULT_CAMERA_OPACITY,
  fadeMm,
  loadCameraOpacity,
  opacityFor,
  polygonPoints,
  reachMm,
  saveCameraOpacity,
  spanMask,
  spanSizeMm,
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

const CAMERA: RegisteredCamera = {
  area: "dev-corner",
  source: "/tmp/synthetic.png",
  mm_per_px: 2,
  width: 500,
  height: 500,
  span_mm: SPAN,
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

// The map and the Layers tab over one opacity map, exactly as App wires them.
const Harness: React.FC<{ cameras?: RegisteredCamera[] }> = ({
  cameras = [CAMERA],
}) => {
  const [cameraOpacity, setCameraOpacity] = useState<CameraOpacity>(
    loadCameraOpacity,
  );
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

  it("marks the span out, in the box's own coordinates", () => {
    render(<Harness />);
    // The box is the area, so the span's frame millimetres land as the
    // area's own: 1030 mm of frame is 30 mm into a dev-corner starting at
    // 1000.
    const points = "30,73.5 970,73.5 970,926.5 30,926.5";
    expect(
      screen.getByTestId("camera-span-dev-corner").getAttribute("points"),
    ).toBe(points);
    expect(polygonPoints(SPAN, DEV_CORNER)).toBe(points);
  });

  it("draws the image whole out to the area's edge, with no falloff", () => {
    render(<Harness />);
    expect(
      screen.getByTestId("camera-image-dev-corner").style.maskImage,
    ).toBe("");
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

  it("masks nothing when the camera reports no span", () => {
    expect(spanMask([], DEV_CORNER)).toBe("");
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
