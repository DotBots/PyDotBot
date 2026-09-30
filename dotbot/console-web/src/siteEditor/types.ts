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
