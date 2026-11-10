import { describe, expect, it } from "vitest";

import fixtures from "../../../calibration/station_rule.json";
import { candidates, select } from "./stationRule";

const num = (v: number | string) => (typeof v === "number" ? v : Number(v));
const rectsOf = (rects: Record<string, number[] | undefined>) =>
  Object.fromEntries(Object.entries(rects).flatMap(([k, v]) => (v ? [[Number(k), v]] : []))) as Record<number, number[]>;

describe("the station rule, against the fixtures the Python rule writes", () => {
  it.each(fixtures.cases.map((c) => [c.name, c] as const))("%s", (_, c) => {
    const solves = c.solves.map(([s, x, y]) => ({ station: Number(s), x: num(x), y: num(y) }));
    expect(select(solves, rectsOf(c.rects))).toBe(c.expect);
  });

  it.each(fixtures.points.map((p) => [p.name, p] as const))("%s", (_, p) => {
    expect(candidates(rectsOf(p.rects), p.point[0], p.point[1])).toEqual(p.expect);
  });

  it("covers every case", () => {
    expect(fixtures.cases).toHaveLength(17);
  });
});
