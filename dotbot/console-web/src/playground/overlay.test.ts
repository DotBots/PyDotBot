import { describe, expect, it } from "vitest";

import { parseOut, parseOverlayItems } from "./overlay";

describe("parseOverlayItems", () => {
  it("keeps every kind the renderer draws", () => {
    const items = parseOverlayItems([
      { type: "point", x: 100, y: 200, label: "pad" },
      { type: "polyline", points: [{ x: 0, y: 0 }, { x: 10, y: 10 }], closed: true },
      { type: "rect", x: 0, y: 0, w: 500, h: 500, fill: true },
      { type: "label", x: 5, y: 5, text: "west" },
      { type: "badge", address: "DEAD", text: "charging", color: "good" },
    ]);
    expect(items.map((i) => i.type)).toEqual(["point", "polyline", "rect", "label", "badge"]);
  });

  it("drops items the canvas cannot place and keeps the rest", () => {
    const items = parseOverlayItems([
      { type: "point", x: 1, y: 2 },
      { type: "point", x: "left", y: 2 },
      { type: "rect", x: 0, y: 0, w: 10 },
      { type: "polyline", points: [{ x: 0, y: 0 }] },
      { type: "spline", points: [] },
      42,
    ]);
    expect(items).toEqual([{ type: "point", x: 1, y: 2 }]);
  });

  it("ignores a colour it cannot resolve to a token", () => {
    const [item] = parseOverlayItems([{ type: "point", x: 0, y: 0, color: "#ff00ff" }]);
    expect(item).toEqual({ type: "point", x: 0, y: 0 });
  });

  it("survives a non-list", () => {
    expect(parseOverlayItems("everything")).toEqual([]);
  });
});

describe("parseOut", () => {
  it("reads an overlay and a status", () => {
    expect(parseOut({ kind: "overlay", items: [{ type: "point", x: 1, y: 1 }] })).toEqual({
      kind: "overlay",
      items: [{ type: "point", x: 1, y: 1 }],
    });
    expect(parseOut({ kind: "status", text: "4 bots charging" })).toEqual({
      kind: "status",
      text: "4 bots charging",
    });
  });

  it("reads an empty overlay, which is how a script clears what it drew", () => {
    expect(parseOut({ kind: "overlay", items: [] })).toEqual({ kind: "overlay", items: [] });
  });

  it("returns null for anything the page does not show", () => {
    expect(parseOut({ kind: "positions", bots: [] })).toBeNull();
    expect(parseOut(null)).toBeNull();
    expect(parseOut({ kind: "status" })).toBeNull();
  });
});
