import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const fleet = vi.hoisted(() => ({ bots: [] as unknown[], site: null }));
vi.mock("../useFleet", () => ({ useFleet: () => fleet }));
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
  coverage_union: WHOLE,
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
    ? "S0 and S1 share one coverage: the coverages do not decide"
    : "S0 x 0-630, y 0-1220 · S1 x 430-1060, y 0-1220 · S0/S1 handover x 530";
}

const served = row("4640cfde", [WHOLE, WHOLE], { served: true });
const handover = row("a1b41f12", [
  [0, 0, 630, 1220],
  [430, 0, 1060, 1220],
]);
const inFrame = [served, handover, ...["0ac36f3e", "991ec9c8", "b86304cc", "c9315b3f", "ff221900"].map((id) => row(id, [WHOLE, WHOLE]))];
const free = ["e06610ac", "80188d29", "cc82d16d", "0bf50aee", "6e13c58f"].map((id, i) =>
  row(id, [[0, 0, 619, 864], [0, 0, 619, 864]], { in_frame: false, spin: `free${i}`, coverage_union: [0, 0, 619, 864] }),
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
  fleet.bots = [];
  window.localStorage.clear();
  Object.defineProperty(window, "innerWidth", { configurable: true, value: 1440 });
  // Reduced motion: the camera turns at once, so a test waits on no animation
  vi.stubGlobal("matchMedia", (q: string) => ({ matches: q.includes("reduce"), media: q, addEventListener: () => {}, removeEventListener: () => {} }));
});
afterEach(() => vi.unstubAllGlobals());

const TEXT = 'anchor = "top-left"\nextent_mm = [1060, 1220]\n';

const PLAN = { text: TEXT + "\n[areas.pen]\n", site_changed: true, frame: null, from_frame: "f0237ffd", calibration: null, use: false };

function stubFetch(overrides: Record<string, (init?: RequestInit) => Response> = {}) {
  const calls: { url: string; init?: RequestInit }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init });
      // A dry run of the Save is answered apart, as "dry:api/apply"
      const dry = url === "api/apply" && !!JSON.parse((init?.body as string) ?? "{}").dry_run;
      if (dry) return (overrides["dry:api/apply"] ?? (() => new Response(JSON.stringify(PLAN), { status: 200 })))(init);
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
    expect(screen.getByRole("tab", { name: "Not placed in this site yet 5" })).toBeTruthy();
    expect(screen.getByTestId("status-line").textContent).toContain("Using inria-hil-r3-inria-2lh");
    expect(screen.getByTestId("serving-card").textContent).toContain("from its command line");
    fireEvent.click(screen.getByTestId("library-row-a1b41f12"));
    expect(screen.getByTestId("status-side").textContent).toContain("looking at tag-a1b41f12");
    expect(screen.getByTestId("status-line").textContent).toContain("Using inria-hil-r3-inria-2lh");
    fireEvent.click(screen.getByLabelText("Back to the calibration in use"));
    expect(screen.queryByTestId("status-side")).toBeNull();
    fireEvent.click(screen.getByRole("tab", { name: "Not placed in this site yet 5" }));
    expect(screen.getByTestId("library-not-placed").textContent).toContain("5 spins");
  });
});


/** Into the top-down edit, from the 3D view the page opens on. */
async function toPlan() {
  fireEvent.click(await screen.findByTestId("enter-edit"));
  await waitFor(() => expect(screen.getByTestId("plan")).toBeTruthy());
}

const keyDown = (key: string, extra: Partial<KeyboardEventInit> = {}) =>
  fireEvent.keyDown(window, { key, ...extra });

describe("the editor shell", () => {
  it("switches kinds by number, leaves R unbound, and goes back to View on Esc", async () => {
    stubFetch();
    render(<SiteEditorApp />);
    await toPlan();
    const kindTab = (name: RegExp) => screen.getByRole("tab", { name });
    keyDown("4");
    expect(kindTab(/^Areas/).getAttribute("aria-selected")).toBe("true");
    keyDown("r");
    expect(kindTab(/^Areas/).getAttribute("aria-selected")).toBe("true");
    keyDown("Escape");
    expect(kindTab(/^View/).getAttribute("aria-selected")).toBe("true");
  });

  it("brings an unsaved draft back on reload, and says it is kept in this browser", async () => {
    stubFetch();
    const first = render(<SiteEditorApp />);
    await toPlan();
    // Rename the field from the inspector
    fireEvent.click(screen.getByRole("tab", { name: "Outline" }));
    fireEvent.click(screen.getByTestId("outline-area:field"));
    const name = screen.getByLabelText("Name");
    fireEvent.change(name, { target: { value: "arena" } });
    fireEvent.keyDown(name, { key: "Enter" });
    await waitFor(() => expect(screen.getByTestId("unsaved").textContent).toContain("1 unsaved, kept in this browser"));
    first.unmount();
    render(<SiteEditorApp />);
    await toPlan();
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
    await toPlan();
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
    await toPlan();
    fireEvent.click(screen.getByRole("tab", { name: "Outline" }));
    fireEvent.click(screen.getByTestId("outline-area:field"));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "arena" } });
    fireEvent.keyDown(screen.getByLabelText("Name"), { key: "Enter" });
    keyDown("s", { metaKey: true });
    // Save waits for the server's plan of what it writes
    await waitFor(() => expect((screen.getByTestId("review-save") as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByTestId("review-save"));
    await waitFor(() => expect(screen.getByTestId("review-error").textContent).toContain("re-applied your draft"));
    expect(siteCalls).toBe(2);
    expect(screen.getByTestId("unsaved").textContent).toContain("1 unsaved");
  });
});

