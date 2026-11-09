import type { AreaRole, SiteObjectKind } from "../types";

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

/** A wall (polyline) or an obstacle (closed polygon), frame mm. */
export interface EditBarrier {
  name: string | null;
  points: [number, number][];
  comment: string | null;
  /** The entry's index in the file when the page loaded it; null for a new one. */
  was?: number | null;
}

export type BarrierKind = "walls" | "obstacles";

/** One `[objects.<name>]` table: a thing on the floor at a pose, frame mm. */
export interface EditObject {
  name: string;
  kind: SiteObjectKind;
  x: number;
  y: number;
  heading_deg: number;
  comment: string | null;
  /** The object's name in the file when the page loaded it; null for a new one. */
  was?: string | null;
}

export interface SiteModel {
  anchor: string | null;
  extent_mm: [number, number] | null;
  areas: EditArea[];
  walls?: EditBarrier[];
  obstacles?: EditBarrier[];
  objects?: EditObject[];
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
  /** In this site's frame, so its station boxes may be edited. */
  in_frame: boolean;
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
  /** Why it is not in this site's frame; null when it is. */
  frame_refusal?: string | null;
}

/** What POST /api/calibrations/{id}/place and /boxes answer: the new calibration. */
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

/** What GET /api/turn answers: the site's anchor and what a turn would rewrite. */
export interface TurnInfo {
  anchor: string;
  /** The middle of the extent, frame mm. */
  pivot: [number, number];
  /** Why the turn moves zero off something measured on the floor; empty when nothing is. */
  anchor_marks: string[];
  /** The calibrations in the site's frame. */
  calibrations: { id: string; id8: string; tag: string; created_at: string; stations: number[]; path: string }[];
}

/** What POST /api/turn answers: one new calibration per one turned. */
export interface TurnSaved {
  saved: PlacedCalibration[];
  anchor_marks: string[];
}

/** One robot of the console's fleet: its LH2 fix and heading, frame mm. */
export interface LiveRobot {
  id: string;
  x: number;
  y: number;
  heading_deg: number | null;
  /** The site of the calibration it holds when not this one, "" otherwise. */
  otherSite: string;
}

/** The console's fleet, and the calibration the controller serves. */
export interface LiveFleet {
  robots: LiveRobot[];
  served: { id: string; site: string; anchor: string } | null;
}
