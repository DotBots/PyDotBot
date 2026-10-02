import React from "react";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ageLabel,
  appLabel,
  areaLabel,
  calibrationDiffers,
  detailText,
  FleetContext,
  firmwareTooOld,
  headingLabel,
  bootloaderLabel,
  reportsDetail,
  reportsLabel,
} from "./botFacts";
import { GridView } from "./GridView";
import { ListView } from "./ListView";
import type { Site, SwarmitDeviceInfo, UnifiedBot } from "./types";

const site: Site = {
  name: "lab",
  anchor: "top-left",
  extent_mm: [4000, 4000],
  areas: [
    { x: 0, y: 0, w: 3000, h: 3000, name: "field", role: "field" },
    { x: 0, y: 0, w: 500, h: 500, name: "bench", role: "corner" },
  ],
};

const info = (over: Partial<SwarmitDeviceInfo> = {}): SwarmitDeviceInfo => ({
  info_version: 4,
  bl_version: "1.25.0",
  net_version: "1.25.0",
  boot_count: 3,
  uptime_s: 60,
  image_name: "dotbot",
  image_version: "1.4",
  image_digest: "3f9a21c0deadbeef",
  lh2_calibration_id: "abcd1234ffff",
  ...over,
});

const bot = (id: string, over: Partial<UnifiedBot> = {}): UnifiedBot => ({
  id,
  state: "Running",
  link: "active",
  position: { x: 1200, y: 800 },
  heading: null,
  battery: 2.9,
  led: null,
  deviceType: "DotBotV3",
  application: 0,
  pose: { heading_deg: 92.4, heading_source: "ekf" } as UnifiedBot["pose"],
  drivable: true,
  nav: "drive",
  waypoints: [],
  trail: [],
  image: null,
  resetCause: null,
  severity: "normal",
  batteryPct: 80,
  batteryLevel: "ok",
  swarmit: { device: "DotBotV3", status: "Running", battery: 2900, pos_x: 0, pos_y: 0, info: info() },
  lastReport: 1000,
  ...over,
});

const ctx: FleetContext = { calibrationId: "abcd1234ffff", site, now: 1000 };

describe("botFacts", () => {
  it("names the app, its version and a short digest", () => {
    expect(appLabel(bot("A"))).toBe("dotbot 1.4 · 3f9a21c0");
    expect(appLabel(bot("A", { swarmit: null }))).toBe("");
  });

  it("names the bootloader version, and the net core's only when it differs", () => {
    expect(bootloaderLabel(bot("A"))).toBe("1.25.0");
    const split = bot("A", { swarmit: { ...bot("A").swarmit!, info: info({ net_version: "1.24.0" }) } });
    expect(bootloaderLabel(split)).toBe("1.25.0 · net 1.24.0");
    expect(bootloaderLabel(bot("A", { swarmit: null }))).toBe("");
  });

  it("flags firmware too old for the controller's calibrations, not a calibration mismatch", () => {
    const old = bot("A", { swarmit: { ...bot("A").swarmit!, info: info({ info_version: 2, lh2_calibration_id: "" }) } });
    expect(firmwareTooOld(old)).toBe(true);
    expect(calibrationDiffers(old, ctx.calibrationId)).toBe(false);
    expect(firmwareTooOld(bot("A", { swarmit: null }))).toBe(false);
  });

  it("flags a calibration other than the served one, and none when nothing is served", () => {
    const other = bot("A", { swarmit: { ...bot("A").swarmit!, info: info({ lh2_calibration_id: "0000" }) } });
    expect(calibrationDiffers(other, ctx.calibrationId)).toBe(true);
    expect(calibrationDiffers(bot("A"), ctx.calibrationId)).toBe(false);
    expect(calibrationDiffers(other, "")).toBe(false);
  });

  it("picks the smallest area the robot stands in", () => {
    expect(areaLabel(bot("A"), site)).toBe("field");
    expect(areaLabel(bot("A", { position: { x: 100, y: 100 } }), site)).toBe("bench");
    expect(areaLabel(bot("A", { position: { x: 3900, y: 3900 } }), site)).toBe("");
  });

  it("says the heading and its source, and nothing without one", () => {
    expect(headingLabel(bot("A"))).toBe("92° ekf");
    expect(headingLabel(bot("A", { pose: null }))).toBe("");
  });

  it("adds how long a robot has been silent once it slips", () => {
    expect(ageLabel(990, 1000)).toBe("10 s");
    expect(ageLabel(1000 - 600, 1000)).toBe("10 min");
    expect(reportsLabel(bot("A"), 1000)).toBe("Reporting");
    expect(reportsLabel(bot("A", { link: "stale", lastReport: 988 }), 1000)).toBe("Late 12 s");
    expect(reportsLabel(bot("A", { link: "lost", lastReport: 760 }), 1000)).toBe("Silent 4 min");
    expect(reportsLabel(bot("A", { link: "unknown", lastReport: null }), 1000)).toBe("No reports");
  });

  it("spells a reports label out down to the REST status behind it", () => {
    expect(reportsDetail(bot("A", { link: "stale", lastReport: 994 }), 1000)).toMatch(
      /^Late\. Last report 6 s ago.*\(status 1, stale\)$/,
    );
    expect(reportsDetail(bot("A", { link: "lost", lastReport: 900 }), 1000)).toContain("Swarmit still hears");
    expect(reportsDetail(bot("A", { link: "unknown" }), 1000)).toContain("not in GET /controller/dotbots");
    expect(reportsDetail(bot("A", { link: "lost", lastReport: null }), 1000)).toMatch(/^Silent\. Last report unknown\./);
  });

  it("lists the facts and warnings for a tooltip", () => {
    const old = bot("A", { swarmit: { ...bot("A").swarmit!, info: info({ info_version: 2 }) } });
    const text = detailText(old, ctx);
    expect(text).toContain("Position: 1200, 800 mm");
    expect(text).toContain("Area: field");
    expect(text).toContain("Reports: Reporting");
    expect(text).toContain("! bootloader too old");
  });
});

