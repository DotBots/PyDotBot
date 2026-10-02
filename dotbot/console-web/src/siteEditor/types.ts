import type { AreaRole } from "../types";

// The editor's model of a site pack's `site.toml`, as GET /api/site serves it.

/** One area as the file declares it: `role` is the declared one, not the implied. */
export interface EditArea {
  name: string;
  x: number;
  y: number;
  w: number;
  h: number;
  role: AreaRole | null;
  comment: string | null;
  /** The area's name in the file when the page loaded it; null for a new one. */
  was?: string | null;
}

export interface SiteModel {
  anchor: string | null;
  extent_mm: [number, number] | null;
  areas: EditArea[];
  connection?: { conn?: string | null; swarm_id?: string | null } | null;
}

export interface CalibrationFolder {
  folder: string;
  count: number;
}

export interface SiteResponse {
  name: string;
  path: string;
  revision: string;
  site: SiteModel;
  calibrations: CalibrationFolder[];
  written?: boolean;
}

/** One LH2 calibration file, as GET /api/calibrations lists it. */
export interface CalibrationListing {
  id: string;
  id8: string;
  created_at: string;
  /** Solved in its own frame by spinning robots, so it may be moved. */
  free: boolean;
  /** The solved stations' lh_index. */
  stations: number[];
  tag: string;
  site: string;
  path: string;
}

/** One spin circle, its centre in the calibration's frame. */
export interface SpinCircle {
  name: string;
  x: number;
  y: number;
  radius_mm: number;
}

/** A calibration as the editor draws it, every number in its own frame. */
export interface CalibrationOverlay {
  id: string;
  id8: string;
  free: boolean;
  fence: [number, number, number, number];
  stations: {
    index: number;
    channel: number;
    /** The station's own rectangle, else the fence. */
    rect: [number, number, number, number];
    centres: [number, number][];
    circles: SpinCircle[];
    solved_from: string;
  }[];
  links: { a: number; b: number; shared: number; weak: boolean }[];
  tag: string;
  created_at: string;
  site: string;
  anchor: string;
}

/** What POST /api/calibrations/{id}/place answers: the new calibration. */
export interface PlacedCalibration extends CalibrationOverlay {
  path: string;
  source: string;
  push: string;
  warnings: string[];
}

/** One LH2 calibration of this site, drawn read-only under the areas. */
export interface CalibrationBackdrop {
  id8: string;
  tag: string;
  created_at: string;
  /** Each placement's points, frame mm. */
  placements: [number, number][][];
  /** Spin centres, frame mm. */
  centres: [number, number][];
}

/** One registered camera of this site. */
export interface CameraBackdrop {
  id8: string;
  area: string;
  /** The area it is registered on, [x, y, w, h]; null when the site lacks it. */
  rect: [number, number, number, number] | null;
  span: [number, number][];
  /** The still warped onto `rect`, when one was saved beside the file. */
  still: string | null;
}

export interface Backdrops {
  calibrations: CalibrationBackdrop[];
  cameras: CameraBackdrop[];
}
