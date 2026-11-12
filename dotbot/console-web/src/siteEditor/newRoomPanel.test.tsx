import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { docFromSite } from "./model";
import { NewRoomPanel } from "./NewRoomPanel";
import type { LibraryRow } from "./types";

const SPIN = "e06610ac00000000";

const row = (id: string, extra: Partial<LibraryRow>): LibraryRow => ({
  id,
  id8: id.slice(0, 8),
  tag: "",
  created_at: "2026-11-09T08:12:50Z",
  path: `/cal/${id}.toml`,
  site: "lab",
  coverage_union: [0, 0, 600, 800],
  spin: "s",
  tracks: 8,
  stations: [],
  reading: "",
  in_frame: false,
  served: false,
  ...extra,
});

const overlay = { id: SPIN, id8: SPIN.slice(0, 8), free: true, coverage_union: [0, 0, 600, 800], tag: "", site: "lab", frame_refusal: null, stations: [] };

afterEach(() => vi.unstubAllGlobals());

const panel = (rows: LibraryRow[]) =>
  render(
    <NewRoomPanel
      doc={docFromSite({ anchor: null, extent_mm: [2000, 2000], areas: [] })}
      siteName="lab"
      spin={null}
      placeId={SPIN}
      freeRows={[rows[0]]}
      bots={[]}
      live
      editable
      consoleHref="/console"
      onPlaceId={() => {}}
      onPreview={() => {}}
      placed={null}
      onDraft={() => {}}
      onClose={() => {}}
      servedId={null}
      rows={rows}
    />,
  );

describe("the new-room steps after a reload", () => {
  it("goes on past Place it in the site for a spin already placed", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(overlay), { status: 200 })));
    panel([row(SPIN, { free: true }), row("9a9a9a9a11111111", { in_frame: true, placed_from: SPIN, tag: "lab-placed" })]);
    await waitFor(() => expect(screen.getByText(/lab-placed is placed in this site/)).toBeTruthy());
    expect(screen.queryByTestId("place-write")).toBeNull();
  });

  it("offers to place a spin no file was placed from", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(overlay), { status: 200 })));
    panel([row(SPIN, { free: true })]);
    await waitFor(() => expect(screen.getByTestId("place-write")).toBeTruthy());
  });
});