describe("ListView", () => {
  beforeEach(() => window.localStorage.clear());
  afterEach(cleanup);

  const fleet = [
    bot("AAAA000000000001", { battery: 2.5 }),
    bot("AAAA000000000002", {
      battery: 2.1,
      swarmit: { ...bot("A").swarmit!, info: info({ info_version: 2 }) },
    }),
  ];
  const renderList = () =>
    render(<ListView bots={fleet} selection={new Set()} onSelect={() => {}} ctx={ctx} />);

  it("shows the operator's columns and flags the robot whose bootloader is too old", () => {
    renderList();
    for (const h of ["Reports", "App", "Bootloader", "LH2 cal", "Position", "Heading", "Area"]) {
      expect(screen.getByRole("columnheader", { name: new RegExp(`^${h}`) })).toBeTruthy();
    }
    const rows = screen.getAllByRole("row").slice(1);
    expect(within(rows[1]).getByText("too old")).toBeTruthy();
    expect(within(rows[0]).queryByText("too old")).toBeNull();
  });

  it("draws the heading as a glyph beside its degrees, and an empty one without a heading", () => {
    render(
      <ListView
        bots={[bot("AAAA000000000001"), bot("AAAA000000000002", { pose: null })]}
        selection={new Set()}
        onSelect={() => {}}
        ctx={ctx}
      />,
    );
    expect(screen.getByRole("img", { name: "heading 92° ekf" })).toBeTruthy();
    expect(screen.getByRole("img", { name: "no heading yet" })).toBeTruthy();
    expect(screen.getByText("92°")).toBeTruthy();
  });

  it("sorts by a column and hides one, remembering it", () => {
    renderList();
    fireEvent.click(screen.getByRole("columnheader", { name: /^Battery/ }));
    expect(screen.getAllByRole("row")[1].textContent).toContain("AAAA000000000002");
    fireEvent.click(screen.getByText("Columns"));
    fireEvent.click(screen.getByRole("checkbox", { name: "Heading" }));
    expect(screen.queryByRole("columnheader", { name: /^Heading/ })).toBeNull();
    cleanup();
    renderList();
    expect(screen.queryByRole("columnheader", { name: /^Heading/ })).toBeNull();
  });
});

describe("GridView", () => {
  beforeEach(() => window.localStorage.clear());
  afterEach(cleanup);

  const other = bot("BBBB000000000001", {
    swarmit: { ...bot("A").swarmit!, info: info({ lh2_calibration_id: "0000", net_version: "1.24.0" }) },
  });
  const late = bot("BBBB000000000002", { link: "stale", lastReport: 994 });
  const renderGrid = () =>
    render(<GridView bots={[other, late]} selection={new Set()} onSelect={() => {}} ctx={ctx} />);

  it("starts compact: where it is, its app and bootloader, and only the exceptions", () => {
    renderGrid();
    expect(screen.getAllByText(/1200, 800 mm · field/)).toHaveLength(2);
    expect(screen.getAllByRole("img", { name: "heading 92° ekf" })).toHaveLength(2);
    expect(screen.getAllByText("dotbot")).toHaveLength(2);
    expect(screen.getByText("bl 1.25.0 · net 1.24.0")).toBeTruthy();
    expect(screen.getByText("cal differs")).toBeTruthy();
    expect(screen.getByText("Late 6 s")).toBeTruthy();
    expect(screen.queryByText("Reporting")).toBeNull();
    expect(screen.queryByText("App")).toBeNull();
  });

  it("switches to full cards, which name every fact, and remembers it", () => {
    renderGrid();
    fireEvent.click(screen.getByRole("button", { name: "Full" }));
    expect(screen.getAllByText("App")).toHaveLength(2);
    expect(screen.getByText("Reporting")).toBeTruthy();
    expect(screen.getAllByText("dotbot 1.4 · 3f9a21c0").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/1200, 800 mm · 92° ekf · field/).length).toBeGreaterThan(0);
    expect(screen.getByText("differs")).toBeTruthy();
    cleanup();
    renderGrid();
    expect(screen.getByRole("button", { name: "Full" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("falls back to compact when storage throws", () => {
    const spy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    renderGrid();
    expect(screen.getByRole("button", { name: "Compact" }).getAttribute("aria-pressed")).toBe("true");
    spy.mockRestore();
  });
});
