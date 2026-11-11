import { describe, expect, it } from "vitest";

import { bestSplit, contours, coverageSay, fixtureAgreement, handover, layoutText, moved, movedHandover, share, splitFloor, type Coverage } from "./coverage";
import type { LibraryRow } from "./types";

const GEOMETRY = {
  stations: { "0": { x_mm: -542, y_mm: 1268, height_mm: 2423, off_square_deg: 5.4 }, "1": { x_mm: 1387, y_mm: -245, height_mm: 1606, off_square_deg: -3.1 } },
  apart_mm: { "0-1": 2620 },
};

describe("the Stations kind's drawing", () => {
  it("agrees with every fixture the Python rule wrote", () => {
    expect(fixtureAgreement()).toEqual({ agree: 17, total: 17 });
  });

  it("finds a1b41f12's handover at x 530, and none for shared boxes", () => {
    expect(handover([0, 0, 630, 1220], [430, 0, 1060, 1220])?.label).toBe("handover x 530 mm");
    expect(handover([0, 0, 1060, 1220], [0, 0, 1060, 1220])).toBeNull();
    expect(handover([0, 0, 300, 1220], [500, 0, 1060, 1220])).toBeNull();
  });

  it("splits the floor with S0 on its own side and 200 mm of overlap", () => {
    expect(splitFloor([1060, 1220], GEOMETRY, [0, 1])).toEqual({ 0: [0, 0, 630, 1220], 1: [430, 0, 1060, 1220] });
    const swapped = { ...GEOMETRY, stations: { "0": GEOMETRY.stations["1"], "1": GEOMETRY.stations["0"] } };
    expect(splitFloor([1060, 1220], swapped, [0, 1])).toEqual({ 1: [0, 0, 630, 1220], 0: [430, 0, 1060, 1220] });
  });

  it("splits where each station is the more accurate, and in the middle without an error map", () => {
    expect(bestSplit([1060, 1220], GEOMETRY, [0, 1], null)).toMatchObject({ axis: "x", at: 530, boxes: { 0: [0, 0, 630, 1220], 1: [430, 0, 1060, 1220] } });
    // S0 is better up to x 400, S1 beyond: one row of 100 mm cells
    const cols = 11;
    const own = {
      "0": Array.from({ length: cols }, (_, i) => (i * 100 + 50 < 400 ? 0.5 : 2)),
      "1": Array.from({ length: cols }, (_, i) => (i * 100 + 50 < 400 ? 2 : 0.5)),
    };
    const fog: NonNullable<Coverage["fog"]> = { origin: [0, 0], cell_mm: 100, cols, rows: 1, sigma: [], undecided: [], own };
    const split = bestSplit([1060, 1220], GEOMETRY, [0, 1], fog);
    expect(split.at).toBe(400);
    expect(handover(split.boxes[0], split.boxes[1])?.label).toBe("handover x 400 mm");
  });

  it("moves a handover to a new line, keeping the overlap and the outer edges", () => {
    const boxes = [
      { index: 0, rect: [0, 0, 630, 1220] as [number, number, number, number] },
      { index: 1, rect: [430, 0, 1060, 1220] as [number, number, number, number] },
    ];
    const moved = movedHandover(boxes, 600)!;
    expect(moved).toEqual({ 0: [0, 0, 770, 1220], 1: [570, 0, 1060, 1220] });
    expect(handover(moved[0], moved[1])?.label).toBe("handover x 600 mm");
  });

  it("says what is drawn, and what is in use when the two differ", () => {
    const whole = [
      { index: 0, rect: [0, 0, 1060, 1220] as [number, number, number, number] },
      { index: 1, rect: [0, 0, 1060, 1220] as [number, number, number, number] },
    ];
    const split = [
      { index: 0, rect: [0, 0, 630, 1220] as [number, number, number, number] },
      { index: 1, rect: [430, 0, 1060, 1220] as [number, number, number, number] },
    ];
    expect(layoutText(whole)).toBe("both cover the whole floor, no handover");
    expect(coverageSay(whole, whole)).toEqual({ text: "both cover the whole floor, no handover", differs: false });
    expect(coverageSay(split, whole)).toEqual({ text: "handover at x 530 mm · not in use yet (in use: both cover the whole floor)", differs: true });
  });

  it("gives each station its share of the floor", () => {
    const boxes = [
      { index: 0, rect: [0, 0, 630, 1220] as [number, number, number, number] },
      { index: 1, rect: [430, 0, 1060, 1220] as [number, number, number, number] },
    ];
    expect(share(boxes, [1060, 1220], 0)).toBeCloseTo(0.5, 1);
  });

  it("draws a contour where the fog crosses a level", () => {
    const fog: NonNullable<Coverage["fog"]> = { origin: [0, 0], cell_mm: 10, cols: 2, rows: 2, sigma: [0.4, 0.6, 0.4, 0.6], undecided: [], own: {} };
    const segs = contours(fog, 0.5);
    expect(segs).toHaveLength(1);
    expect(segs[0][0]).toBeCloseTo(10, 6);
  });

  it("reads no sign of a move when the spins agree, and flags one that does not", () => {
    const row = (spin: string, h0: number, apart: number) =>
      ({ spin, in_frame: true, geometry: { stations: { "0": { ...GEOMETRY.stations["0"], height_mm: h0 } }, apart_mm: { "0-1": apart } } }) as unknown as LibraryRow;
    expect(moved(row("a", 2423, 2620), [row("b", 2400, 2600), row("c", 2480, 2640)]).verdict).toBe("no sign");
    expect(moved(row("a", 3100, 2620), [row("b", 2400, 2600), row("c", 2480, 2640)]).verdict).toBe("moved?");
    expect(moved(row("a", 2423, 2620), []).verdict).toBe("one spin");
    // A spin in another frame is not one of this room's
    expect(moved(row("a", 2423, 2620), [{ ...row("b", 2400, 2600), in_frame: false }]).verdict).toBe("one spin");
  });
});
