import { describe, expect, it } from "vitest";

import { formatLh2, formatUptime, infoText } from "./Inspector";
import { SwarmitNode, UnifiedBot } from "./types";

const bot = (over: Partial<UnifiedBot> = {}): UnifiedBot => ({
  id: "217B829760EBA3E0",
  state: "Running",
  link: "active",
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
  severity: "normal",
  batteryPct: null,
  batteryLevel: null,
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

  it("renders the summary swarmit computed, verbatim", () => {
    const info = { bl_version: "", net_version: "", boot_count: 0, uptime_s: 0, image_name: "", image_version: "", image_digest: "" };
    const withInfo = (over: object) => bot({ swarmit: node({ info: { ...info, ...over } }) });
    expect(formatLh2(withInfo({ lh2_summary: "uncalibrated" }))).toBe("uncalibrated");
    expect(formatLh2(withInfo({ lh2_summary: "2 basestations (valid, from flash)" }))).toBe(
      "2 basestations (valid, from flash)",
    );
  });
});

describe("infoText", () => {
  it("is plain text carrying the identity and the reset cause", () => {
    const t = infoText(
      bot({ resetCause: "stopped", swarmit: node({ reset_reason: 1 << 25, fault: 0, fault_name: "NoFault" }) }),
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
      bot({ severity: "crashed", swarmit: node({ reset_reason: 2, fault: 1, pc: 0x2000abcd }) }),
    );
    expect(crashed).toContain("cfsr");
    expect(crashed).toContain("pc              0x2000abcd");
  });

  // A watchdog timeout raises no fault, so cfsr/sfsr are structurally zero.
  // Printing them invites decoding a status that was never populated - the
  // CLI suppresses them for exactly this case, and so must this.
  it("hides the fault registers for a watchdog timeout, but keeps pc and lr", () => {
    const hung = infoText(
      bot({
        severity: "hung",
        resetCause: "hung (watchdog0 pc=0x00010230)",
        swarmit: node({
          reset_reason: 0x02,
          fault: 3, // WatchdogTimeout
          fault_name: "WatchdogTimeout",
          cfsr: 0,
          sfsr: 0,
          pc: 0x00010230,
          lr: 0x0001022b,
        }),
      }),
    );

    expect(hung).not.toContain("cfsr");
    expect(hung).not.toContain("sfsr");
    // pc and lr are the whole answer for this failure mode.
    expect(hung).toContain("pc              0x00010230");
    expect(hung).toContain("lr              0x0001022b");
    expect(hung).toContain("fault           WatchdogTimeout");
  });
});
