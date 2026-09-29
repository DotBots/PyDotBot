import { describe, expect, it } from "vitest";

import { areaColor } from "./areaColor";
import type { Area } from "./types";

const area = (name: string, role?: Area["role"]): Area => ({ x: 0, y: 0, w: 1, h: 1, name, role });

describe("areaColor", () => {
  it("colours areas of one role alike and each role apart", () => {
    const areas = [
      area("field", "field"),
      area("staging", "staging"),
      area("charging", "staging"),
      area("dev-corner", "corner"),
    ];
    const [field, staging, charging, corner] = areas.map((a) => areaColor(a, areas));
    expect(staging).toBe(charging);
    expect(new Set([field, staging, corner]).size).toBe(3);
  });

  it("gives role-less areas their own colours, none a role's", () => {
    const areas = [area("field", "field"), area("staging", "staging"), area("a"), area("b")];
    const colours = areas.map((a) => areaColor(a, areas));
    expect(new Set(colours).size).toBe(4);
  });

  it("keeps a role-less area's colour whatever order the areas come in", () => {
    const areas = [area("b"), area("a"), area("field", "field")];
    expect(areaColor(areas[0], areas)).toBe(areaColor(areas[0], [...areas].reverse()));
  });
});
