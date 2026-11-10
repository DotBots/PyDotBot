import type { EditorContext, Library, SitePayload } from "./types";

// Every route is relative to the page: the controller serves the editor at
// /controller/site-editor/ and `dotbot site edit` at its own root.

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    let detail = response.statusText;
    try {
      detail = (await response.json()).detail ?? detail;
    } catch {
      // not JSON: the status text says enough
    }
    throw new Error(`${response.status}: ${detail}`);
  }
  return (await response.json()) as T;
}

export const fetchContext = () => json<EditorContext>("api/context");
export const fetchSite = () => json<SitePayload>("api/site");
export const fetchLibrary = () => json<Library>("api/calibrations?scope=site");
