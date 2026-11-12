import type { Coverage } from "./coverage";
import type { EditorContext, EditorSite, Library, Rect, SitePayload } from "./types";

// Every route is relative to the page: the controller serves the editor at
// /controller/site-editor/ and `dotbot site edit` at its own root.

export class HttpError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      // not JSON: the status text says enough
    }
    throw new HttpError(response.status, `${response.status}: ${detail}`);
  }
  return (await response.json()) as T;
}

const post = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const fetchContext = () => json<EditorContext>("api/context");
export const fetchSite = () => json<SitePayload>("api/site");
export const fetchLibrary = () => json<Library>("api/calibrations?scope=site");
export const previewSite = (site: unknown, text: string | null = null) =>
  json<{ text: string; changed: boolean }>("api/preview", post({ site, text }));
export const parseSite = (text: string) => json<{ site: EditorSite }>("api/parse", post({ text }));
export const fetchRevision = () => json<{ revision: string }>("api/revision");
export const openInEditor = () => json<{ command: string; path: string }>("api/open", post({}));

export interface ApplyStep {
  step: "site.toml" | "calibration" | "use";
  status: "written" | "reused" | "unchanged" | "refused";
  detail: string;
  id?: string;
}

/** A move of the room's origin, in the saved frame's mm, as the server takes it. */
export interface MoveBody {
  theta_deg: number;
  pivot: [number, number];
  dx_mm: number;
  dy_mm: number;
}

/** Every pending edit of one calibration. */
export interface CalibrationEdit {
  source: string;
  frame?: MoveBody | null;
  place?: { theta_deg: number; dx_mm: number; dy_mm: number } | null;
  stations?: Record<number, Rect> | null;
  /** The new file's name; null derives it from what changed. */
  tag?: string | null;
}

/** One Save of the draft. */
export interface SaveBody {
  revision: string;
  site: unknown | null;
  text: string | null;
  calibration: CalibrationEdit | null;
}

/** What a Save makes of a calibration edit. */
export interface PlannedCalibration {
  id: string;
  id8: string;
  tag: string;
  source: string;
  source_tag: string;
  /** Nothing in the draft changes the file it starts from. */
  unchanged: boolean;
  /** A file already holding the result: nothing new is written. */
  existing: { id: string; id8: string; tag: string; path: string } | null;
  new: boolean;
  warnings: string[];
  reading: string;
  push: string;
}

/** What a Save would write, worked out and checked by the server. */
export interface SavePlan {
  text: string;
  site_changed: boolean;
  frame: string | null;
  from_frame: string;
  calibration: PlannedCalibration | null;
  /** This controller would switch to the result. */
  use: boolean;
}

/** What Save would write, without writing it; a refusal is an HttpError. */
export const planSave = (body: SaveBody) => json<SavePlan>("api/apply", post({ ...body, dry_run: true }));

/** One Save: the calibration the draft makes, site.toml, then this controller uses it. */
export const applySave = (body: SaveBody) =>
  json<SitePayload & { ok: boolean; steps: ApplyStep[]; calibration: PlannedCalibration | null }>("api/apply", post(body));

export interface Version {
  id: string;
  at: string;
  revision: string;
}

export const fetchHistory = () => json<Version[]>("api/history");
export const restoreVersion = (version: string, revision: string) =>
  json<SitePayload>("api/restore", post({ version, revision }));

/** Who gives the fix and the predicted error for `boxes`, the file's own when null. */
export function fetchCoverage(id: string, boxes: Record<number, Rect> | null, frame: MoveBody | null = null) {
  const query = [boxes ? `boxes=${encodeURIComponent(JSON.stringify(boxes))}` : "", frame ? `frame=${encodeURIComponent(JSON.stringify(frame))}` : ""].filter(Boolean).join("&");
  return json<Coverage>(`api/calibrations/${encodeURIComponent(id)}/coverage${query ? `?${query}` : ""}`);
}

/** Serve `spec` on the controller that opened the editor; `persist` also at
 * its next start. `expected` is what the page believes is served ("none" for
 * nothing): the controller refuses with 409 when that is no longer true. */
export const putServed = (spec: string, persist: boolean, expected?: string) =>
  json<EditorContext>("api/served", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ spec, persist, ...(expected !== undefined ? { expected } : {}) }) });

