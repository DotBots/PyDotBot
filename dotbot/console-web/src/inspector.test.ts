import { describe, expect, it } from "vitest";

import { formatLh2, formatUptime, infoText } from "./Inspector";
import { SwarmitNode, UnifiedBot } from "./types";

const bot = (over: Partial<UnifiedBot> = {}): UnifiedBot => ({
  id: "217B829760EBA3E0",
  state: "Running",
  position: { x: 1552, y: 267 },
  heading: null,
  battery: 2.58,
  led: null,
  deviceType: "DotBotV3",
  application: 0,
  drivable: true,
  nav: "drive",
  waypoints: [],
  trail: [],
  image: null,
  resetCause: null,
  crashed: false,
  swarmit: null,
  ...over,
});

const node = (over: Partial<SwarmitNode> = {}): SwarmitNode => ({
  device: "DotBotV3",
  status: "Running",
  battery: 2580,
  pos_x: 1552,
  pos_y: 267,
  ...over,
});

describe("formatUptime", () => {
  it("matches swarmit's format_uptime", () => {
    expect(formatUptime(45)).toBe("45s");
    expect(formatUptime(336)).toBe("5m 36s");
    expect(formatUptime(7444)).toBe("2h 04m 04s");
  });
});

describe("formatLh2", () => {
  // A bot that never answered and one reporting zero homographies are
  // different facts: one is re-provisioned, the other is a pending fetch.
  it("separates never-answered from uncalibrated", () => {
    expect(formatLh2(bot({ swarmit: null }))).toBe("unknown (no device info)");
    expect(formatLh2(bot({ swarmit: node({ info: null }) }))).toBe("unknown (no device info)");
  });

  it("reads the homography count and flags", () => {
    const info = { bl_version: "", net_version: "", boot_count: 0, uptime_s: 0, image_name: "", image_version: "", image_digest: "" };
    const withInfo = (over: object) => bot({ swarmit: node({ info: { ...info, ...over } }) });
    expect(formatLh2(withInfo({ lh2_homography_count: 0 }))).toBe("uncalibrated");
    expect(formatLh2(withInfo({ lh2_homography_count: 1, lh2_flags: 3 }))).toBe(
      "1 basestation (valid, from flash)",
    );
    expect(formatLh2(withInfo({ lh2_homography_count: 2, lh2_flags: 1 }))).toBe(
      "2 basestations (valid)",
    );
  });
});

describe("infoText", () => {
  it("is plain text carrying the identity and the reset cause", () => {
    const t = infoText(
      bot({ resetCause: "stopped", swarmit: node({ reset_reason: 1 << 25, fault: 0 }) }),
    );
    expect(t.split("\n")[0]).toBe("217B829760EBA3E0");
    expect(t).toContain("Last reset        stopped");
    expect(t).toContain("reset_reason    0x02000000");
    expect(t).toContain("fault           NoFault");
  });

  it("spells out the fault registers only when a fault was latched", () => {
    const clean = infoText(bot({ swarmit: node({ reset_reason: 0, fault: 0 }) }));
    expect(clean).not.toContain("cfsr");
    const crashed = infoText(
      bot({ crashed: true, swarmit: node({ reset_reason: 2, fault: 1, pc: 0x2000abcd }) }),
    );
    expect(crashed).toContain("cfsr");
    expect(crashed).toContain("pc              0x2000abcd");
  });
});