describe("the anchor flow from the page", () => {
  it("leaves no dead end with nothing served: the Anchor kind names the step that serves one", async () => {
    stubFetch({
      "api/context": () => new Response(JSON.stringify({ ...CONTEXT, served: null }), { status: 200 }),
      "api/calibrations": () => new Response(JSON.stringify({ ...LIBRARY, served: null, serving: null, groups: [{ ...LIBRARY.groups[0], rows: inFrame.map((r) => ({ ...r, served: false })) }] }), { status: 200 }),
    });
    render(<SiteEditorApp />);
    await waitFor(() => expect(screen.getByTestId("goal-stations").textContent).toContain("none in use"));
    expect(screen.getByTestId("goal-anchor").textContent).toContain("once a calibration is in use");
    expect(screen.queryByTestId("act-anchor")).toBeNull();
    keyDown("3");
    keyDown("a");
    await waitFor(() => expect(screen.getByTestId("anchor-unserved")).toBeTruthy());
    expect(screen.getByTestId("anchor-serve-step").textContent).toBe("Choose one");
    fireEvent.click(screen.getByTestId("anchor-serve-step"));
    expect(screen.getByRole("tab", { name: /Calibrations/ }).getAttribute("aria-selected")).toBe("true");
  });

  it("opens from the Anchor row's button, closing the new room steps", async () => {
    fleet.bots = [holding("DE00000000002222", served.id)];
    stubFetch();
    render(<SiteEditorApp />);
    fireEvent.click(await screen.findByLabelText("More"));
    fireEvent.click(screen.getByRole("menuitem", { name: /Set up a site/ }));
    expect(screen.getByTestId("new-room")).toBeTruthy();
    fireEvent.click(await screen.findByTestId("act-anchor"));
    await waitFor(() => expect(screen.getByTestId("anchor-panel")).toBeTruthy());
    expect(screen.queryByTestId("new-room")).toBeNull();
    expect(screen.getByRole("tab", { name: /^Anchor/ }).getAttribute("aria-selected")).toBe("true");
  });
});

