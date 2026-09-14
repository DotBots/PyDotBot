import React, { useState } from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MapView } from "./MapView";
import type { Area, Site } from "./types";
import {
  Camera,
  SITE_CAMERA,
  cameraForZoom,
  viewGeom,
  zoomFromSearch,
} from "./zoom";

const ARENA: Area = { x: 0, y: 0, w: 2000, h: 2000, name: "arena" };
const ANNEX: Area = { x: 0, y: 2000, w: 2000, h: 2000, name: "annex" };
const C405: Site = {
  name: "c405-arena",
  anchor: "the arena's top-left corner",
  extent_mm: [2000, 4000],
  areas: [ARENA, ANNEX],
};
const VIEWPORT: Area = { x: -2000, y: -2000, w: 6000, h: 8000 };
const GEOM = viewGeom(900, 600, VIEWPORT);

// The map with a camera over it, zoomed the way App zooms it.
const Harness: React.FC<{ onCam?: (c: Camera) => void }> = ({ onCam }) => {
  const [cam, setCam] = useState<Camera>(SITE_CAMERA);
  return (
    <MapView
      bots={[]}
      viewport={VIEWPORT}
      siteAreas={C405.areas}
      hiddenAreas={new Set()}
      siteExtent={{ x: 0, y: 0, w: 2000, h: 4000, name: C405.name }}
      selection={new Set()}
      layers={{
        batteryBars: true,
        waypoints: true,
        hotSpots: false,
        dotBots: true,
        trails: false,
        crashedOnly: false,
      }}
      plannedMissions={[]}
      cam={cam}
      setCam={setCam}
      onGeom={() => {}}
      onSelect={() => {}}
      onAddWaypoint={() => {}}
      site={C405}
      onZoom={(name) => {
        const next = cameraForZoom(name, C405, VIEWPORT, GEOM);
        if (next) {
          setCam(next);
          onCam?.(next);
        }
      }}
    />
  );
};

describe("the zoom menu", () => {
  it("opens on the fit button and lists the site and every area", () => {
    render(<Harness />);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();

    fireEvent.click(screen.getByTitle("Zoom to"));

    const menu = screen.getByRole("menu", { name: "Zoom to" });
    expect(within(menu).getAllByRole("menuitem").map((i) => i.textContent)).toEqual(
      ["site", "arena", "annex"],
    );
  });

  it("zooms to the area a menu item names, and closes", () => {
    const seen: Camera[] = [];
    render(<Harness onCam={(c) => seen.push(c)} />);
    fireEvent.click(screen.getByTitle("Zoom to"));
    fireEvent.click(screen.getByRole("menuitem", { name: "annex" }));

    expect(seen).toEqual([cameraForZoom("annex", C405, VIEWPORT, GEOM)]);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("goes back to the whole site from the same menu", () => {
    const seen: Camera[] = [];
    render(<Harness onCam={(c) => seen.push(c)} />);
    fireEvent.click(screen.getByTitle("Zoom to"));
    fireEvent.click(screen.getByRole("menuitem", { name: "site" }));
    expect(seen).toEqual([SITE_CAMERA]);
  });
});

describe("an area's name on the map", () => {
  it("zooms to that area when clicked", () => {
    const seen: Camera[] = [];
    render(<Harness onCam={(c) => seen.push(c)} />);
    fireEvent.pointerDown(screen.getByTitle("Zoom to arena"));
    expect(seen).toEqual([cameraForZoom("arena", C405, VIEWPORT, GEOM)]);
  });
});

describe("the ?zoom= preset", () => {
  it("lands on the same camera the menu item would", () => {
    const asked = zoomFromSearch("?zoom=annex", C405);
    const seen: Camera[] = [];
    render(<Harness onCam={(c) => seen.push(c)} />);
    fireEvent.click(screen.getByTitle("Zoom to"));
    fireEvent.click(screen.getByRole("menuitem", { name: "annex" }));

    expect(cameraForZoom(asked!, C405, VIEWPORT, GEOM)).toEqual(seen[0]);
  });
});
