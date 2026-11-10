import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../useFleet", () => {
  const fleet = { bots: [], site: null };
  return { useFleet: () => fleet };
});
vi.mock("../useOrchestration", () => {
  const orch = { act: () => {}, busy: null, outcome: null };
  return { useOrchestration: () => orch };
});

import { filtered, groupTitle } from "./library";
import { docFromSite } from "./model";
import { SiteEditorApp } from "./SiteEditorApp";
import type { Library, LibraryRow, Rect } from "./types";

const WHOLE: Rect = [0, 0, 1060, 1220];

const row = (id8: string, boxes: [Rect, Rect], extra: Partial<LibraryRow> = {}): LibraryRow => ({
  id: `${id8}00000000`,
  id8,
  tag: `tag-${id8}`,
  created_at: "2026-11-09T08:12:50Z",
  path: `/cal/calibration-${id8}.toml`,
  site: "inria-2lh",
  fence: WHOLE,
  spin: "2bab9ec3",
  tracks: 18,
  stations: boxes.map((box, index) => ({ index, residual_mm: 1.1, box, solved_from: "conics-joint" })),
  reading: index8Reading(boxes),
  in_frame: true,
  served: false,
  ...extra,
});

function index8Reading(boxes: [Rect, Rect]): string {
  return boxes[0].join() === boxes[1].join()
    ? "S0 and S1 share one box: the boxes do not decide"
    : "S0 x 0-630, y 0-1220 · S1 x 430-1060, y 0-1220 · S0/S1 handover x 530";
}

const served = row("4640cfde", [WHOLE, WHOLE], { served: true });
const handover = row("a1b41f12", [
  [0, 0, 630, 1220],
  [430, 0, 1060, 1220],
]);
const inFrame = [served, handover, ...["0ac36f3e", "991ec9c8", "b86304cc", "c9315b3f", "ff221900"].map((id) => row(id, [WHOLE, WHOLE]))];
const free = ["e06610ac", "80188d29", "cc82d16d", "0bf50aee", "6e13c58f"].map((id, i) =>
  row(id, [[0, 0, 619, 864], [0, 0, 619, 864]], { in_frame: false, spin: `free${i}`, fence: [0, 0, 619, 864] }),
);

const LIBRARY: Library = {
  site: "inria-2lh",
  served: served.id,
  serving: served,
  count: 12,
  groups: [{ spin: "2bab9ec3", created_at: "2026-11-09T08:12:50Z", rows: inFrame }],
  not_placed: free,
};

const CONTEXT = {
  mode: "controller",
  site: "inria-2lh",
  path: "/sites/inria-2lh/site.toml",
  served: {
    id: served.id,
    id8: "4640cfde",
    tag: "inria-hil-r3-inria-2lh",
    created_at: "2026-11-09T08:12:50Z",
    spec: "4640cfde",
    source: "the command line",
  },
  next_start: null,
  configured: null,
  controller: { version: "0.34.0", port: 8000 },
};

const SITE = {
  name: "inria-2lh",
  path: "/sites/inria-2lh/site.toml",
  revision: "r1",
  site: { anchor: "top-left", extent_mm: [1060, 1220] as [number, number], areas: [{ name: "field", x: 0, y: 0, w: 1060, h: 1220, role: "field" as const }] },
};

beforeEach(() => {
  window.localStorage.clear();
  Object.defineProperty(window, "innerWidth", { configurable: true, value: 1440 });
});
afterEach(() => vi.unstubAllGlobals());

const TEXT = 'anchor = "top-left"\nextent_mm = [1060, 1220]\n';

function stubFetch(overrides: Record<string, (init?: RequestInit) => Response> = {}) {
  const calls: { url: string; init?: RequestInit }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init });
      for (const [prefix, answer] of Object.entries(overrides)) if (url.startsWith(prefix)) return answer(init);
      const body = url.startsWith("api/context")
        ? CONTEXT
        : url.startsWith("api/site")
          ? { ...SITE, text: TEXT }
          : url.startsWith("api/preview")
            ? { text: TEXT + "\n[areas.pen]\n", changed: true }
            : LIBRARY;
      return new Response(JSON.stringify(body), { status: 200 });
    }),
  );
  return calls;
}

