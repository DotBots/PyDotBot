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
});

describe("SiteEditor calibration placement", () => {
  const overlay = (free: boolean) => ({
    id: "3f2a91c0aaaaaaaa",
    id8: "3f2a91c0",
    free,
    fence: [0, 0, 1000, 800],
    stations: [
      {
        index: 0,
        channel: 1,
        rect: [0, 0, 1000, 800],
        centres: [[200, 300]],
        circles: [{ name: "robot0", x: 200, y: 300, radius_mm: 51.4 }],
        solved_from: free ? "conics-free" : "direct",
      },
    ],
    links: [],
    tag: "",
    created_at: "2026-10-01T10:00:00Z",
    site: "lab",
    anchor: "free mode",
  });

  function placementServer(free: boolean) {
    const fetch = vi.fn(async (url: string, init?: RequestInit) => {
      const json = (status: number, body: unknown) =>
        new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
      if (url === "api/site") return json(200, loaded());
      if (url === "api/calibrations")
        return json(200, [
          { id: "3f2a91c0aaaaaaaa", id8: "3f2a91c0", created_at: "", free, stations: [0], tag: "", site: "lab", path: "" },
        ]);
      if (url === "api/calibrations/3f2a91c0") return json(200, overlay(free));
      if (url === "api/calibrations/3f2a91c0aaaaaaaa/place" && init?.method === "POST")
        return json(200, {
          ...overlay(free),
          id8: "7c0d5e12",
          path: "/home/cal/arena/calibration-7c0d5e12.toml",
          source: "3f2a91c0",
          push: "dotbot swarm calibrate-lh2 push 7c0d5e12 --site arena --site-changed",
          warnings: [],
        });
      return json(404, { detail: "no" });
    });
    vi.stubGlobal("fetch", fetch);
    return fetch;
  }

  async function loadIt() {
    render(<SiteEditor />);
    await screen.findByTestId("edit-area-field");
    fireEvent.click(screen.getByText("Calibration"));
    fireEvent.change(await screen.findByLabelText("calibration id"), { target: { value: "3f2a91c0" } });
    await act(async () => fireEvent.click(screen.getByText("Load")));
  }

  it("draws a loaded calibration and saves it moved as a new one", async () => {
    const fetch = placementServer(true);
    await loadIt();
    expect(await screen.findByTestId("placement-circle-0-robot0")).toBeInTheDocument();
    expect(screen.getByTestId("placement-turn")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("shift x (mm)"), { target: { value: "500" } });
    fireEvent.change(screen.getByLabelText("turn (deg)"), { target: { value: "90" } });
    await act(async () => fireEvent.click(screen.getByText("Save calibration")));
    const post = fetch.mock.calls.find(([url]) => url === "api/calibrations/3f2a91c0aaaaaaaa/place")!;
    expect(JSON.parse(post[1]!.body as string)).toEqual({ dx_mm: 500, dy_mm: 0, theta_deg: 90, reanchor: false });
    expect(await screen.findByTestId("placement-saved")).toHaveTextContent(
      "dotbot swarm calibrate-lh2 push 7c0d5e12 --site arena",
    );
  });

  it("refuses to move a corner-collected calibration until Re-anchor is ticked", async () => {
    placementServer(false);
    await loadIt();
    expect(await screen.findByTestId("placement-refused")).toBeInTheDocument();
    expect(screen.getByText("Save calibration")).toBeDisabled();
    fireEvent.click(screen.getByLabelText("re-anchor"));
    expect(screen.getByText("Save calibration")).not.toBeDisabled();
  });

  it("drags the calibration on the snap grid", async () => {
    placementServer(true);
    await loadIt();
    const body = await screen.findByTestId("placement-body");
    const canvas = screen.getByTestId("site-canvas");
    fireEvent.pointerDown(body, { button: 0, clientX: 300, clientY: 300, pointerId: 1 });
    fireEvent.pointerMove(canvas, { clientX: 337, clientY: 300, pointerId: 1 });
    fireEvent.pointerUp(canvas, { clientX: 337, clientY: 300, pointerId: 1 });
    const dx = Number((screen.getByLabelText("shift x (mm)") as HTMLInputElement).value);
    expect(dx % 50).toBe(0);
    expect(dx).toBeGreaterThan(0);
  });
});

describe("SiteEditor comfort", () => {
  const xOf = () => Number((screen.getByLabelText("x") as HTMLInputElement).value);

  it("undoes and redoes an edit, a field's typing as one step", async () => {
    server(loaded(), { status: 200, body: {} });
    render(<SiteEditor />);
    await screen.findByLabelText("show dev-corner");
    fireEvent.click(screen.getByLabelText("show dev-corner").parentElement!);
    fireEvent.change(screen.getByLabelText("x"), { target: { value: "9" } });
    fireEvent.change(screen.getByLabelText("x"), { target: { value: "95" } });
    fireEvent.change(screen.getByLabelText("x"), { target: { value: "950" } });
    expect(xOf()).toBe(950);
    fireEvent.click(screen.getByText("Undo"));
    expect(xOf()).toBe(1000);
    expect(screen.getByText("Undo")).toBeDisabled();
    fireEvent.click(screen.getByText("Redo"));
    expect(xOf()).toBe(950);
    fireEvent.keyDown(window, { key: "z", ctrlKey: true });
    expect(xOf()).toBe(1000);
    fireEvent.keyDown(window, { key: "z", ctrlKey: true, shiftKey: true });
    expect(xOf()).toBe(950);
  });

  it("nudges the selected area by a snap step, Alt by a millimetre", async () => {
    server(loaded(), { status: 200, body: {} });
    render(<SiteEditor />);
    await screen.findByLabelText("show dev-corner");
    fireEvent.click(screen.getByLabelText("show dev-corner").parentElement!);
    fireEvent.keyDown(window, { key: "ArrowRight" });
    expect(xOf()).toBe(1050);
    fireEvent.keyDown(window, { key: "ArrowLeft", altKey: true });
    expect(xOf()).toBe(1049);
    fireEvent.keyDown(window, { key: "ArrowLeft", shiftKey: true });
    expect(xOf()).toBe(549);
    fireEvent.click(screen.getByText("Undo"));
    expect(xOf()).toBe(1000);
  });

  it("offers a backdrop only for what the site has, and draws it when ticked", async () => {
    const fetch = vi.fn(async (url: string) => {
      const json = (status: number, body: unknown) =>
        new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
      if (url === "api/site") return json(200, loaded());
      if (url === "api/backdrops")
        return json(200, {
          calibrations: [
            {
              id8: "b54cb043",
              tag: "",
              created_at: "",
              placements: [[[0, 0], [2000, 0], [2000, 2000], [0, 2000]]],
              centres: [],
            },
          ],
          cameras: [],
        });
      return json(404, { detail: "no" });
    });
    vi.stubGlobal("fetch", fetch);
    render(<SiteEditor />);
    const box = await screen.findByLabelText("backdrop LH2 b54cb043");
    expect(screen.queryByTestId("backdrop-calibration-b54cb043")).toBeNull();
    fireEvent.click(box);
    expect(screen.getByTestId("backdrop-calibration-b54cb043")).toBeInTheDocument();
  });
});
