import { afterEach, describe, expect, it, vi } from "vitest";

import { RefusedSiteError, StaleSiteError, fetchSite, saveSite } from "./api";
import type { SiteModel } from "./types";

const site: SiteModel = {
  anchor: "a",
  extent_mm: [1000, 1000],
  areas: [{ name: "field", x: 0, y: 0, w: 500, h: 500, role: null, comment: "", was: "field" }],
};

function reply(status: number, body: unknown) {
  return vi.fn().mockResolvedValue(
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("site editor api", () => {
  it("marks each loaded area with its name in the file", async () => {
    vi.stubGlobal("fetch", reply(200, { name: "s", path: "p", revision: "r", calibrations: [], site }));
    const body = await fetchSite();
    expect(body.site.areas[0].was).toBe("field");
  });

  it("sends the revision the page loaded, and an empty comment as none", async () => {
    const fetch = reply(200, { name: "s", path: "p", revision: "r2", calibrations: [], site, written: true });
    vi.stubGlobal("fetch", fetch);
    await saveSite("r1", site);
    const [, init] = fetch.mock.calls[0];
    const sent = JSON.parse(init.body);
    expect(init.method).toBe("PUT");
    expect(sent.revision).toBe("r1");
    expect(sent.site.areas[0].comment).toBeNull();
  });

  it("tells a stale save from a refused one", async () => {
    vi.stubGlobal("fetch", reply(409, { detail: "changed on disk" }));
    await expect(saveSite("r1", site)).rejects.toBeInstanceOf(StaleSiteError);
    vi.stubGlobal("fetch", reply(422, { detail: "at most one field" }));
    await expect(saveSite("r1", site)).rejects.toThrow(RefusedSiteError);
  });
});
