import { useEffect, useState } from "react";

/** How long the zoom must hold still before the markers are laid out again. */
export const MARKER_SETTLE_MS = 150;

/** How far a CSS scale may carry a marker before it is laid out at once. */
export const MARKER_STRETCH_MAX = 2;

/** Whether markers laid out at `laidOut` px/mm must be redrawn now for `perMm`. */
export function markerLayoutStale(perMm: number, laidOut: number): boolean {
  if (!(laidOut > 0) || !(perMm > 0)) return perMm !== laidOut;
  const stretch = perMm / laidOut;
  return stretch > MARKER_STRETCH_MAX || stretch < 1 / MARKER_STRETCH_MAX;
}

/**
 * The px/mm the robot markers are laid out at: `perMm` once it has held still
 * for `MARKER_SETTLE_MS`, or at once when a CSS scale would stretch the old
 * layout too far. In between the caller scales the markers by
 * `perMm / markerPerMm`.
 */
export function useMarkerPerMm(perMm: number): number {
  const [laidOut, setLaidOut] = useState(perMm);
  const stale = markerLayoutStale(perMm, laidOut);
  useEffect(() => {
    if (perMm === laidOut) return;
    if (stale) {
      setLaidOut(perMm);
      return;
    }
    const t = setTimeout(() => setLaidOut(perMm), MARKER_SETTLE_MS);
    return () => clearTimeout(t);
  }, [perMm, laidOut, stale]);
  return stale ? perMm : laidOut;
}
