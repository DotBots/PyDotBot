import type { SiteObjectKind } from "./types";

// How a site object is drawn, on the map and in the site editor alike.

export const OBJECT_KINDS: SiteObjectKind[] = ["charger", "dock", "landmark", "camera"];

/** The drawn size of an object, in floor mm: about a robot's. */
export const OBJECT_SIZE_MM = 120;

export const OBJECT_COLOUR: Record<SiteObjectKind, string> = {
  charger: "var(--s-Running)",
  dock: "var(--s-Bootloader)",
  landmark: "var(--s-Programming)",
  camera: "var(--s-Resetting)",
};

/** The unit vector an object faces, in frame axes (heading 0 faces +y). */
export function facing(headingDeg: number): [number, number] {
  const t = (headingDeg * Math.PI) / 180;
  return [-Math.sin(t), Math.cos(t)];
}