describe("the library", () => {
  it("titles a spin's group by its box layouts and searches the readings", () => {
    expect(groupTitle(LIBRARY.groups[0])).toBe("Measured 9 Nov 08:12 · 7 coverage layouts");
    const found = filtered(LIBRARY, "handover");
    expect(found.groups[0].rows.map((r) => r.id8)).toEqual(["a1b41f12"]);
    expect(found.not_placed).toEqual([]);
  });
});

describe("the editor page", () => {
  it("opens on the served calibration, lists one group of 7 and 5 free spins, and previews on click", async () => {
    stubFetch();
    render(<SiteEditorApp />);
    await waitFor(() => expect(screen.getByRole("tab", { name: /Calibrations/ })).toBeTruthy());
    fireEvent.click(screen.getByRole("tab", { name: /Calibrations/ }));
    await waitFor(() => expect(screen.getAllByTestId("library-group")).toHaveLength(1));
    expect(screen.getByTestId("library-group").textContent).toBe("Measured 9 Nov 08:12 · 7 coverage layouts");
    expect(screen.getByRole("tab", { name: "Not in this room yet 5" })).toBeTruthy();
    expect(screen.getByTestId("status-line").textContent).toContain("Using inria-hil-r3-inria-2lh");
    expect(screen.getByTestId("serving-card").textContent).toContain("from its command line");
    fireEvent.click(screen.getByTestId("library-row-a1b41f12"));
    expect(screen.getByTestId("status-side").textContent).toContain("looking at tag-a1b41f12");
    expect(screen.getByTestId("status-line").textContent).toContain("Using inria-hil-r3-inria-2lh");
    fireEvent.click(screen.getByLabelText("Back to the calibration in use"));
    expect(screen.queryByTestId("status-side")).toBeNull();
    fireEvent.click(screen.getByRole("tab", { name: "Not in this room yet 5" }));
    expect(screen.getByTestId("library-not-placed").textContent).toContain("5 spins");
  });
});


const keyDown = (key: string, extra: Partial<KeyboardEventInit> = {}) =>
  fireEvent.keyDown(window, { key, ...extra });