describe("rows look, buttons act", () => {
  it("a row click selects its subject and picks its kind top-down, without a flow", async () => {
    fleet.bots = [holding("DE00000000002222", served.id)];
    stubFetch();
    render(<SiteEditorApp />);
    fireEvent.click(await screen.findByTestId("goal-floor"));
    expect(screen.getByTestId("inspector-floor")).toBeTruthy();
    expect(screen.getByTestId("goal-floor").getAttribute("aria-pressed")).toBe("true");
    await waitFor(() => expect(screen.getByTestId("plan")).toBeTruthy());
    expect(screen.getByRole("tab", { name: /^Extent/ }).getAttribute("aria-selected")).toBe("true");
    // The floor is measured: nothing to do, so no button
    expect(screen.queryByTestId("act-floor")).toBeNull();
    fireEvent.click(screen.getByTestId("goal-anchor"));
    expect(screen.getByTestId("inspector-anchor")).toBeTruthy();
    expect(screen.getByRole("tab", { name: /^Anchor/ }).getAttribute("aria-selected")).toBe("true");
    expect(screen.queryByTestId("anchor-panel")).toBeNull();
    expect(screen.getByTestId("act-anchor").textContent).toBe("Anchor with a robot…");
  });

  it("each row with a kind picks that kind on the map, on Select", async () => {
    stubFetch({
      "api/site": () =>
        new Response(
          JSON.stringify({ ...SITE, site: { ...SITE.site, walls: [{ name: "north", points: [[0, 0], [1060, 0]] }], objects: [{ type: "charger", name: "c1", x: 100, y: 100 }] }, text: TEXT }),
          { status: 200 },
        ),
    });
    render(<SiteEditorApp />);
    const rows: [string, RegExp][] = [
      ["goal-stations", /^Stations/],
      ["goal-floor", /^Extent/],
      ["goal-anchor", /^Anchor/],
      ["goal-areas", /^Areas/],
      ["goal-walls", /^Walls/],
      ["goal-objects", /^Objects/],
    ];
    for (const [row, tab] of rows) {
      fireEvent.click(await screen.findByTestId(row));
      await waitFor(() => expect(screen.getByTestId("plan")).toBeTruthy());
      expect(screen.getByRole("tab", { name: tab }).getAttribute("aria-selected")).toBe("true");
      expect(screen.getByRole("button", { name: "Select" }).getAttribute("aria-pressed")).toBe("true");
    }
  });

  it("on a page that cannot write, a row selects its subject in View", async () => {
    stubFetch({ "api/context": () => new Response(JSON.stringify({ ...CONTEXT, can_write: false }), { status: 200 }) });
    render(<SiteEditorApp />);
    fireEvent.click(await screen.findByTestId("goal-stations"));
    expect(screen.getByTestId("goal-stations").getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByTestId("room-view")).toBeTruthy();
    expect(screen.queryByTestId("plan")).toBeNull();
  });

  it("says anchoring needs a robot, and keeps its button off until one reports a position", async () => {
    fleet.bots = [{ ...holding("DE00000000002222", served.id), position: null }];
    stubFetch();
    const first = render(<SiteEditorApp />);
    fireEvent.click(await screen.findByTestId("goal-anchor"));
    expect(screen.getByTestId("inspector-anchor").querySelector(".ins-h")!.textContent).toContain("not anchored");
    expect(screen.getByTestId("anchor-needs").textContent).toContain("Needs a real robot and a tape measure");
    expect(screen.getByTestId("inspector-anchor").textContent).not.toContain("where the spin put it");
    const start = screen.getByTestId("anchor-start") as HTMLButtonElement;
    expect(start.textContent).toBe("Anchor with a robot…");
    expect(start.disabled).toBe(true);
    expect(screen.getByTestId("anchor-no-robot").textContent).toBe("No robot is reporting a position. Turn one on inside the coverage.");
    first.unmount();
    fleet.bots = [holding("DE00000000002222", served.id)];
    render(<SiteEditorApp />);
    fireEvent.click(await screen.findByTestId("goal-anchor"));
    expect((screen.getByTestId("anchor-start") as HTMLButtonElement).disabled).toBe(false);
    expect(screen.queryByTestId("anchor-no-robot")).toBeNull();
    fireEvent.click(screen.getByTestId("anchor-start"));
    await waitFor(() => expect(screen.getByTestId("anchor-panel").textContent).toContain("Needs a real robot and a tape measure"));
  });

  it("opens Walls and Objects on their drawing tool while there are none, else on Select", async () => {
    stubFetch();
    render(<SiteEditorApp />);
    fireEvent.click(await screen.findByTestId("goal-walls"));
    await waitFor(() => expect(screen.getByTestId("plan")).toBeTruthy());
    expect(screen.getByRole("tab", { name: /^Walls/ }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getByRole("button", { name: "Wall" }).getAttribute("aria-pressed")).toBe("true");
    keyDown("Escape");
    expect(screen.getByRole("button", { name: "Select" }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByTestId("goal-objects"));
    expect(screen.getByRole("tab", { name: /^Objects/ }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getByRole("button", { name: "Charger" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("opens Walls on Select when there are walls to pick", async () => {
    stubFetch({
      "api/site": () =>
        new Response(JSON.stringify({ ...SITE, site: { ...SITE.site, walls: [{ name: "north", points: [[0, 0], [1060, 0]] }] }, text: TEXT }), { status: 200 }),
    });
    render(<SiteEditorApp />);
    await waitFor(() => expect(screen.getByTestId("goal-walls").textContent).toContain("1 wall"));
    fireEvent.click(screen.getByTestId("goal-walls"));
    await waitFor(() => expect(screen.getByTestId("plan")).toBeTruthy());
    expect(screen.getByRole("button", { name: "Select" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("closes a flow when another row is picked, and reopening it keeps what was typed", async () => {
    fleet.bots = [holding("DE00000000002222", served.id)];
    stubFetch();
    render(<SiteEditorApp />);
    fireEvent.click(await screen.findByTestId("act-anchor"));
    await waitFor(() => expect(screen.getByTestId("anchor-panel")).toBeTruthy());
    const x = screen.getByLabelText("spot x of …2222");
    fireEvent.change(x, { target: { value: "120" } });
    fireEvent.keyDown(x, { key: "Enter" });
    fireEvent.click(screen.getByTestId("goal-areas"));
    expect(screen.queryByTestId("anchor-panel")).toBeNull();
    expect(screen.getByTestId("inspector-areas")).toBeTruthy();
    fireEvent.click(screen.getByTestId("act-anchor"));
    await waitFor(() => expect(screen.getByTestId("anchor-panel")).toBeTruthy());
    expect((screen.getByLabelText("spot x of …2222") as HTMLInputElement).value).toBe("120");
    keyDown("Escape");
    await waitFor(() => expect(screen.queryByTestId("anchor-panel")).toBeNull());
  });
});

describe("keeping the operator's work", () => {
  const edit = async () => {
    await toPlan();
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

const holding = (id: string, held: string) => ({ id, address: id, application: "DotBot", state: "Running", status: 0, position: { x: 300, y: 400 }, swarmit: { info: { info_version: 4, lh2_station_mask: 3, lh2_calibration_id: held } } });

describe("the one map", () => {
  const geometry = { stations: { "0": { x_mm: -542, y_mm: 1268, height_mm: 2423, off_square_deg: 5.4 }, "1": { x_mm: 1387, y_mm: -245, height_mm: 1606, off_square_deg: -3.1 } }, apart_mm: { "0-1": 2583 } };
  const withGeometry = (rows: LibraryRow[]) => ({ ...LIBRARY, serving: { ...served, geometry }, groups: [{ ...LIBRARY.groups[0], rows: rows.map((r) => (r.id === served.id ? { ...r, geometry } : r)) }] });
  const stub = () => stubFetch({ "api/calibrations?": () => new Response(JSON.stringify(withGeometry(inFrame)), { status: 200 }) });
  const preset = (name: string) => screen.getByRole("button", { name, pressed: undefined });

  it("opens in 3D at 3/4 with both panes, and draws the stations, their rays to their own coverage and the robots", async () => {
    fleet.bots = [holding("DE00000000002222", served.id)];
    stub();
    render(<SiteEditorApp />);
    await waitFor(() => expect(screen.getByTestId("room-card-0")).toBeTruthy());
    expect(screen.queryByTestId("plan")).toBeNull();
    expect(screen.queryByTestId("presbar")).toBeNull();
    expect(screen.getByTestId("pane-left")).toBeTruthy();
    expect(screen.getByTestId("pane-right")).toBeTruthy();
    expect(preset("3/4").getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByTestId("room-card-0").querySelector("text")?.textContent).toBe("S0 ≈ 2.4 m up · fit 1.10 mm");
    expect(screen.getAllByTestId("room-ray-0")).toHaveLength(4);
    expect(screen.getAllByTestId(/room-cover-/)).toHaveLength(2);
    await waitFor(() => expect(screen.getAllByTestId("room-robot")).toHaveLength(1));
    expect(screen.getByTestId("room-coverage-note").textContent).toBe("both cover the whole extent, no handover");
    expect(screen.queryByRole("tab", { name: "Plan" })).toBeNull();
  });

  it("goes top-down to edit and back: Edit, a kind's number, Done and Esc", async () => {
    stub();
    render(<SiteEditorApp />);
    await waitFor(() => expect(screen.getByTestId("room-view")).toBeTruthy());
    fireEvent.click(screen.getByTestId("enter-edit"));
    await waitFor(() => expect(screen.getByTestId("plan")).toBeTruthy());
    expect(screen.queryByTestId("room-view")).toBeNull();
    expect(preset("Top").getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByTestId("done-editing"));
    await waitFor(() => expect(screen.getByTestId("room-view")).toBeTruthy());
    await waitFor(() => expect(preset("3/4").getAttribute("aria-pressed")).toBe("true"));
    keyDown("4");
    await waitFor(() => expect(screen.getByTestId("tools")).toBeTruthy());
    expect(screen.getByRole("tab", { name: /^Areas/ }).getAttribute("aria-selected")).toBe("true");
    keyDown("Escape");
    await waitFor(() => expect(screen.getByTestId("room-view")).toBeTruthy());
    expect(screen.getByRole("tab", { name: /^View/ }).getAttribute("aria-selected")).toBe("true");
  });

  it("leaves the edit for a preset other than Top, and keeps the draft across the round trip", async () => {
    stub();
    render(<SiteEditorApp />);
    await toPlan();
    fireEvent.click(screen.getByRole("tab", { name: "Outline" }));
    fireEvent.click(screen.getByTestId("outline-area:field"));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "arena" } });
    fireEvent.keyDown(screen.getByLabelText("Name"), { key: "Enter" });
    await waitFor(() => expect(screen.getByTestId("unsaved").textContent).toContain("1 unsaved"));
    fireEvent.click(preset("Top"));
    expect(screen.getByTestId("plan")).toBeTruthy();
    fireEvent.click(preset("Side"));
    await waitFor(() => expect(screen.getByTestId("room-view")).toBeTruthy());
    await waitFor(() => expect(preset("Side").getAttribute("aria-pressed")).toBe("true"));
    expect(screen.getByTestId("unsaved").textContent).toContain("1 unsaved");
    expect(screen.getByTestId("room-label-area-area:field").textContent).toBe("arena");
    await toPlan();
    expect(screen.getByTestId("area-arena")).toBeTruthy();
  });

  it("a preset resets the zoom", async () => {
    stub();
    render(<SiteEditorApp />);
    await waitFor(() => expect(screen.getByTestId("room-view")).toBeTruthy());
    fireEvent.click(screen.getByLabelText("Zoom in"));
    expect(screen.getByTestId("room-fit").className).toBe("");
    fireEvent.click(preset("Front"));
    expect(screen.getByTestId("room-fit").className).toBe("on");
  });

  it("opens every load in View, 3D, at 3/4, whatever this browser kept, with the draft restored", async () => {
    stub();
    window.localStorage.setItem("dotbot.siteEditor.camera", JSON.stringify({ az: 0, el: 90 }));
    window.localStorage.setItem("dotbot.siteEditor.mode", "edit");
    const first = render(<SiteEditorApp />);
    await toPlan();
    keyDown("4");
    fireEvent.click(screen.getByRole("tab", { name: "Outline" }));
    fireEvent.click(screen.getByTestId("outline-area:field"));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "arena" } });
    fireEvent.keyDown(screen.getByLabelText("Name"), { key: "Enter" });
    await waitFor(() => expect(screen.getByTestId("unsaved").textContent).toContain("1 unsaved"));
    expect(screen.getByTestId("plan")).toBeTruthy();
    first.unmount();
    render(<SiteEditorApp />);
    await waitFor(() => expect(screen.getByTestId("notice").textContent).toContain("restored from this browser"));
    expect(screen.getByTestId("room-view")).toBeTruthy();
    expect(screen.queryByTestId("plan")).toBeNull();
    expect(screen.getByRole("tab", { name: /^View/ }).getAttribute("aria-selected")).toBe("true");
    expect(preset("3/4").getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByTestId("room-label-area-area:field").textContent).toBe("arena");
  });

  it("presents the same map full screen, and Edit · Esc or Esc goes back to the editor in 3D", async () => {
    stub();
    render(<SiteEditorApp />);
    await waitFor(() => expect(screen.getByTestId("room-view")).toBeTruthy());
    fireEvent.click(screen.getByTestId("present"));
    await waitFor(() => expect(screen.getByTestId("presbar")).toBeTruthy());
    expect(screen.getByTestId("present-edit").textContent).toContain("Edit · Esc");
    expect(screen.queryByText("Exit")).toBeNull();
    fireEvent.click(screen.getByTestId("present-edit"));
    await waitFor(() => expect(screen.queryByTestId("presbar")).toBeNull());
    expect(screen.getByTestId("room-view")).toBeTruthy();
    keyDown("f");
    await waitFor(() => expect(screen.getByTestId("presbar")).toBeTruthy());
    keyDown("2");
    expect(screen.queryByTestId("plan")).toBeNull();
    keyDown("Escape");
    await waitFor(() => expect(screen.queryByTestId("presbar")).toBeNull());
    expect(screen.getByTestId("room-view")).toBeTruthy();
  });

  it("follows a drafted split: the canvas, the legend and the Coverage check all describe the draft", async () => {
    stub();
    render(<SiteEditorApp />);
    await waitFor(() => expect(screen.getByTestId("goal-stations-coverage")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "Split at the best line" }));
    await waitFor(() => expect(screen.getByTestId("notice").textContent).toContain("Draft: split at x 530 mm. Drag the dashed line to move it, then Save."));
    await waitFor(() => expect(screen.getByTestId("plan")).toBeTruthy());
    expect(screen.getByTestId("goal-stations-coverage").textContent).toContain("handover at x 530 mm · not in use yet (in use: both cover the whole extent)");
    expect(screen.getByTestId("coverage-card").textContent).toContain("Handover at x 530 mm · not in use yet");
    expect(screen.getByTestId("switch-label").textContent).toBe("switches here · x 530 mm");
    expect(screen.getByTestId("band-label").textContent).toBe("both allowed");
    fireEvent.click(screen.getByTestId("done-editing"));
    await waitFor(() => expect(screen.getByTestId("room-handover")).toBeTruthy());
    expect(screen.getByTestId("room-label-handover").textContent).toBe("switches here · x 530 mm");
    expect(screen.getByTestId("room-label-band").textContent).toBe("both allowed");
    expect(screen.getByTestId("room-coverage-note").textContent).toBe("handover at x 530 mm · not in use yet (in use: both cover the whole extent)");
    fireEvent.click(screen.getByTestId("notice-act"));
    await waitFor(() => expect(screen.getByTestId("goal-stations-coverage").textContent).toContain("robots pick the closer fix"));
  });

  it("marks where each station stands on the plan, with a layer to hide them", async () => {
    stub();
    render(<SiteEditorApp />);
    await toPlan();
    await waitFor(() => expect(screen.getByTestId("station-pos-0")).toBeTruthy());
    // One label in both views, the same card; where it stands is in the tooltip
    expect(screen.getByTestId("station-card-0").textContent).toBe("S0 ≈ 2.4 m up · fit 1.10 mm");
    expect(screen.getByTestId("station-pos-0").querySelector("title")?.textContent).toContain("(-542, 1268) mm");
    expect(screen.getByTestId("station-pos-0").querySelector("title")?.textContent).toContain("estimated, not to tape");
    keyDown("4");
    expect(screen.queryByTestId("station-pos-0")).toBeNull();
    keyDown("2");
    expect(screen.getByTestId("station-pos-1")).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: "Layers" }));
    fireEvent.click(screen.getByText("Station positions"));
    expect(screen.queryByTestId("station-pos-1")).toBeNull();
  });
});

describe("picking a coverage to resize", () => {
  const geometry = { stations: { "0": { x_mm: -542, y_mm: 1268, height_mm: 2423, off_square_deg: 5.4 }, "1": { x_mm: 1387, y_mm: -245, height_mm: 1606, off_square_deg: -3.1 } }, apart_mm: { "0-1": 2583 } };
  const stub = () =>
    stubFetch({
      "api/calibrations?": () =>
        new Response(JSON.stringify({ ...LIBRARY, serving: { ...served, geometry }, groups: [{ ...LIBRARY.groups[0], rows: inFrame.map((r) => (r.id === served.id ? { ...r, geometry } : r)) }] }), { status: 200 }),
    });
  /** Where frame mm `p` lands on the plan, as a pointer event's client point. */
  const at = (p: [number, number]) => {
    const floor = screen.getByTestId("floor");
    const boxW = Number(floor.closest("svg")!.getAttribute("width"));
    const [fx, fy, fw, fh] = ["x", "y", "width", "height"].map((k) => Number(floor.getAttribute(k)));
    const m = /translate\((-?[\d.]+)px, (-?[\d.]+)px\) scale\(([\d.]+)\)/.exec((floor.closest("svg")!.parentElement!.parentElement as HTMLElement).style.transform)!;
    const [tx, ty, sc] = [Number(m[1]), Number(m[2]), Number(m[3])];
    const boxH = Number(floor.closest("svg")!.getAttribute("height"));
    const bx = fx + (p[0] / 1060) * fw;
    const by = fy + (p[1] / 1220) * fh;
    return { clientX: (bx - boxW / 2) * sc + 400 + tx, clientY: (by - boxH / 2) * sc + 300 + ty };
  };
  const click = (el: Element, p: [number, number]) => {
    fireEvent.pointerDown(el, { button: 0, pointerId: 1, ...at(p) });
    fireEvent.pointerUp(screen.getByTestId("plan"), { button: 0, pointerId: 1, ...at(p) });
  };
  const toStations = async () => {
    await toPlan();
    keyDown("2");
    await waitFor(() => expect(screen.getByTestId("station-pos-0")).toBeTruthy());
  };
  const picked = () => screen.queryByTestId("inspector-box")?.querySelector(".name")?.textContent ?? null;

  it("selects a coverage by a click inside it, over the field area, the nearest station's where they overlap", async () => {
    stub();
    render(<SiteEditorApp />);
    await toStations();
    // Both cover the whole extent: S0 stands off the bottom-left corner, S1 off the top-right
    click(screen.getByTestId("area-field").querySelector("rect")!, [100, 1100]);
    expect(picked()).toBe("S0");
    expect(screen.getAllByTestId(/^box-handle-/)).toHaveLength(8);
    expect(screen.getByRole("tab", { name: /^Stations/ }).getAttribute("aria-selected")).toBe("true");
    click(screen.getByTestId("plan"), [1000, 100]);
    expect(picked()).toBe("S1");
    // Outside every coverage, a click clears the selection
    click(screen.getByTestId("plan"), [1500, 600]);
    expect(screen.queryAllByTestId(/^box-handle-/)).toHaveLength(0);
  });

  it("selects a station's coverage from its marker and from its Resize coverage button", async () => {
    stub();
    render(<SiteEditorApp />);
    await toStations();
    fireEvent.pointerDown(screen.getByTestId("station-pos-1"), { button: 0, pointerId: 1 });
    expect(picked()).toBe("S1");
    expect(screen.getAllByTestId(/^box-handle-/)).toHaveLength(8);
    fireEvent.click(screen.getByRole("button", { name: "All stations" }));
    fireEvent.click(screen.getByTestId("resize-coverage-0"));
    expect(picked()).toBe("S0");
    expect(screen.getAllByTestId(/^box-handle-/)).toHaveLength(8);
  });

  it("shows no coverage handles on a page that cannot write", async () => {
    stubFetch({
      "api/context": () => new Response(JSON.stringify({ ...CONTEXT, can_write: false }), { status: 200 }),
      "api/calibrations?": () =>
        new Response(JSON.stringify({ ...LIBRARY, serving: { ...served, geometry }, groups: [{ ...LIBRARY.groups[0], rows: inFrame.map((r) => (r.id === served.id ? { ...r, geometry } : r)) }] }), { status: 200 }),
    });
    render(<SiteEditorApp />);
    await toStations();
    fireEvent.pointerDown(screen.getByTestId("station-pos-1"), { button: 0, pointerId: 1 });
    expect(picked()).toBe("S1");
    expect(screen.queryAllByTestId(/^box-handle-/)).toHaveLength(0);
  });

  it("lets the handover line take a drag before the coverage under it", async () => {
    stub();
    render(<SiteEditorApp />);
    await waitFor(() => expect(screen.getByTestId("goal-stations-coverage")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "Split at the best line" }));
    await waitFor(() => expect(screen.getByTestId("handover-grip")).toBeTruthy());
    click(screen.getByTestId("handover-grip"), [530, 600]);
    expect(picked()).toBeNull();
    expect(screen.queryAllByTestId(/^box-handle-/)).toHaveLength(0);
  });

  it("leaves areas out of a Stations edit, and coverages out of an Areas edit", async () => {
    stub();
    render(<SiteEditorApp />);
    await toStations();
    click(screen.getByTestId("area-field").querySelector("rect")!, [500, 600]);
    expect(screen.queryByTestId("handle-n")).toBeNull();
    expect(screen.getByRole("tab", { name: /^Stations/ }).getAttribute("aria-selected")).toBe("true");
    keyDown("4");
    click(screen.getByTestId("box-0").querySelector("rect")!, [0, 0]);
    expect(screen.queryAllByTestId(/^box-handle-/)).toHaveLength(0);
    expect(screen.getByRole("tab", { name: /^Areas/ }).getAttribute("aria-selected")).toBe("true");
    click(screen.getByTestId("area-field").querySelector("rect")!, [500, 600]);
    expect(screen.getByTestId("handle-n")).toBeTruthy();
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
    await waitFor(() => expect(screen.getByTestId("serve-conflict").textContent).toContain("Another page switched it to"));
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
    await toPlan();
    keyDown("1");
    keyDown("t");
    const turn = screen.getByLabelText("turn");
    fireEvent.change(turn, { target: { value: "5" } });
    fireEvent.keyDown(turn, { key: "Enter" });
    await waitFor(() => expect(screen.getByTestId("frame-ghost")).toBeTruthy());
    keyDown("v");
    await waitFor(() => expect(screen.queryByTestId("frame-ghost")).toBeNull());
  });
});

describe("the collapse order", () => {
  it("folds the left pane into a rail below 1100 px and the right one below 980 px", async () => {
    stubFetch();
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 1024 });
    const { unmount } = render(<SiteEditorApp />);
    await toPlan();
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


describe("Push to robots", () => {
  it("stays off while every robot holds what the controller uses, and opens the push sheet once one does not", async () => {
    fleet.bots = [holding("DE00000000002B07", served.id), holding("DE00000000004A11", served.id)];
    stubFetch();
    const first = render(<SiteEditorApp />);
    await waitFor(() => expect(screen.getByTestId("status-line").textContent).toContain("robots: on 2 of 2"));
    expect((screen.getByTestId("push") as HTMLButtonElement).disabled).toBe(true);
    first.unmount();
    fleet.bots = [holding("DE00000000002B07", served.id), holding("DE00000000004A11", handover.id)];
    render(<SiteEditorApp />);
    await waitFor(() => expect(screen.getByTestId("status-line").textContent).toContain("robots: need a push"));
    const push = screen.getByTestId("push") as HTMLButtonElement;
    await waitFor(() => expect(push.disabled).toBe(false));
    fireEvent.click(push);
    await waitFor(() => expect(screen.getByTestId("serve-sheet")).toBeTruthy());
    expect(screen.getByTestId("serve-in-use")).toBeTruthy();
    expect(screen.getByTestId("serve-sheet").textContent).toContain(`Push ${served.tag} to robots`);
  });

  it("cannot tell when the robots send no device info", async () => {
    fleet.bots = [{ ...holding("DE00000000002B07", ""), swarmit: null }];
    stubFetch();
    render(<SiteEditorApp />);
    await waitFor(() => expect(screen.getByTestId("status-line").textContent).toContain("robots: cannot tell"));
    expect(screen.getByTestId("push").textContent).toContain("cannot tell");
    expect((screen.getByTestId("push") as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("a move of the origin in the draft", () => {
  const moved = {
    frame: "0badf00d",
    from_frame: "f0237ffd",
    site: { ...SITE.site, extent_mm: [1560, 1720], areas: [{ ...SITE.site.areas[0], x: 500, y: 500 }] },
    base: { ...SITE.site, extent_mm: [1560, 1720], areas: [{ ...SITE.site.areas[0], x: 500, y: 500 }] },
    stations: null,
    coverage: { 0: [500, 500, 1560, 1720], 1: [500, 500, 1560, 1720] },
    warnings: [],
  };

  it("counts as one unsaved change, keeps the area on the floor with new numbers, and undoes as one", async () => {
    fleet.bots = [holding("DE00000000002B07", served.id)];
    const calls = stubFetch({ "api/frame": () => new Response(JSON.stringify(moved), { status: 200 }) });
    render(<SiteEditorApp />);
    await toPlan();
    keyDown("1");
    keyDown("t");
    for (const [label, v] of [
      ["shift x", "-500"],
      ["shift y", "-500"],
    ]) {
      const f = screen.getByLabelText(label);
      fireEvent.change(f, { target: { value: v } });
      fireEvent.keyDown(f, { key: "Enter" });
    }
    await waitFor(() => expect(screen.getByTestId("frame-ghost")).toBeTruthy());
    fireEvent.click(await screen.findByTestId("frame-apply"));
    await waitFor(() => expect(screen.getByTestId("status-unsaved").textContent).toContain("1 unsaved change"));
    expect(screen.getByTestId("frame-in-draft")).toBeTruthy();
    expect(screen.queryByTestId("frame-ghost")).toBeNull();
    expect(screen.getByTestId("robots-old-origin").textContent).toBe("robots report in the old origin until pushed");
    const asked = JSON.parse(calls.find((c) => c.url === "api/frame")!.init!.body as string);
    expect(asked.move).toEqual({ theta_deg: 0, pivot: [530, 610], dx_mm: -500, dy_mm: -500 });
    // Nothing was written: only the server's dry runs were asked
    expect(calls.filter((c) => c.url === "api/apply" && !JSON.parse(c.init!.body as string).dry_run)).toEqual([]);
    fireEvent.click(screen.getByRole("tab", { name: "Outline" }));
    fireEvent.click(screen.getByTestId("outline-area:field"));
    expect((screen.getByLabelText("x") as HTMLInputElement).value).toBe("500");
    keyDown("z", { ctrlKey: true });
    await waitFor(() => expect(screen.queryByTestId("status-unsaved")).toBeNull());
    expect((screen.getByLabelText("x") as HTMLInputElement).value).toBe("0");
    expect(screen.queryByTestId("robots-old-origin")).toBeNull();
    keyDown("z", { ctrlKey: true, shiftKey: true });
    await waitFor(() => expect(screen.getByTestId("status-unsaved").textContent).toContain("1 unsaved change"));
    expect((screen.getByLabelText("x") as HTMLInputElement).value).toBe("500");
  });
});

/** Where frame mm `p` lands on the plan, as a pointer event's client point. */
function planAt(p: [number, number], extent: [number, number] = [1060, 1220]) {
  const floor = screen.getByTestId("floor");
  const svg = floor.closest("svg")!;
  const [boxW, boxH] = [Number(svg.getAttribute("width")), Number(svg.getAttribute("height"))];
  const [fx, fy, fw, fh] = ["x", "y", "width", "height"].map((k) => Number(floor.getAttribute(k)));
  const m = /translate\(([-\d.e+]+)px, ([-\d.e+]+)px\) scale\(([-\d.e+]+)\)/.exec((svg.parentElement!.parentElement as HTMLElement).style.transform)!;
  const [tx, ty, sc] = [Number(m[1]), Number(m[2]), Number(m[3])];
  return { clientX: (fx + (p[0] / extent[0]) * fw - boxW / 2) * sc + 400 + tx, clientY: (fy + (p[1] / extent[1]) * fh - boxH / 2) * sc + 300 + ty };
}

describe("the origin moved on the plan", () => {
  const moved = { frame: "0badf00d", from_frame: "f0237ffd", site: SITE.site, base: SITE.site, stations: null, coverage: { 0: [0, 0, 1060, 1220], 1: [0, 0, 1060, 1220] }, warnings: [] };
  const lastMove = (calls: { url: string; init?: RequestInit }[]) => JSON.parse(calls.filter((c) => c.url === "api/frame").slice(-1)[0].init!.body as string).move;

  it("drags the origin to a shift snapped to 10 mm, put in the draft as one change", async () => {
    const calls = stubFetch({ "api/frame": () => new Response(JSON.stringify(moved), { status: 200 }) });
    render(<SiteEditorApp />);
    await toPlan();
    keyDown("1");
    fireEvent.pointerDown(await screen.findByTestId("origin-grip"), { button: 0, pointerId: 1, ...planAt([0, 0]) });
    fireEvent.pointerMove(screen.getByTestId("plan"), { pointerId: 1, ...planAt([123, 77]) });
    expect(screen.getByTestId("frame-readout").textContent).toBe("dx +120, dy +80 mm");
    expect(screen.getByTestId("frame-ghost")).toBeTruthy();
    expect(screen.getByTestId("frame-turn")).toBeTruthy();
    fireEvent.pointerUp(screen.getByTestId("plan"), { pointerId: 1, ...planAt([123, 77]) });
    await waitFor(() => expect(screen.getByTestId("status-unsaved").textContent).toContain("1 unsaved change"));
    expect(lastMove(calls)).toEqual({ theta_deg: 0, pivot: [120, 80], dx_mm: 120, dy_mm: 80 });
    expect((screen.getByLabelText("shift x") as HTMLInputElement).value).toBe("120");
    expect(screen.queryByTestId("frame-readout")).toBeNull();
    keyDown("z", { ctrlKey: true });
    await waitFor(() => expect(screen.queryByTestId("status-unsaved")).toBeNull());
  });

  it("reads a drag from the drafted origin, and keeps the drafted floor's far edges in its preview", async () => {
    const drafted = { ...moved, site: { ...SITE.site, extent_mm: [2490, 2500], areas: [{ ...SITE.site.areas[0], x: 290, y: 150 }] } };
    stubFetch({ "api/frame": () => new Response(JSON.stringify(drafted), { status: 200 }) });
    render(<SiteEditorApp />);
    await toPlan();
    keyDown("1");
    keyDown("t");
    for (const [label, v] of [
      ["shift x", "-290"],
      ["shift y", "-150"],
    ]) {
      const f = screen.getByLabelText(label);
      fireEvent.change(f, { target: { value: v } });
      fireEvent.keyDown(f, { key: "Enter" });
    }
    fireEvent.click(await screen.findByTestId("frame-apply"));
    await waitFor(() => expect(screen.getByTestId("frame-in-draft")).toBeTruthy());
    keyDown("v");
    const ext: [number, number] = [2490, 2500];
    fireEvent.pointerDown(await screen.findByTestId("origin-grip"), { button: 0, pointerId: 1, ...planAt([0, 0], ext) });
    fireEvent.pointerMove(screen.getByTestId("plan"), { pointerId: 1, ...planAt([130, 140], ext) });
    expect(screen.getByTestId("frame-readout").textContent).toBe("dx +130, dy +140 mm");
    expect(screen.getByTestId("frame-ghost").getAttribute("data-extent")).toBe("2360x2360");
    fireEvent.pointerUp(screen.getByTestId("plan"), { pointerId: 1, ...planAt([130, 140], ext) });
    await waitFor(() => expect((screen.getByLabelText("shift x") as HTMLInputElement).value).toBe("-160"));
    expect((screen.getByLabelText("shift y") as HTMLInputElement).value).toBe("-10");
  });

  it("turns the frame about the origin from the handle, in 0.5 degree steps or 15 with Shift", async () => {
    const calls = stubFetch({ "api/frame": () => new Response(JSON.stringify(moved), { status: 200 }) });
    render(<SiteEditorApp />);
    await toPlan();
    keyDown("1");
    const along = (deg: number): [number, number] => [300, 300 * Math.tan((deg * Math.PI) / 180)];
    fireEvent.pointerDown(await screen.findByTestId("turn-grip"), { button: 0, pointerId: 1, ...planAt([300, 0]) });
    fireEvent.pointerMove(screen.getByTestId("plan"), { pointerId: 1, ...planAt(along(12.3)) });
    expect(screen.getByTestId("frame-readout").textContent).toBe("turn 12.5°");
    fireEvent.pointerMove(screen.getByTestId("plan"), { pointerId: 1, shiftKey: true, ...planAt(along(12.3)) });
    expect(screen.getByTestId("frame-readout").textContent).toBe("turn 15°");
    fireEvent.pointerUp(screen.getByTestId("plan"), { pointerId: 1, shiftKey: true, ...planAt(along(12.3)) });
    await waitFor(() => expect(screen.getByTestId("status-unsaved").textContent).toContain("1 unsaved change"));
    expect(lastMove(calls)).toEqual({ theta_deg: 15, pivot: [0, 0], dx_mm: 0, dy_mm: 0 });
  });

  it("nudges the origin with the arrow keys while it is picked, 10 mm or 1 with Alt", async () => {
    const calls = stubFetch({ "api/frame": () => new Response(JSON.stringify(moved), { status: 200 }) });
    render(<SiteEditorApp />);
    await toPlan();
    keyDown("1");
    fireEvent.pointerDown(await screen.findByTestId("origin-grip"), { button: 0, pointerId: 1, ...planAt([0, 0]) });
    fireEvent.pointerUp(screen.getByTestId("plan"), { pointerId: 1, ...planAt([0, 0]) });
    expect(screen.getByTestId("frame-turn")).toBeTruthy();
    keyDown("ArrowRight");
    keyDown("ArrowRight");
    keyDown("ArrowDown", { altKey: true });
    await waitFor(() => expect(screen.getByTestId("status-unsaved").textContent).toContain("1 unsaved change"));
    expect(lastMove(calls)).toEqual({ theta_deg: 0, pivot: [20, 1], dx_mm: 20, dy_mm: 1 });
  });

  it("shows its handles only in an Extent edit, with a tool that is not Measure, on a page that can write", async () => {
    stubFetch();
    const first = render(<SiteEditorApp />);
    await toPlan();
    keyDown("4");
    expect(screen.queryByTestId("origin-grip")).toBeNull();
    keyDown("1");
    expect(screen.getByTestId("origin-grip")).toBeTruthy();
    expect(screen.getByTestId("turn-grip")).toBeTruthy();
    keyDown("m");
    expect(screen.queryByTestId("origin-grip")).toBeNull();
    first.unmount();
    stubFetch({ "api/context": () => new Response(JSON.stringify({ ...CONTEXT, can_write: false }), { status: 200 }) });
    render(<SiteEditorApp />);
    await toPlan();
    keyDown("1");
    expect(screen.queryByTestId("origin-grip")).toBeNull();
    expect(screen.queryByTestId("turn-grip")).toBeNull();
  });
});
