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
  /** Standalone: what the config names for this site. */
  configured: { spec: string; source: string; id?: string; id8?: string; tag?: string; error?: string } | null;
  controller?: { version: string; port: number };
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
  fence: Rect;
  /** The measurement the file holds: files differing only in boxes share it. */
  spin: string;
  tracks: number;
  stations: LibraryStation[];
  /** The boxes in one line, by the robots' station rule. */
  reading: string;
  in_frame: boolean;
  served: boolean;
}

export interface Library {
  site: string;
  served: string | null;
  serving: LibraryRow | null;
  count: number;
  groups: { spin: string; created_at: string; rows: LibraryRow[] }[];
  not_placed: LibraryRow[];
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
  extent_mm: [number, number] | null;
  areas: EditorArea[];
  walls?: { name?: string | null; points: [number, number][] }[];
  obstacles?: { name?: string | null; points: [number, number][] }[];
  objects?: { name: string; kind: string; x: number; y: number; heading_deg: number }[];
}

export interface SitePayload {
  name: string;
  path: string;
  revision: string;
  /** site.toml as it is on disk. */
  text?: string;
  site: EditorSite;
}
