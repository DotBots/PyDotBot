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
  step: "site.toml" | "calibration" | "serve";
  status: "written" | "unchanged" | "refused";
  detail: string;
  revision?: string;
  id?: string;
  push?: string;
  warnings?: string[];
}

export const applySave = (
  revision: string,
  site: unknown,
  text: string | null = null,
  boxes: { of: string; stations: Record<number, Rect>; tag: string | null } | null = null,
) =>
  json<SitePayload & { ok: boolean; steps: ApplyStep[] }>(
    "api/apply",
    post({ revision, site, text, ...(boxes ? { boxes_of: boxes.of, boxes: { stations: boxes.stations, tag: boxes.tag } } : {}) }),
  );

export interface Version {
  id: string;
  at: string;
  revision: string;
}

export const fetchHistory = () => json<Version[]>("api/history");
export const restoreVersion = (version: string, revision: string) =>
  json<SitePayload>("api/restore", post({ version, revision }));

/** Who gives the fix and the predicted error for `boxes`, the file's own when null. */
export const fetchCoverage = (id: string, boxes: Record<number, Rect> | null) =>
  json<Coverage>(`api/calibrations/${encodeURIComponent(id)}/coverage${boxes ? `?boxes=${encodeURIComponent(JSON.stringify(boxes))}` : ""}`);

export interface DryRun {
  id: string;
  id8: string;
  source: string;
  written: false;
  existing: { id: string; id8: string; tag: string; path: string } | null;
  reading: string;
}

/** What saving `id` with `boxes` would write, without writing it. */
export const dryRunBoxes = (id: string, boxes: Record<number, Rect>, revision: string, tag: string | null) =>
  json<DryRun>(`api/calibrations/${encodeURIComponent(id)}/boxes?dry_run=1`, post({ stations: boxes, revision, tag }));

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
  theta_deg: number;
  pivot: [number, number];
  dx_mm: number;
  dy_mm: number;
  note: string | null;
  revision: string;
  serve: boolean;
  dry_run: boolean;
}

export interface FrameResult {
  frame: string;
  from_frame: string;
  calibration: { id: string; id8: string; tag: string };
  source: string;
  warnings: string[];
  push: string;
  steps: ApplyStep[];
  ok?: boolean;
}

export type FrameAnswer = { ok: true; result: FrameResult } | { ok: false; status: number; message: string; offer: { dx_mm: number; dy_mm: number } | null };

/** A frame change, or what it would do with `dry_run`; a refusal carries the
 * largest legal shift when there is one. */
export async function postFrame(request: FrameRequest): Promise<FrameAnswer> {
  const response = await fetch("api/frame", post(request));
  const body = await response.json().catch(() => ({}));
  if (response.ok) return { ok: true, result: body as FrameResult };
  const detail = body?.detail;
  if (detail && typeof detail === "object" && !Array.isArray(detail)) return { ok: false, status: response.status, message: String(detail.message), offer: detail.offer ?? null };
  return { ok: false, status: response.status, message: typeof detail === "string" ? detail : response.statusText, offer: null };
}

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
  fence: [number, number, number, number];
  stations: { index: number; rect: Rect; circles: { name: string; x: number; y: number; radius_mm: number }[] }[];
  tag: string;
  site: string;
  frame_refusal: string | null;
}

export const fetchOverlay = (id: string) => json<CalibrationOverlay>(`api/calibrations/${encodeURIComponent(id)}`);
/** Move a spin into this site by a turn and a shift; writes a new file. */
export const placeCalibration = (id: string, move: { theta_deg: number; dx: number; dy: number }) =>
  json<{ id: string; id8: string; source: string; path: string; push: string; warnings: string[] }>(
    `api/calibrations/${encodeURIComponent(id)}/place`,
    post({ theta_deg: move.theta_deg, dx_mm: move.dx, dy_mm: move.dy }),
  );
