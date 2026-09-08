import { BOT_FOOTPRINT_MM } from "./fakeWorld";
import type { Vec2 } from "./types";

// Picking a bot by tapping the map. Pure, so the gesture handler stays thin.

/** How far off a bot a tap still counts as picking it, in bot footprints. */
export const PICK_RADIUS_FOOTPRINTS = 3;

export const PICK_RADIUS_MM = PICK_RADIUS_FOOTPRINTS * BOT_FOOTPRINT_MM;

/**
 * The bot nearest `at` within `radiusMm`, or -1 when the tap landed on empty
 * arena. `poses` is the renderer's x, y, heading triples.
 */
export function nearestBotIndex(
  poses: Float32Array,
  at: Vec2,
  radiusMm: number = PICK_RADIUS_MM,
): number {
  let best = -1;
  let bestD2 = radiusMm * radiusMm;
  const n = Math.floor(poses.length / 3);
  for (let i = 0; i < n; i++) {
    const dx = poses[i * 3] - at.x;
    const dy = poses[i * 3 + 1] - at.y;
    const d2 = dx * dx + dy * dy;
    if (d2 <= bestD2) {
      bestD2 = d2;
      best = i;
    }
  }
  return best;
}
