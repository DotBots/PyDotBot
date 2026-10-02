// The site editor as a console panel: the controller serves the editor's
// routes over its own site pack, to a browser on the same machine.

export const SITE_EDITOR_BASE = "/controller/site-editor/";

/** Whether the controller lets this browser edit its site: a pack, on this machine. */
export async function siteEditable(): Promise<boolean> {
  try {
    const res = await fetch(`${SITE_EDITOR_BASE}api/site`);
    return res.ok;
  } catch {
    return false;
  }
}
