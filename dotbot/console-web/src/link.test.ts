import { describe, expect, it } from "vitest";

import { fleetSummary, heard, markerOpacity, nobodyHears, rowOpacity } from "./link";
import { LinkState, SwarmitNode } from "./types";

const bot = (link: LinkState, swarmit: SwarmitNode | null = null) => ({ link, swarmit });

describe("link tiers", () => {
  it("still sends commands to a stale robot, not to a lost one", () => {
    expect(heard("active")).toBe(true);
    expect(heard("stale")).toBe(true);
    expect(heard("lost")).toBe(false);
    expect(heard("unknown")).toBe(false);
  });

  it("hides a lost robot only when swarmit does not report it either", () => {
    expect(nobodyHears(bot("lost"))).toBe(true);
    expect(nobodyHears(bot("lost", {} as SwarmitNode))).toBe(false);
    expect(nobodyHears(bot("stale"))).toBe(false);
  });

  it("fades a lost robot swarmit reports no more than a stale one", () => {
    expect(markerOpacity(bot("lost"))).toBeLessThan(markerOpacity(bot("stale")));
    expect(markerOpacity(bot("stale"))).toBeLessThan(1);
    expect(markerOpacity(bot("lost", {} as SwarmitNode))).toBe(markerOpacity(bot("stale")));
    expect(rowOpacity(bot("lost", {} as SwarmitNode))).toBe(rowOpacity(bot("stale")));
  });

  it("counts the fleet by tier, naming only the tiers that hold a robot", () => {
    expect(fleetSummary([bot("active"), bot("active")], false)).toBe("2 bots");
    expect(fleetSummary([bot("active"), bot("stale"), bot("lost"), bot("lost")], false)).toBe(
      "2 bots · 1 stale · 2 lost (hidden)",
    );
    expect(fleetSummary([bot("active"), bot("lost")], true)).toBe("1 bot · 1 lost");
  });
});
