import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SiteCard } from "./SiteCard";
import type { Site } from "./types";

const SITE: Site = {
  name: "inria-2lh",
  anchor: "",
  extent_mm: [1060, 1220],
  areas: [],
  field: null,
  calibration: { id: "4640cfde014c7232", tag: "inria-hil-r3-inria-2lh", created_at: "", placements: [] },
};

describe("the Site card in Layers", () => {
  it("names the site and the served calibration, and opens the editor in its own tab", () => {
    render(<SiteCard site={SITE} />);
    expect(screen.getByTestId("site-card").textContent).toContain("inria-2lh");
    expect(screen.getByTestId("calibration-chip").textContent).toContain("SERVING4640cfde");
    const link = screen.getByTestId("edit-site");
    expect(link.getAttribute("href")).toBe("/controller/site-editor/");
    expect(link.getAttribute("target")).toBe("dotbot-site-editor");
  });

  it("says when nothing is served", () => {
    render(<SiteCard site={{ ...SITE, calibration: null }} />);
    expect(screen.getByTestId("calibration-chip").textContent).toContain("NO CALIBRATION");
  });
});