/** Rename a file's tag, or move it into or out of archived/. */
export const patchCalibration = (id: string, change: { tag?: string; archived?: boolean; force?: boolean }) =>
  json<{ id: string; id8: string; tag: string; path: string }>(`api/calibrations/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(change),
  });

export interface FrameRequest {
  calibration: string;
  /** The draft's site in the frame `start` leaves, and the file as loaded. */
  site: unknown;
  base: unknown;
  start: MoveBody | null;
  move: MoveBody;
  stations: Record<number, Rect> | null;
}

/** The draft after a move of the origin: everything renumbered so it stays where it is on the floor. */
export interface FrameMoved {
  frame: string;
  from_frame: string;
  site: EditorSite;
  base: EditorSite;
  stations: Record<number, Rect> | null;
  /** The calibration's own coverage, in the moved frame. */
  coverage: Record<number, Rect>;
  warnings: string[];
}

export type FrameAnswer = { ok: true; result: FrameMoved } | { ok: false; status: number; message: string; offer: { dx_mm: number; dy_mm: number } | null };

/** The draft as a move of the origin leaves it; nothing is written. A
 * refusal carries the largest legal shift when there is one. */
export async function postFrame(request: FrameRequest): Promise<FrameAnswer> {
  const response = await fetch("api/frame", post(request));
  const body = await response.json().catch(() => ({}));
  if (response.ok) return { ok: true, result: body as FrameMoved };
  const detail = body?.detail;
  if (detail && typeof detail === "object" && !Array.isArray(detail)) return { ok: false, status: response.status, message: String(detail.message), offer: detail.offer ?? null };
  return { ok: false, status: response.status, message: typeof detail === "string" ? detail : response.statusText, offer: null };
}

export interface AnchorFit {
  move: { theta_deg: number; pivot: [number, number]; dx_mm: number; dy_mm: number };
  residuals_mm: number[];
  worst_mm: number;
}
/** The move of the origin that lays tape-measured spots on the robots' reads; nothing is written. */
export const postAnchor = (spots: { at_mm: [number, number]; read_mm: [number, number] }[]) => json<AnchorFit>("api/anchor", post({ spots }));

export const fetchChecks = () => json<{ checks: import("./checks").CheckRecord[]; path: string }>("api/checks");
export const postCheck = (check: { calibration: string; mark_mm: [number, number]; measured_mm: [number, number]; robot: string; predicted_mm: number | null; assumed?: boolean; revision?: string }) =>
  json<import("./checks").CheckRecord>("api/checks", post(check));
export const fetchProvenance = () => json<{ lines: string[]; text: string }>("api/provenance");

export interface RestorePoint {
  id: string;
  name: string;
  at: string;
  served: string | null;
  revision: string;
}
export const fetchPoints = () => json<RestorePoint[]>("api/points");
export const savePoint = (name: string) => json<RestorePoint>("api/points", post({ name }));
export const restorePoint = (id: string, revision: string, serve: boolean) =>
  json<SitePayload & { steps: ApplyStep[] }>(`api/points/${encodeURIComponent(id)}/restore`, post({ revision, serve }));

export interface SiteRow {
  name: string;
  shown_path: string;
  current?: boolean;
  extent_mm?: [number, number] | null;
  anchor?: string;
  frame_id?: string;
  areas?: number;
  error?: string;
}

export interface SiteList {
  current: string;
  has_pack: boolean;
  /** Where a new site's folder goes */
  home: string;
  sites: SiteRow[];
}

export type NewSiteStart = "empty" | "size" | "spin";

export const fetchSites = () => json<SiteList>("api/sites");
export const createSite = (body: { name: string; note: string; start: NewSiteStart; size_mm?: [number, number] | null; calibration?: string | null; persist: boolean }) =>
  json<{ name: string; shown_path: string; calibration: string | null }>("api/sites", post({ ...body, use: true }));
export const switchSite = (name: string, persist: boolean) =>
  json<{ site: string; dropped: string | null }>("api/sites/current", { ...post({ name, persist }), method: "PUT" });

/** A calibration as the plan draws it, in its own frame. */
export interface CalibrationOverlay {
  id: string;
  id8: string;
  /** Solved in its own frame: a spin not yet placed in a room */
  free: boolean;
  coverage_union: [number, number, number, number];
  stations: { index: number; rect: Rect; circles: { name: string; x: number; y: number; radius_mm: number }[] }[];
  tag: string;
  site: string;
  frame_refusal: string | null;
}

export const fetchOverlay = (id: string) => json<CalibrationOverlay>(`api/calibrations/${encodeURIComponent(id)}`);
