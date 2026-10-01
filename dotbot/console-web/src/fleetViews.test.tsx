import React from "react";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  ageLabel,
  appLabel,
  areaLabel,
  calibrationDiffers,
  detailText,
  FleetContext,
  firmwareTooOld,
  headingLabel,
  linkLabel,
  sandboxLabel,
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
  info_version: 3,
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
  lastSeen: 1000,
  ...over,
});

const ctx: FleetContext = { calibrationId: "abcd1234ffff", site, now: 1000 };

describe("botFacts", () => {
  it("names the app, its version and a short digest", () => {
    expect(appLabel(bot("A"))).toBe("dotbot 1.4 · 3f9a21c0");
    expect(appLabel(bot("A", { swarmit: null }))).toBe("");
  });

  it("collapses matching bootloader and net core versions", () => {
    expect(sandboxLabel(bot("A"))).toBe("1.25.0");
    const split = bot("A", { swarmit: { ...bot("A").swarmit!, info: info({ net_version: "1.24.0" }) } });
    expect(sandboxLabel(split)).toBe("bl 1.25.0 · net 1.24.0");
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
    expect(linkLabel(bot("A"), 1000)).toBe("Live");
    expect(linkLabel(bot("A", { link: "stale", lastSeen: 988 }), 1000)).toBe("Stale 12 s");
    expect(linkLabel(bot("A", { link: "unknown", lastSeen: 1000 }), 1000)).toBe("Swarmit only");
  });

  it("lists the facts and warnings for a tooltip", () => {
    const old = bot("A", { swarmit: { ...bot("A").swarmit!, info: info({ info_version: 2 }) } });
    const text = detailText(old, ctx);
    expect(text).toContain("Position: 1200, 800 mm");
    expect(text).toContain("Area: field");
    expect(text).toContain("! firmware too old");
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

  it("shows the operator's columns and flags the robot to reflash", () => {
    renderList();
    for (const h of ["App", "Sandbox fw", "LH2 cal", "Position", "Heading", "Area", "Link"]) {
      expect(screen.getByRole("columnheader", { name: new RegExp(`^${h}`) })).toBeTruthy();
    }
    const rows = screen.getAllByRole("row").slice(1);
    expect(within(rows[1]).getByText("reflash")).toBeTruthy();
    expect(within(rows[0]).queryByText("reflash")).toBeNull();
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
  afterEach(cleanup);

  it("carries position, app and warning badges on each card", () => {
    const other = bot("BBBB000000000001", {
      swarmit: { ...bot("A").swarmit!, info: info({ lh2_calibration_id: "0000" }) },
    });
    render(<GridView bots={[other]} selection={new Set()} onSelect={() => {}} ctx={ctx} />);
    expect(screen.getByText(/1200, 800 mm · 92° · field/)).toBeTruthy();
    expect(screen.getByText("dotbot")).toBeTruthy();
    expect(screen.getByText("cal differs")).toBeTruthy();
  });
});
