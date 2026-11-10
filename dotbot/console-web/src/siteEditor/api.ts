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
  step: "site.toml" | "calibration";
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

/** Serve `spec` on the controller that opened the editor; `persist` also at its next start. */
export const putServed = (spec: string, persist: boolean) =>
  json<EditorContext>("api/served", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ spec, persist }) });

/** Rename a file's tag, or move it into or out of archived/. */
export const patchCalibration = (id: string, change: { tag?: string; archived?: boolean }) =>
  json<{ id: string; id8: string; tag: string; path: string }>(`api/calibrations/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(change),
  });