describe("the editor shell", () => {
  it("switches kinds by number, leaves R unbound, and goes back to View on Esc", async () => {
    stubFetch();
    render(<SiteEditorApp />);
    await waitFor(() => expect(screen.getByTestId("plan")).toBeTruthy());
    const kindTab = (name: RegExp) => screen.getByRole("tab", { name });
    keyDown("2");
    expect(kindTab(/^Areas/).getAttribute("aria-selected")).toBe("true");
    keyDown("r");
    expect(kindTab(/^Areas/).getAttribute("aria-selected")).toBe("true");
    keyDown("Escape");
    expect(kindTab(/^View/).getAttribute("aria-selected")).toBe("true");
  });

  it("brings an unsaved draft back on reload, and says it is kept in this browser", async () => {
    stubFetch();
    const first = render(<SiteEditorApp />);
    await waitFor(() => expect(screen.getByTestId("area-field")).toBeTruthy());
    // Rename the field from the inspector
    fireEvent.click(screen.getByRole("tab", { name: "Outline" }));
    fireEvent.click(screen.getByTestId("outline-area:field"));
    const name = screen.getByLabelText("Name");
    fireEvent.change(name, { target: { value: "arena" } });
    fireEvent.keyDown(name, { key: "Enter" });
    await waitFor(() => expect(screen.getByTestId("unsaved").textContent).toContain("1 unsaved, kept in this browser"));
    first.unmount();
    render(<SiteEditorApp />);
    await waitFor(() => expect(screen.getByTestId("area-arena")).toBeTruthy());
    expect(screen.getByTestId("notice").textContent).toContain("restored from this browser");
  });

  it("reviews with a diff and saves through one ordered route", async () => {
    const calls = stubFetch({
      "api/apply": () =>
        new Response(
          JSON.stringify({ ...SITE, revision: "r2", text: TEXT, ok: true, steps: [{ step: "site.toml", status: "written", detail: SITE.path }] }),
          { status: 200 },
        ),
    });
    render(<SiteEditorApp />);
    await waitFor(() => expect(screen.getByTestId("area-field")).toBeTruthy());
    fireEvent.click(screen.getByRole("tab", { name: "Outline" }));
    fireEvent.click(screen.getByTestId("outline-area:field"));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "arena" } });
    fireEvent.keyDown(screen.getByLabelText("Name"), { key: "Enter" });
    keyDown("s", { ctrlKey: true });
    await waitFor(() => expect(screen.getByTestId("review-diff").textContent).toContain("+[areas.pen]"));
    expect(screen.getByTestId("review").textContent).toContain("Saving never touches robots");
    fireEvent.click(screen.getByTestId("review-save"));
    await waitFor(() => expect(screen.getByTestId("review-result").textContent).toContain("written"));
    const apply = calls.find((c) => c.url === "api/apply")!;
    expect(JSON.parse(apply.init!.body as string).revision).toBe("r1");
    expect(screen.getByTestId("unsaved").textContent).toBe("saved");
  });

  it("re-applies the draft when the save meets a changed file", async () => {
    let siteCalls = 0;
    stubFetch({
      "api/apply": () => new Response(JSON.stringify({ detail: "changed on disk" }), { status: 409 }),
      "api/site": () => {
        siteCalls += 1;
        const revision = siteCalls === 1 ? "r1" : "r2";
        return new Response(JSON.stringify({ ...SITE, revision, text: TEXT }), { status: 200 });
      },
    });
    render(<SiteEditorApp />);
    await waitFor(() => expect(screen.getByTestId("area-field")).toBeTruthy());
    fireEvent.click(screen.getByRole("tab", { name: "Outline" }));
    fireEvent.click(screen.getByTestId("outline-area:field"));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "arena" } });
    fireEvent.keyDown(screen.getByLabelText("Name"), { key: "Enter" });
    keyDown("s", { metaKey: true });
    await waitFor(() => expect(screen.getByTestId("review-save")).toBeTruthy());
    fireEvent.click(screen.getByTestId("review-save"));
    await waitFor(() => expect(screen.getByTestId("review-error").textContent).toContain("re-applied your draft"));
    expect(siteCalls).toBe(2);
    expect(screen.getByTestId("unsaved").textContent).toContain("1 unsaved");
  });
});

