import { describe, expect, it } from "vitest";

import {
  declaredRole,
  effectiveRole,
  frameChanged,
  freshName,
  moveRect,
  rectFromDrag,
  resizeRect,
  sameSite,
  siteIssues,
  snap,
} from "./edit";
import { finishPoints, freshObjectName, movePoints, parsePoints } from "./edit";
import type { EditArea, SiteModel } from "./types";

const area = (name: string, x: number, y: number, w: number, h: number, role: EditArea["role"] = null): EditArea => ({
  name,
  x,
  y,
  w,
  h,
  role,
  comment: null,
  was: name,
});

const arena = (): SiteModel => ({
  anchor: "the door corner",
  extent_mm: [2000, 4000],
  areas: [
    area("field", 0, 0, 2000, 2000),
    area("staging", 0, 2000, 2000, 2000),
    area("field+staging", 0, 0, 2000, 4000),
    area("dev-corner", 1000, 0, 1000, 1000, "corner"),
  ],
});

describe("snapping and dragging", () => {
  it("snaps to the step and leaves free placement at 1 mm", () => {
    expect(snap(1024, 50)).toBe(1000);
    expect(snap(1026, 50)).toBe(1050);
    expect(snap(1026.4, 1)).toBe(1026);
  });

  it("moves the corner onto the grid, keeping the size", () => {
    expect(moveRect({ x: 1000, y: 0, w: 1000, h: 1000 }, 48, 12, 50)).toEqual({ x: 1050, y: 0, w: 1000, h: 1000 });
  });

  it("resizes only the dragged edges", () => {
    const start = { x: 1000, y: 0, w: 1000, h: 1000 };
    expect(resizeRect(start, "se", { x: 2230, y: 1490 }, 50)).toEqual({ x: 1000, y: 0, w: 1250, h: 1500 });
    expect(resizeRect(start, "w", { x: 510, y: 9999 }, 50)).toEqual({ x: 500, y: 0, w: 1500, h: 1000 });
    expect(resizeRect(start, "n", { x: 0, y: 260 }, 50)).toEqual({ x: 1000, y: 250, w: 1000, h: 750 });
  });

  it("never flips or collapses a rectangle past its opposite edge", () => {
    const start = { x: 1000, y: 1000, w: 500, h: 500 };
    expect(resizeRect(start, "e", { x: 200, y: 0 }, 50)).toEqual({ x: 1000, y: 1000, w: 50, h: 500 });
    expect(resizeRect(start, "nw", { x: 3000, y: 3000 }, 50)).toEqual({ x: 1450, y: 1450, w: 50, h: 50 });
  });

  it("draws a rectangle from either corner, and ignores a click", () => {
    expect(rectFromDrag({ x: 1210, y: 990 }, { x: 190, y: 20 }, 50)).toEqual({ x: 200, y: 0, w: 1000, h: 1000 });
    expect(rectFromDrag({ x: 100, y: 100 }, { x: 110, y: 104 }, 50)).toBeNull();
  });
});

describe("roles", () => {
  it("takes the role from the name unless one is declared", () => {
    expect(effectiveRole({ name: "field", role: null })).toBe("field");
    expect(effectiveRole({ name: "dock", role: null })).toBeNull();
    expect(effectiveRole({ name: "field", role: "corner" })).toBe("corner");
  });

  it("declares a role only when the name does not already say it", () => {
    expect(declaredRole("field", "field")).toBeNull();
    expect(declaredRole("dock", "staging")).toBe("staging");
    expect(declaredRole("staging", "corner")).toBe("corner");
  });

  it("picks a name no area has", () => {
    expect(freshName([area("area-1", 0, 0, 1, 1)])).toBe("area-2");
  });
});

