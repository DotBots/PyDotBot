import { describe, expect, it } from "vitest";

import { docFromSite } from "./model";
import { areaArg, problems } from "./rules";

const ROOM = (staging: { x: number; y: number; w: number; h: number }) =>
  docFromSite({
    anchor: null,
    extent_mm: [1060, 1220],
    areas: [
      { name: "field", x: 0, y: 0, w: 1060, h: 1220 },
      { name: "staging", role: "staging", ...staging },
    ],
  });

describe("the field and staging rule", () => {
  it("refuses staging drawn over the field and offers two fixes, applying neither", () => {
    const doc = ROOM({ x: 0, y: 1000, w: 1060, h: 220 });
    const [p] = problems(doc);
    expect(p.blocking).toBe(true);
    expect(p.title).toBe("Field and staging split the extent");
    expect(p.fixes.map((f) => f.label)).toEqual(["Shrink the field to 1060 × 1000", "Grow the extent by 220 mm, staging below"]);
    expect(doc.areas[0].h).toBe(1220);
    const grown = p.fixes[1].doc;
    expect(grown.extent_mm).toEqual([1060, 1440]);
    expect(grown.areas[1]).toMatchObject({ y: 1220, h: 220 });
    expect(problems(p.fixes[0].doc).filter((q) => q.blocking)).toEqual([]);
    expect(problems(grown).filter((q) => q.blocking)).toEqual([]);
  });

  it("lets staging touch the field and a corner overlap anything", () => {
    const doc = ROOM({ x: 0, y: 1220, w: 1060, h: 200 });
    doc.extent_mm = [1060, 1420];
    doc.areas.push({ ...doc.areas[0], key: "area:c", name: "c", role: "corner", x: 0, y: 0, w: 100, h: 100, was: null });
    expect(problems(doc)).toEqual([]);
  });

  it("warns, without blocking, about an area off the floor and offers to clip it", () => {
    const doc = ROOM({ x: 0, y: 1220, w: 1060, h: 200 });
    doc.areas[1] = { ...doc.areas[1], role: "corner", x: 1000, y: 1100, w: 100, h: 200 };
    const [p] = problems(doc);
    expect(p).toMatchObject({ blocking: false, title: "staging runs off the extent" });
    expect(p.fixes[0].label).toBe("Clip it to the extent (60 × 120)");
  });
});

describe("area names and a staging corner", () => {
  it("refuses a name scripts cannot pass to --area, and offers one they can", () => {
    const doc = docFromSite({ anchor: "x", extent_mm: [2000, 2000], areas: [{ name: "Parking Zone!", x: 0, y: 0, w: 100, h: 100 }] });
    const [p] = problems(doc);
    expect(p.blocking).toBe(true);
    expect(p.fixes[0].label).toBe("Rename it Parking-Zone");
    expect(problems(p.fixes[0].doc)).toEqual([]);
  });

  it("offers to shrink the field when staging overlaps one of its corners", () => {
    const doc = docFromSite({
      anchor: "x",
      extent_mm: [2000, 2000],
      areas: [
        { name: "field", x: 0, y: 0, w: 1000, h: 1000 },
        { name: "staging", x: 800, y: 900, w: 400, h: 300 },
      ],
    });
    const fixes = problems(doc)[0].fixes.filter((f) => f.label.startsWith("Shrink"));
    expect(fixes.map((f) => f.label)).toEqual(["Shrink the staging to 400 × 200", "Shrink the field to 1000 × 900"]);
    for (const f of fixes) expect(problems(f.doc)).toEqual([]);
  });

  it("gives up the small corner square rather than a strip of the field", () => {
    const doc = docFromSite({
      anchor: "x",
      extent_mm: [3000, 2000],
      areas: [
        { name: "field", x: 0, y: 0, w: 3000, h: 2000 },
        { name: "staging", x: 2800, y: 1800, w: 300, h: 300 },
      ],
    });
    const [first] = problems(doc)[0].fixes;
    expect(first.label).toBe("Shrink the staging to 300 × 100");
    expect(first.note).toContain("the field stays whole");
  });

  it("quotes a name the shell would split when it says --area", () => {
    expect(areaArg("field")).toBe("field");
    expect(areaArg("Parking Zone!")).toBe("'Parking Zone!'");
  });
});