describe("capturing zero", () => {
  it("leaves no dead end with nothing served: the capture panel names the step that serves one", async () => {
    stubFetch({
      "api/context": () => new Response(JSON.stringify({ ...CONTEXT, served: null }), { status: 200 }),
      "api/calibrations": () => new Response(JSON.stringify({ ...LIBRARY, served: null, serving: null, groups: [{ ...LIBRARY.groups[0], rows: inFrame.map((r) => ({ ...r, served: false })) }] }), { status: 200 }),
    });
    render(<SiteEditorApp />);
    await waitFor(() => expect(screen.getByTestId("goal-calibration").textContent).toContain("none in use"));
    expect(screen.getByTestId("goal-origin").textContent).toContain("Describe…");
    expect(screen.queryByTestId("goal-stations")).toBeNull();
    keyDown("1");
    keyDown("c");
    await waitFor(() => expect(screen.getByTestId("frame-serve-step").textContent).toBe("Choose…"));
    fireEvent.click(screen.getByTestId("frame-serve-step"));
    expect(screen.getByRole("tab", { name: /Calibrations/ }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getByTestId("library-serve-hint").textContent).toContain("Use this…");
  });

  it("shows the capture panel even when the new room sheet was open", async () => {
    stubFetch();
    render(<SiteEditorApp />);
    await waitFor(() => expect(screen.getByTestId("plan")).toBeTruthy());
    fireEvent.click(screen.getByLabelText("More"));
    fireEvent.click(screen.getByRole("menuitem", { name: /Set up a room/ }));
    expect(screen.getByTestId("new-room")).toBeTruthy();
    keyDown("1");
    keyDown("c");
    await waitFor(() => expect(screen.getByTestId("frame-capture")).toBeTruthy());
    expect(screen.queryByTestId("new-room")).toBeNull();
  });
});

describe("keeping the operator's work", () => {
  const edit = async () => {
    await waitFor(() => expect(screen.getByTestId("area-field")).toBeTruthy());
    fireEvent.click(screen.getByRole("tab", { name: "Outline" }));
    fireEvent.click(screen.getByTestId("outline-area:field"));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "arena" } });
    fireEvent.keyDown(screen.getByLabelText("Name"), { key: "Enter" });
    await waitFor(() => expect(screen.getByTestId("unsaved").textContent).toContain("1 unsaved"));
  };

  it("discards every unsaved change on request, here and in this browser", async () => {
    stubFetch();
    render(<SiteEditorApp />);
    await edit();
    fireEvent.click(screen.getByLabelText("More"));
    fireEvent.click(screen.getByTestId("discard-all"));
    await waitFor(() => expect(screen.getByTestId("unsaved").textContent).toBe("saved"));
    expect(window.localStorage.getItem("dotbot.siteEditor.draft.inria-2lh")).toBeNull();
  });

  it("keeps text edits that cannot follow a changed file, for copying", async () => {
    window.localStorage.setItem(
      "dotbot.siteEditor.draft.inria-2lh",
      JSON.stringify({ revision: "r0", calibration: null, base: docFromSite(SITE.site), doc: docFromSite(SITE.site), text: "# my hand edit\n" + TEXT, boxes: null }),
    );
    stubFetch();
    render(<SiteEditorApp />);
    await waitFor(() => expect(screen.getByTestId("notice").textContent).toContain("copy them from here"));
    expect(screen.getByTestId("notice-copy-lost")).toBeTruthy();
  });

  it("names what depends on a file before archiving it, and archives anyway on request", async () => {
    const calls = stubFetch({
      "api/calibrations/a1b41f1200000000": (init) => {
        const body = JSON.parse((init?.body as string) ?? "{}");
        if (init?.method === "PATCH" && !body.force)
          return new Response(JSON.stringify({ detail: { message: "a1b41f12 is named for the next start: a1b41f12 in dotbot.local.toml", dependents: ["named for the next start: a1b41f12 in dotbot.local.toml"] } }), { status: 409 });
        return new Response(JSON.stringify({ id: handover.id, id8: "a1b41f12", tag: "t", path: "/x" }), { status: 200 });
      },
    });
    render(<SiteEditorApp />);
    await waitFor(() => expect(screen.getByRole("tab", { name: /Calibrations/ })).toBeTruthy());
    fireEvent.click(screen.getByRole("tab", { name: /Calibrations/ }));
    await waitFor(() => expect(screen.getByTestId("library-row-a1b41f12")).toBeTruthy());
    fireEvent.click(screen.getByLabelText("Actions for tag-a1b41f12"));
    fireEvent.click(screen.getByRole("menuitem", { name: "Archive" }));
    await waitFor(() => expect(screen.getByTestId("notice").textContent).toContain("named for the next start"));
    fireEvent.click(screen.getByTestId("notice-act"));
    await waitFor(() => expect(screen.getByTestId("toast").textContent).toContain("Archived tag-a1b41f12"));
    const forced = calls.filter((c) => c.init?.method === "PATCH").map((c) => JSON.parse(c.init!.body as string).force);
    expect(forced).toEqual([false, true]);
  });

  it("lists the files this build cannot read instead of saying there are none", async () => {
    stubFetch({
      "api/calibrations?": () =>
        new Response(JSON.stringify({ ...LIBRARY, count: 0, groups: [], not_placed: [], serving: null, served: null, unreadable: [{ path: "/cal/old.toml", name: "old.toml", schema: 2, error: "unsupported schema_version 2" }] }), { status: 200 }),
    });
    render(<SiteEditorApp />);
    await waitFor(() => expect(screen.getByRole("tab", { name: /Calibrations/ })).toBeTruthy());
    fireEvent.click(screen.getByRole("tab", { name: /Calibrations/ }));
    await waitFor(() => expect(screen.getByTestId("library-unreadable")).toBeTruthy());
    expect(screen.getByTestId("library").textContent).toContain("1 older file, none this build reads");
    expect(screen.getByTestId("library").textContent).toContain("old.toml");
  });

  it("restores a kept version of the room file from the Snapshots section", async () => {
    const calls = stubFetch({
      "api/history": () => new Response(JSON.stringify([{ id: "v1", at: "2026-11-10T09:00:00Z", revision: "r0" }]), { status: 200 }),
      "api/restore": () => new Response(JSON.stringify({ ...SITE, revision: "r0", text: TEXT, restored: "v1" }), { status: 200 }),
    });
    render(<SiteEditorApp />);
    await waitFor(() => expect(screen.getByTestId("versions")).toBeTruthy());
    const restore = screen.getByRole("button", { name: "Restore…" });
    fireEvent.click(restore);
    fireEvent.click(screen.getByRole("button", { name: "Restore now" }));
    await waitFor(() => expect(screen.getByTestId("toast").textContent).toContain("back as kept at 2026-11-10 09:00"));
    expect(JSON.parse(calls.find((c) => c.url === "api/restore")!.init!.body as string)).toEqual({ version: "v1", revision: "r1" });
  });
});