describe("siteIssues", () => {
  it("finds nothing wrong with a well-formed site", () => {
    expect(siteIssues(arena())).toEqual([]);
  });

  it("refuses a second field, as the schema does", () => {
    const site = arena();
    site.areas[1].role = "field";
    expect(siteIssues(site).filter((i) => i.level === "error")[0].message).toMatch(/at most one field/);
  });

  it("refuses names the resolver cannot reach", () => {
    const site = arena();
    site.areas[1].name = "a,b";
    site.areas[3].name = "field";
    const messages = siteIssues(site).map((i) => i.message);
    expect(messages.some((m) => m.includes("comma"))).toBe(true);
    expect(messages.some((m) => m.includes("two areas are named field"))).toBe(true);
  });

  it("warns about an area outside the extent and an oversized field", () => {
    const site = arena();
    site.areas[3].x = 1500;
    site.areas[0] = area("field", 0, 0, 6000, 2000);
    const warnings = siteIssues(site).filter((i) => i.level === "warning").map((i) => i.area);
    expect(warnings).toContain("dev-corner");
    expect(warnings).toContain("field");
  });

  it("warns when a composite is not the bounding box of its parts", () => {
    const site = arena();
    site.areas[1].h = 1000;
    const issue = siteIssues(site).find((i) => i.area === "field+staging");
    expect(issue?.message).toMatch(/0, 0, 2000 x 3000/);
  });
});

describe("change tracking", () => {
  it("tells a frame change from an area change", () => {
    const site = arena();
    const moved = { ...site, areas: site.areas.map((a, i) => (i === 3 ? { ...a, x: 950 } : a)) };
    expect(frameChanged(site, moved)).toBe(false);
    expect(frameChanged(site, { ...site, extent_mm: [2000, 4050] })).toBe(true);
    expect(frameChanged(site, { ...site, anchor: "elsewhere" })).toBe(true);
    expect(sameSite(site, moved)).toBe(false);
    expect(sameSite(site, { ...site, anchor: "the door corner" })).toBe(true);
  });
});

describe("barriers", () => {
  it("reads points one per line and refuses a line that does not read", () => {
    expect(parsePoints("0, 0\n1000 0\n\n 1000,  500 ")).toEqual([
      [0, 0],
      [1000, 0],
      [1000, 500],
    ]);
    expect(parsePoints("0, 0\n12")).toBeNull();
  });

  it("moves points with the first on the snap grid, and drops a double-click's repeat", () => {
    expect(movePoints([[10, 10], [110, 10]], 37, 0, 50)).toEqual([[50, 0], [150, 0]]);
    expect(finishPoints([[0, 0], [100, 0], [100, 0]])).toEqual([[0, 0], [100, 0]]);
  });

  it("flags a barrier with too few points and one outside the extent", () => {
    const site = {
      anchor: null,
      extent_mm: [2000, 2000] as [number, number],
      areas: [],
      walls: [{ name: "w", points: [[0, 0]] as [number, number][], comment: null }],
      obstacles: [{ name: null, points: [[0, 0], [3000, 0], [0, 100]] as [number, number][], comment: null }],
    };
    const messages = siteIssues(site).map((i) => `${i.level}: ${i.message}`);
    expect(messages).toContain("error: w needs at least 2 points");
    expect(messages).toContain("warning: obstacle 1 reaches outside the extent");
  });
});

describe("objects", () => {
  it("names a new object after the ones taken, and checks names", () => {
    expect(freshObjectName(["charger-1"], "charger")).toBe("charger-2");
    const site = {
      anchor: null,
      extent_mm: [2000, 2000] as [number, number],
      areas: [],
      objects: [
        { name: "a", kind: "charger" as const, x: 0, y: 0, heading_deg: 0, comment: null },
        { name: "a", kind: "dock" as const, x: 2500, y: 0, heading_deg: 0, comment: null },
      ],
    };
    const messages = siteIssues(site).map((i) => i.message);
    expect(messages).toContain("two objects are named a");
    expect(messages).toContain("a is outside the extent");
  });
});
