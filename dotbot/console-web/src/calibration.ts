import { headingToGlyphRotation } from "./frame";
import type { Area, CalibrationPoint, CalibrationSession } from "./types";

// Calibration mode, as geometry and wording rather than markup.
//
// The controller resolves the points and owns the loop; everything here is
// what a renderer needs on top of the state it sends, so the numbering, the
// glyph and the step wording can be read back in a test.

/** The order a placement stores its corners in, and captures them in. */
export const CORNERS = [
  "top-left",
  "top-right",
  "bottom-left",
  "bottom-right",
] as const;

/** Below this width the step card is the whole screen, per the floor layout. */
export const PHONE_MAX_PX = 480;

export function isPhoneWidth(width: number): boolean {
  return width < PHONE_MAX_PX;
}

/** The rectangle the session's points span, in frame millimetres. */
export function sessionRect(session: CalibrationSession | null): Area | null {
  if (!session || session.points.length === 0) return null;
  const xs = session.points.map((p) => p.x);
  const ys = session.points.map((p) => p.y);
  const x = Math.min(...xs);
  const y = Math.min(...ys);
  return { x, y, w: Math.max(...xs) - x, h: Math.max(...ys) - y, name: session.at };
}

/**
 * Heading for the robot glyph at one corner: the nose faces the nearest top
 * or bottom edge, so the top pair and the bottom pair face away from each
 * other. Heading 0 is +y, which is the bottom of the map.
 */
export function noseHeading(nose: string): number {
  return nose === "top" ? 180 : 0;
}

/** The glyph's on-screen rotation at one corner. */
export function noseRotation(nose: string): number {
  return headingToGlyphRotation(noseHeading(nose)) % 360;
}

/** "Step 3 of 4", one-based, for the point still outstanding. */
export function stepLabel(session: CalibrationSession): string {
  const step = session.outstanding === null ? session.total : session.outstanding + 1;
  return `Step ${step} of ${session.total}`;
}

/** The corner named in words, as a sentence opener: "Bottom-left corner". */
export function cornerTitle(point: CalibrationPoint): string {
  const words = point.corner ? `${point.corner} corner` : "Typed point";
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** The placement, as the instruction the operator follows. */
export function placementInstruction(point: CalibrationPoint): string {
  if (point.how) return point.how.charAt(0).toUpperCase() + point.how.slice(1) + ".";
  return `Photodiode on (${point.x}, ${point.y}) mm.`;
}

/** The point the card is about: the outstanding one, else the last. */
export function currentPoint(session: CalibrationSession): CalibrationPoint | null {
  if (session.points.length === 0) return null;
  const index = session.outstanding ?? session.points.length - 1;
  return session.points[index] ?? null;
}

/** How far one station's reads have got, as a fraction of the target. */
export function readFraction(reads: number, target: number): number {
  if (target <= 0) return 0;
  return Math.max(0, Math.min(1, reads / target));
}

/**
 * The expected-error line, or null. The predictor is a later phase, so the
 * controller sends no number and the line is absent rather than invented.
 */
export function expectedErrorLine(
  session: CalibrationSession | null,
  areaNames: string[],
): string | null {
  if (!session || typeof session.expected_error_mm !== "number") return null;
  const over = areaNames.length ? areaNames.join(", ") : "the whole site";
  return `expected ${session.expected_error_mm.toFixed(1)} mm over ${over}`;
}

/** What the card says once every point is captured and the stations solved. */
export function residualLines(session: CalibrationSession): string[] {
  return session.stations.map(
    (s) => `station ${s.index}  residual ${s.residual_mm.toFixed(1)} mm`,
  );
}
