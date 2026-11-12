// The site editor's server payloads.

export type Rect = [number, number, number, number];

export interface ServedCalibration {
  id: string;
  id8: string;
  tag: string;
  created_at: string;
  spec: string | null;
  /** "the command line", or the config file that named it. */
  source: string;
}

export interface EditorContext {
  mode: "controller" | "standalone";
  site: string;
  path: string;
  served: ServedCalibration | null;
  /** What the controller serves after a restart, from its config. */
  next_start: { spec: string; source: string } | null;
  /** What this run started serving, and from where. */
  started_with?: { spec: string; source: string } | null;
  /** A frame change this controller served, until robots hold it. */
  frame_change?: { from_id: string; to_id: string; from_frame: string; to_frame: string } | null;
  /** The file "also at the next start" writes to. */
  persist_path?: string | null;
  /** Standalone: what the config names for this site. */
  configured: { spec: string; source: string; id?: string; id8?: string; tag?: string; error?: string } | null;
  controller?: { version: string; port: number };
  /** False on a page opened from another machine: it may only view. */
  can_write?: boolean;
  /** The controller's site has no site pack: there is nothing to edit yet. */
  no_site?: boolean;
  site_name?: string;
}

export interface LibraryStation {
  index: number;
  residual_mm: number;
  box: Rect;
  solved_from: string;
}

export interface LibraryRow {
  id: string;
  id8: string;
  tag: string;
  created_at: string;
  path: string;
  site: string;
  coverage_union: Rect;
  /** The measurement the file holds: files differing only in boxes share it. */
  spin: string;
  tracks: number;
  stations: LibraryStation[];
  /** The boxes in one line, by the robots' station rule. */
  reading: string;
  in_frame: boolean;
  served: boolean;
  /** A spin in its own frame, zero at its robots' top-left: placed in a room before use */
  free?: boolean;
  /** The spin this file was placed from, "" when it was not placed. */
  placed_from?: string;
  /** Where the stations stand, estimated from the homographies. */
  geometry?: {
    stations: Record<string, { x_mm: number; y_mm: number; height_mm: number; off_square_deg: number }>;
    apart_mm: Record<string, number>;
  };
}

export interface Library {
  site: string;
  served: string | null;
  serving: LibraryRow | null;
  count: number;
  groups: { spin: string; created_at: string; rows: LibraryRow[] }[];
  not_placed: LibraryRow[];
  archived?: LibraryRow[];
  /** Files under the site this build cannot read, with the schema they carry. */
  unreadable?: { path: string; name: string; schema: number | null; error: string }[];
}

export interface EditorArea {
  name: string;
  x: number;
  y: number;
  w: number;
  h: number;
  role?: "field" | "staging" | "corner" | null;
  comment?: string | null;
}

export interface EditorSite {
  anchor: string | null;
  /** The frame id site.toml records, null when it is derived. */
  frame?: string | null;
  extent_mm: [number, number] | null;
  areas: EditorArea[];
  walls?: { name?: string | null; points: [number, number][] }[];
  obstacles?: { name?: string | null; points: [number, number][] }[];
  objects?: { name: string; kind: string; x: number; y: number; heading_deg: number }[];
  /** The spots the frame was anchored on: tape-measured, and the robot's distance from each once anchored. */
  anchor_spots?: { at_mm: [number, number]; error_mm: number }[];
}

export interface SitePayload {
  name: string;
  path: string;
  revision: string;
  /** The site's frame id, recorded or derived from its name and note. */
  frame_id?: string;
  /** The path with the home folder as ~. */
  shown_path?: string;
  /** site.toml as it is on disk. */
  text?: string;
  site: EditorSite;
}
