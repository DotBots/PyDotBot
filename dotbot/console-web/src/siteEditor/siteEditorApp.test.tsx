import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { filtered, groupTitle } from "./library";
import { editorChip, servedReason, SiteEditorApp } from "./SiteEditorApp";
import type { EditorContext, Library, LibraryRow, Rect } from "./types";

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

const CONTEXT: EditorContext = {
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

afterEach(() => vi.unstubAllGlobals());

function stubFetch() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const body = url.startsWith("api/context") ? CONTEXT : url.startsWith("api/site") ? SITE : LIBRARY;
      return new Response(JSON.stringify(body), { status: 200 });
    }),
  );
}

describe("the library", () => {
  it("titles a spin's group by its box layouts and searches the readings", () => {
    expect(groupTitle(LIBRARY.groups[0])).toBe("Spin of 2026-11-09 08:12 · 7 box layouts");
    const found = filtered(LIBRARY, "handover");
    expect(found.groups[0].rows.map((r) => r.id8)).toEqual(["a1b41f12"]);
    expect(found.not_placed).toEqual([]);
  });
});

describe("the chip and the serving card", () => {
  it("keeps the served id first while previewing another file", () => {
    const chip = editorChip(CONTEXT, handover);
    expect(chip.id8).toBe("4640cfde");
    expect(chip.side).toEqual({ kind: "preview", id8: "a1b41f12" });
  });

  it("says where the served calibration came from and what a restart serves", () => {
    expect(servedReason(CONTEXT)).toBe(
      "Loaded at start, named on the controller's command line (4640cfde). A restart without --lh2-calibration serves none.",
    );
    expect(
      servedReason({ ...CONTEXT, next_start: { spec: "4640cfde", source: "dotbot.local.toml" } }),
    ).toContain("A restart serves the same.");
  });

  it("names a configured calibration without claiming it is served", () => {
    const standalone: EditorContext = {
      ...CONTEXT,
      mode: "standalone",
      served: null,
      configured: { spec: "4640cfde", source: "dotbot.local.toml", id8: "4640cfde", id: served.id },
    };
    expect(editorChip(standalone, null)).toMatchObject({ id8: "4640cfde", live: false });
    expect(servedReason(standalone)).toContain("No controller serves it here");
  });
});

describe("the editor page", () => {
  it("opens on the served calibration, lists one group of 7 and 5 free spins, and previews on click", async () => {
    stubFetch();
    render(<SiteEditorApp />);
    await waitFor(() => expect(screen.getAllByTestId("library-group")).toHaveLength(1));
    expect(screen.getByTestId("library-group").textContent).toBe("Spin of 2026-11-09 08:12 · 7 box layouts");
    expect(screen.getByTestId("library-not-placed").textContent).toContain("5 spins");
    expect(screen.getByTestId("calibration-chip").textContent).toContain("SERVING4640cfde");
    expect(screen.getByTestId("serving-card").textContent).toContain("named on the controller's command line");
    fireEvent.click(screen.getByTestId("library-row-a1b41f12"));
    expect(screen.getByTestId("calibration-chip-side").textContent).toContain("previewing a1b41f12");
    expect(screen.getByTestId("calibration-chip").textContent).toContain("4640cfde");
    fireEvent.click(screen.getByLabelText("Back to the served calibration"));
    expect(screen.queryByTestId("calibration-chip-side")).toBeNull();
  });
});
