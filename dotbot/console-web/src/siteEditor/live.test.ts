import { describe, expect, it } from "vitest";

import { insideRect, liveRefusal, liveShown } from "./live";

const robot = (id: string, otherSite = "") => ({ id, x: 100, y: 100, heading_deg: null, otherSite });

describe("live robots", () => {
  it("draws them in the frame of a calibration of this site and anchor", () => {
    expect(liveRefusal({ id: "abcd1234ffff", site: "arena", anchor: "the door" }, "arena", "the door")).toBeNull();
    expect(liveRefusal(null, "arena", "the door")).toBeNull();
    // Anchors are compared only when both are recorded
    expect(liveRefusal({ id: "abcd1234ffff", site: "arena", anchor: "" }, "arena", "the door")).toBeNull();
  });

  it("says why when the served calibration is another site's or another anchor's", () => {
    expect(liveRefusal({ id: "abcd1234ffff", site: "lab", anchor: "" }, "arena", "x")).toContain("of site lab");
    expect(liveRefusal({ id: "abcd1234ffff", site: "arena", anchor: "old" }, "arena", "new")).toContain("another anchor");
    const shown = liveShown({ robots: [robot("a")], served: { id: "abcd1234ffff", site: "lab", anchor: "" } }, "arena", null);
    expect(shown.robots).toEqual([]);
    expect(shown.note).toContain("Robots not drawn");
  });

  it("leaves out a robot holding another site's calibration", () => {
    const shown = liveShown({ robots: [robot("a"), robot("b", "lab")], served: null }, "arena", null);
    expect(shown.robots.map((r) => r.id)).toEqual(["a"]);
    expect(shown.note).toBe("1 robot holds a calibration of site lab, in another frame, and is not drawn.");
  });

  it("counts a point on the edge of a box as inside", () => {
    expect(insideRect({ x: 0, y: 0, w: 10, h: 10 }, 10, 0)).toBe(true);
    expect(insideRect({ x: 0, y: 0, w: 10, h: 10 }, 11, 0)).toBe(false);
  });
});
