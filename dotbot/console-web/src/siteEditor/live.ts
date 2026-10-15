import type { LiveFleet, LiveRobot } from "./types";

// The console's robots over the site being edited. Their positions are in
// the frame of the calibration that put them there, so they are drawn only
// when that frame is this site's, as the console's own checks decide.

/** Why the served calibration's positions are not in this site's frame, or null when they are. */
export function liveRefusal(served: LiveFleet["served"], siteName: string, anchor: string | null): string | null {
  if (!served) return null;
  const id8 = served.id.slice(0, 8);
  if (served.site && served.site.toLowerCase() !== siteName.toLowerCase()) {
    return `the controller serves calibration ${id8} of site ${served.site}: its positions are in another frame`;
  }
  // Anchors are compared only when both are recorded, as the controller does
  if (served.anchor && anchor && served.anchor !== anchor) {
    return `the controller serves calibration ${id8}, which records another anchor than this site's: its positions are in another frame until a calibration of this anchor is served`;
  }
  return null;
}

/** The robots to draw, and why some or all are not. */
export function liveShown(fleet: LiveFleet, siteName: string, anchor: string | null): { robots: LiveRobot[]; note: string | null } {
  const refusal = liveRefusal(fleet.served, siteName, anchor);
  if (refusal) return { robots: [], note: `Robots not drawn: ${refusal}.` };
  const robots = fleet.robots.filter((r) => !r.otherSite);
  const left = fleet.robots.length - robots.length;
  if (left === 0) return { robots, note: null };
  const sites = [...new Set(fleet.robots.filter((r) => r.otherSite).map((r) => r.otherSite))].join(", ");
  return {
    robots,
    note: `${left} robot${left === 1 ? " holds a calibration" : "s hold calibrations"} of site ${sites}, in another frame, and ${left === 1 ? "is" : "are"} not drawn.`,
  };
}

export function insideRect(r: { x: number; y: number; w: number; h: number }, x: number, y: number): boolean {
  return x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h;
}