describe("the room view", () => {
  it("draws the stations above the floor, the coverage and the robots, and opens Present on it", async () => {
    const geometry = { stations: { "0": { x_mm: -542, y_mm: 1268, height_mm: 2423, off_square_deg: 5.4 }, "1": { x_mm: 1387, y_mm: -245, height_mm: 1606, off_square_deg: -3.1 } }, apart_mm: { "0-1": 2583 } };
    const withGeometry = { ...LIBRARY, serving: { ...served, geometry }, groups: [{ ...LIBRARY.groups[0], rows: inFrame.map((r) => (r.id === served.id ? { ...r, geometry } : r)) }] };
    stubFetch({ "api/calibrations?": () => new Response(JSON.stringify(withGeometry), { status: 200 }) });
    render(<SiteEditorApp />);
    await waitFor(() => expect(screen.getByTestId("plan")).toBeTruthy());
    fireEvent.click(screen.getByRole("tab", { name: "Room" }));
    await waitFor(() => expect(screen.getByTestId("room-view")).toBeTruthy());
    expect(screen.getByTestId("room-station-0").textContent).toContain("S0 · channel 1");
    expect(screen.getByTestId("room-station-0").textContent).toContain("2.4 m up");
    expect(screen.getAllByTestId(/room-cover-/)).toHaveLength(2);
    expect(screen.getByTestId("room-legend").textContent).toContain("both cover the whole floor, no handover");
    fireEvent.click(screen.getByRole("tab", { name: "Plan" }));
    await waitFor(() => expect(screen.getByTestId("plan")).toBeTruthy());
    fireEvent.click(screen.getByLabelText("More"));
    fireEvent.click(screen.getByRole("menuitem", { name: /Present/ }));
    await waitFor(() => expect(screen.getByTestId("presbar")).toBeTruthy());
    expect(screen.getByTestId("room-view")).toBeTruthy();
    keyDown("Escape");
    await waitFor(() => expect(screen.getByTestId("plan")).toBeTruthy());
  });
});

