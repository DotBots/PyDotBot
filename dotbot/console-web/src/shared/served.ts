import type { SiteCalibration } from "../types";

// What the serving chip says. The served id always leads; a second part says
// what the page shows besides it, and never replaces it.

export type ChipSide =
  | { kind: "none" }
  | { kind: "preview"; id8: string }
  | { kind: "draft"; from: string }
  | { kind: "run-only"; restart: string }
  | { kind: "frame-change" };

export interface ChipModel {
  /** "SERVING", or what a page with no controller has instead. */
  label: string;
  /** The served (or configured) id's first 8 characters; "" for none. */
  id8: string;
  tag: string;
  /** Whether a controller serves it now, rather than a config naming it. */
  live: boolean;
  side: ChipSide;
}

/** The chip for the calibration a controller serves, or its absence. */
export function servedChip(served: Pick<SiteCalibration, "id" | "tag"> | null | undefined): ChipModel {
  if (!served) return { label: "NO CALIBRATION", id8: "", tag: "", live: true, side: { kind: "none" } };
  return { label: "SERVING", id8: served.id.slice(0, 8), tag: served.tag, live: true, side: { kind: "none" } };
}

/** The chip of an editor no controller opened: the calibration the config
 * names for the site, marked as configured rather than served. */
export function configuredChip(configured: { id8?: string; spec: string; tag?: string } | null | undefined): ChipModel {
  if (!configured) return { label: "NO CONTROLLER", id8: "", tag: "", live: false, side: { kind: "none" } };
  return {
    label: "NO CONTROLLER · CONFIGURED",
    id8: configured.id8 ?? configured.spec,
    tag: configured.tag ?? "",
    live: false,
    side: { kind: "none" },
  };
}

/** The second part's words. */
export function sideText(side: ChipSide): string {
  switch (side.kind) {
    case "preview":
      return `previewing ${side.id8}`;
    case "draft":
      return `draft from ${side.from}`;
    case "run-only":
      return `this run only · restart: ${side.restart}`;
    case "frame-change":
      return "frame change · push needed";
    default:
      return "";
  }
}

/** Where the controller serves the site editor, from a console at `base`. */
export const SITE_EDITOR_PATH = "/controller/site-editor/";
