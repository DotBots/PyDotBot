import { describe, expect, it } from "vitest";

import { nearestBotIndex, PICK_RADIUS_MM } from "./pick";

// x, y, heading triples: three bots on a row 500 mm apart.
const POSES = new Float32Array([500, 500, 0, 1000, 500, 0, 1500, 500, 0]);

describe("nearestBotIndex", () => {
  it("picks the closest bot to the tap", () => {
    expect(nearestBotIndex(POSES, { x: 1040, y: 520 })).toBe(1);
    expect(nearestBotIndex(POSES, { x: 480, y: 470 })).toBe(0);
  });

  it("returns -1 when the tap lands on empty arena", () => {
    expect(nearestBotIndex(POSES, { x: 500, y: 500 + PICK_RADIUS_MM * 2 })).toBe(-1);
  });

  it("takes a bot exactly on the radius", () => {
    expect(nearestBotIndex(POSES, { x: 500, y: 500 + PICK_RADIUS_MM })).toBe(0);
  });

  it("has nothing to pick in an empty world", () => {
    expect(nearestBotIndex(new Float32Array(0), { x: 0, y: 0 })).toBe(-1);
  });
});
