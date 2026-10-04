import { afterEach, describe, expect, it, vi } from "vitest";

import { siteEditable } from "./siteEditorPanel";

afterEach(() => vi.unstubAllGlobals());

describe("siteEditable", () => {
  it.each([
    [200, true],
    [403, false],
    [404, false],
  ])("takes a %i from the editor's routes as %s", async (status, editable) => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status })));
    expect(await siteEditable()).toBe(editable);
  });

  it("takes an unreachable controller as not editable", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new Error("down"))));
    expect(await siteEditable()).toBe(false);
  });
});
