import type { LH2Position, MapSize } from "./types";

// The arena frame, and the single place the console states it.
//
// Origin is the top-left corner, x grows right, y grows down. That is the
// frame the LH2 calibration builds: `dotbot swarm lh2-calibration collect`
// walks the operator through the corners top-left, top-right, bottom-left,
// bottom-right, and the homography maps the first of those to the smallest
// (x, y). The control loop integrates odometry in the same frame, so a map
// drawn any other way is a mirror of the room rather than a picture of it.

/** Arena mm to a fraction of the map box, 0..1 from its top-left corner. */
export function arenaToFraction(p: LH2Position, map: MapSize): { fx: number; fy: number } {
  return { fx: p.x / map.width, fy: p.y / map.height };
}

/** A fraction of the map box back to arena mm. */
export function fractionToArena(fx: number, fy: number, map: MapSize): LH2Position {
  return { x: fx * map.width, y: fy * map.height };
}

/**
 * Heading in degrees to the CSS rotation for a nose-up glyph. Heading 0 is +y,
 * which points at the bottom of the map, so the glyph turns half a circle
 * before the heading itself applies.
 */
export function headingToGlyphRotation(heading: number): number {
  return 180 + heading;
}
