import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SiteEditor } from "./SiteEditor";
import type { SiteResponse } from "./types";

const loaded = (count = 0): SiteResponse => ({
  name: "arena",
  path: "/packs/arena/site.toml",
  revision: "r1",
  calibrations: [{ folder: "/home/cal/arena", count }],
  site: {
    anchor: "the door corner",
    extent_mm: [2000, 4000],
    areas: [
      { name: "field", x: 0, y: 0, w: 2000, h: 2000, role: null, comment: "top" },
      { name: "dev-corner", x: 1000, y: 0, w: 1000, h: 1000, role: "corner", comment: null },
    ],
    connection: null,
  },
});

function server(first: SiteResponse, save: { status: number; body: unknown }) {
  const fetch = vi.fn(async (url: string, init?: RequestInit) => {
    const json = (status: number, body: unknown) =>
      new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
    if (url === "api/site" && (!init || !init.method)) return json(200, first);
    if (url === "api/site" && init?.method === "PUT") return json(save.status, save.body);
    return json(404, { detail: "no" });
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

afterEach(() => vi.unstubAllGlobals());

describe("SiteEditor", () => {
  it("draws every area and the anchor", async () => {
    server(loaded(), { status: 200, body: {} });
    render(<SiteEditor />);
    expect(await screen.findByTestId("edit-area-field")).toBeInTheDocument();
    expect(screen.getByTestId("edit-area-dev-corner")).toBeInTheDocument();
    expect(screen.getByTestId("anchor")).toBeInTheDocument();
  });

  it("edits an area's numbers and saves them with the loaded revision", async () => {
    const fetch = server(loaded(), {
      status: 200,
      body: { ...loaded(), revision: "r2", written: true },
    });
    render(<SiteEditor />);
    await screen.findByLabelText("show dev-corner");
    fireEvent.click(screen.getByLabelText("show dev-corner").parentElement!);
    fireEvent.change(screen.getByLabelText("x"), { target: { value: "950" } });
    await act(async () => fireEvent.click(screen.getByText("Save")));
    const put = fetch.mock.calls.find(([, init]) => init?.method === "PUT")!;
    const sent = JSON.parse(put[1]!.body as string);
    expect(sent.revision).toBe("r1");
    expect(sent.site.areas[1].x).toBe(950);
    expect(await screen.findByText(/saved \/packs\/arena\/site.toml/)).toBeInTheDocument();
  });

  it("offers Reload when the file changed on disk", async () => {
    server(loaded(), { status: 409, body: { detail: "changed" } });
    render(<SiteEditor />);
    await screen.findByLabelText("show dev-corner");
    fireEvent.change(screen.getByLabelText("anchor"), { target: { value: "moved" } });
    await act(async () => fireEvent.click(screen.getByText("Save")));
    expect(await screen.findByText("Reload")).toBeInTheDocument();
  });

  it("asks before changing the frame of a calibrated site, never for an area", async () => {
    const fetch = server(loaded(2), { status: 200, body: { ...loaded(2), written: true } });
    render(<SiteEditor />);
    await screen.findByLabelText("show dev-corner");
    expect(screen.getByTestId("calibration-note")).toHaveTextContent("2 calibration files");
    fireEvent.change(screen.getByLabelText("extent W (mm)"), { target: { value: "2500" } });
    fireEvent.click(screen.getByText("Save"));
    expect(screen.getByRole("dialog")).toHaveTextContent("calibrate-lh2 reframe");
    expect(fetch.mock.calls.some(([, init]) => init?.method === "PUT")).toBe(false);
    await act(async () => fireEvent.click(screen.getByText("Save anyway")));
    await waitFor(() => expect(fetch.mock.calls.some(([, init]) => init?.method === "PUT")).toBe(true));
  });

  it("blocks Save while a check fails", async () => {
    server(loaded(), { status: 200, body: {} });
    render(<SiteEditor />);
    await screen.findByLabelText("show dev-corner");
    fireEvent.click(screen.getByLabelText("show dev-corner").parentElement!);
    fireEvent.change(screen.getByLabelText("role"), { target: { value: "field" } });
    expect(screen.getByText("Save")).toBeDisabled();
    expect(screen.getByTestId("issues")).toHaveTextContent("at most one field");
  });

  it("moves an area by dragging it, on the snap grid", async () => {
    server(loaded(), { status: 200, body: {} });
    render(<SiteEditor />);
    const corner = await screen.findByTestId("edit-area-dev-corner");
    // An 800 x 600 canvas draws the 2 x 4 m site with its 400 mm margin at
    // 0.115 px/mm, so 23 px is 200 mm.
    fireEvent.pointerDown(corner, { button: 0, clientX: 300, clientY: 100, pointerId: 1 });
    fireEvent.pointerMove(screen.getByTestId("site-canvas"), { clientX: 323, clientY: 101, pointerId: 1 });
    fireEvent.pointerUp(screen.getByTestId("site-canvas"), { clientX: 323, clientY: 101, pointerId: 1 });
    expect(screen.getByLabelText("x")).toHaveValue(1200);
    expect(screen.getByLabelText("y")).toHaveValue(0);
  });

  it("leaves an off-grid area where it is when a click selects it", async () => {
    const offGrid = loaded();
    offGrid.site.areas[1] = { ...offGrid.site.areas[1], x: 1073, y: 7 };
    server(offGrid, { status: 200, body: {} });
    render(<SiteEditor />);
    const corner = await screen.findByTestId("edit-area-dev-corner");
    fireEvent.pointerDown(corner, { button: 0, clientX: 300, clientY: 100, pointerId: 1 });
    fireEvent.pointerMove(screen.getByTestId("site-canvas"), { clientX: 301, clientY: 101, pointerId: 1 });
    fireEvent.pointerUp(screen.getByTestId("site-canvas"), { clientX: 301, clientY: 101, pointerId: 1 });
    expect(screen.getByLabelText("x")).toHaveValue(1073);
    expect(screen.getByLabelText("y")).toHaveValue(7);
    expect(screen.queryByText(/unsaved/)).toBeNull();
  });
});
