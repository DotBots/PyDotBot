import type { Rigid2D } from "./rigid";
import type {
  Backdrops,
  CalibrationListing,
  CalibrationOverlay,
  PlacedCalibration,
  SiteModel,
  SiteResponse,
} from "./types";

// The editor's server: relative to the page by default, so it works wherever
// it is mounted, or under `base` (ending in "/") when embedded elsewhere.

export class StaleSiteError extends Error {}
export class RefusedSiteError extends Error {}

async function detail(res: Response): Promise<string> {
  try {
    const body = await res.json();
    return typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
  } catch {
    return `${res.status} ${res.statusText}`;
  }
}

/** Areas as the server takes them, each with the name the file knows it by. */
function outgoing(site: SiteModel) {
  return {
    anchor: site.anchor || null,
    extent_mm: site.extent_mm,
    areas: site.areas.map((a) => ({ ...a, comment: a.comment || null })),
    walls: (site.walls ?? []).map((b) => ({ ...b, name: b.name || null, comment: b.comment || null })),
    obstacles: (site.obstacles ?? []).map((b) => ({ ...b, name: b.name || null, comment: b.comment || null })),
    objects: (site.objects ?? []).map((o) => ({ ...o, comment: o.comment || null })),
  };
}

/** The loaded site, with each area's `was` set to its name in the file. */
export function withOrigins(body: SiteResponse): SiteResponse {
  return {
    ...body,
    site: {
      ...body.site,
      areas: body.site.areas.map((a) => ({ ...a, was: a.name })),
      walls: (body.site.walls ?? []).map((b, i) => ({ ...b, was: i })),
      obstacles: (body.site.obstacles ?? []).map((b, i) => ({ ...b, was: i })),
      objects: (body.site.objects ?? []).map((o) => ({ ...o, was: o.name })),
    },
  };
}

export async function fetchSite(base = ""): Promise<SiteResponse> {
  const res = await fetch(`${base}api/site`);
  if (!res.ok) throw new Error(await detail(res));
  return withOrigins(await res.json());
}

export async function previewSite(site: SiteModel, base = ""): Promise<{ text: string; changed: boolean }> {
  const res = await fetch(`${base}api/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(outgoing(site)),
  });
  if (res.status === 422) throw new RefusedSiteError(await detail(res));
  if (!res.ok) throw new Error(await detail(res));
  return res.json();
}

/**
 * Save `site` over the file revision the page loaded. A file changed on disk
 * since throws StaleSiteError; one the schema refuses throws RefusedSiteError.
 */
export async function saveSite(revision: string, site: SiteModel, base = ""): Promise<SiteResponse> {
  const res = await fetch(`${base}api/site`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ revision, site: outgoing(site) }),
  });
  if (res.status === 409) throw new StaleSiteError(await detail(res));
  if (res.status === 422) throw new RefusedSiteError(await detail(res));
  if (!res.ok) throw new Error(await detail(res));
  return withOrigins(await res.json());
}

export async function stopEditor(base = ""): Promise<void> {
  await fetch(`${base}api/done`, { method: "POST" });
}

export async function fetchCalibrations(base = ""): Promise<CalibrationListing[]> {
  const res = await fetch(`${base}api/calibrations`);
  if (!res.ok) throw new Error(await detail(res));
  return res.json();
}

export async function fetchCalibration(spec: string, base = ""): Promise<CalibrationOverlay> {
  const res = await fetch(`${base}api/calibrations/${encodeURIComponent(spec)}`);
  if (!res.ok) throw new Error(await detail(res));
  return res.json();
}

/** Save `calibration` moved by `move` as a new calibration of this site. */
export async function placeCalibration(
  id: string,
  move: Rigid2D,
  reanchor: boolean,
  base = "",
): Promise<PlacedCalibration> {
  const res = await fetch(`${base}api/calibrations/${encodeURIComponent(id)}/place`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...move, reanchor }),
  });
  if (res.status === 422) throw new RefusedSiteError(await detail(res));
  if (!res.ok) throw new Error(await detail(res));
  return res.json();
}

export async function fetchBackdrops(base = ""): Promise<Backdrops> {
  const res = await fetch(`${base}api/backdrops`);
  if (!res.ok) throw new Error(await detail(res));
  return res.json();
}
