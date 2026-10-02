import type { SiteModel, SiteResponse } from "./types";

// The editor's server, relative to the page so it works wherever it is mounted.

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
  };
}

/** The loaded site, with each area's `was` set to its name in the file. */
export function withOrigins(body: SiteResponse): SiteResponse {
  return {
    ...body,
    site: { ...body.site, areas: body.site.areas.map((a) => ({ ...a, was: a.name })) },
  };
}

export async function fetchSite(): Promise<SiteResponse> {
  const res = await fetch("api/site");
  if (!res.ok) throw new Error(await detail(res));
  return withOrigins(await res.json());
}

export async function previewSite(site: SiteModel): Promise<{ text: string; changed: boolean }> {
  const res = await fetch("api/preview", {
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
export async function saveSite(revision: string, site: SiteModel): Promise<SiteResponse> {
  const res = await fetch("api/site", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ revision, site: outgoing(site) }),
  });
  if (res.status === 409) throw new StaleSiteError(await detail(res));
  if (res.status === 422) throw new RefusedSiteError(await detail(res));
  if (!res.ok) throw new Error(await detail(res));
  return withOrigins(await res.json());
}

export async function stopEditor(): Promise<void> {
  await fetch("api/done", { method: "POST" });
}