describe("the Use sheet", () => {
  it("switches with the id it believes is in use, and shows the controller's answer when that is stale", async () => {
    let attempts = 0;
    const calls = stubFetch({
      "api/served": () => {
        attempts += 1;
        if (attempts === 1)
          return new Response(JSON.stringify({ detail: { message: "the controller now uses 0ac36f3e, not 4640cfde: look again before switching", served: null } }), { status: 409 });
        return new Response(JSON.stringify({ ...CONTEXT, served: { ...CONTEXT.served, id: handover.id, id8: "a1b41f12", tag: handover.tag, source: "the site editor, for this run" } }), { status: 200 });
      },
    });
    render(<SiteEditorApp />);
    await waitFor(() => expect(screen.getByRole("tab", { name: /Calibrations/ })).toBeTruthy());
    fireEvent.click(screen.getByRole("tab", { name: /Calibrations/ }));
    await waitFor(() => expect(screen.getByTestId("library-row-a1b41f12")).toBeTruthy());
    fireEvent.click(screen.getByTestId("library-row-a1b41f12"));
    fireEvent.click(screen.getByTestId("status-use"));
    await waitFor(() => expect(screen.getByTestId("serve-sheet")).toBeTruthy());
    expect(screen.getByTestId("serve-sheet").textContent).toContain("Use tag-a1b41f12?");
    fireEvent.click(screen.getByTestId("serve-confirm"));
    await waitFor(() => expect(screen.getByTestId("serve-conflict").textContent).toContain("now uses 0ac36f3e"));
    fireEvent.click(screen.getByTestId("serve-confirm"));
    await waitFor(() => expect(screen.getByTestId("serve-result").textContent).toContain("Now using tag-a1b41f12"));
    const bodies = calls.filter((c) => c.url === "api/served").map((c) => JSON.parse(c.init!.body as string));
    expect(bodies[0]).toEqual({ spec: handover.id, persist: false, expected: served.id });
    expect(screen.getByTestId("status-line").textContent).toContain("Using tag-a1b41f12");
  });
});

describe("the frame tools", () => {
  it("drops the turn's ghost when the tool changes", async () => {
    stubFetch({ "api/frame": () => new Response(JSON.stringify({ frame: "f2", from_frame: "f1", calibration: { id: "x", id8: "x", tag: "" }, source: "", warnings: [], push: "", steps: [] }), { status: 200 }) });
    render(<SiteEditorApp />);
    await waitFor(() => expect(screen.getByTestId("plan")).toBeTruthy());
    keyDown("1");
    keyDown("t");
    const turn = screen.getByLabelText("turn");
    fireEvent.change(turn, { target: { value: "5" } });
    fireEvent.keyDown(turn, { key: "Enter" });
    await waitFor(() => expect(screen.getByTestId("frame-ghost")).toBeTruthy());
    keyDown("c");
    await waitFor(() => expect(screen.queryByTestId("frame-ghost")).toBeNull());
  });
});

describe("the collapse order", () => {
  it("folds the left pane into a rail below 1100 px and the right one below 980 px", async () => {
    stubFetch();
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 1024 });
    const { unmount } = render(<SiteEditorApp />);
    await waitFor(() => expect(screen.getByTestId("plan")).toBeTruthy());
    expect(screen.getByTestId("rail-left")).toBeTruthy();
    expect(screen.getByTestId("pane-right")).toBeTruthy();
    // The status line's name and Save stay
    expect(screen.getByTestId("status-line").textContent).toContain("inria-hil-r3-inria-2lh");
    expect(screen.getByTestId("save")).toBeTruthy();
    unmount();
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 960 });
    render(<SiteEditorApp />);
    await waitFor(() => expect(screen.getByTestId("rail-right")).toBeTruthy());
    fireEvent.click(screen.getByLabelText("Inspect"));
    expect(screen.getByTestId("drawer-right")).toBeTruthy();
  });
});
