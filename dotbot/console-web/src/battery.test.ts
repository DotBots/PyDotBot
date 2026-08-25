import { describe, expect, it } from "vitest";

import { batteryColor, batteryPct } from "./viewChrome";

// The scale is a robot fact and lives in swarmit, per device type. These cover
// that the console renders what it is served and degrades visibly, not
// confidently, for a bot swarmit does not know.
describe("battery rendering", () => {
  it("renders the served percentage verbatim", () => {
    expect(batteryPct({ batteryPct: 57, battery: 2.3 })).toBe(57);
    expect(batteryPct({ batteryPct: 0, battery: 0.6 })).toBe(0);
  });

  it("clamps a nonsense served value rather than overflowing the bar", () => {
    expect(batteryPct({ batteryPct: 140, battery: 3.0 })).toBe(100);
    expect(batteryPct({ batteryPct: -5, battery: 0 })).toBe(0);
  });

  it("falls back only for a bot swarmit does not know", () => {
    expect(batteryPct({ batteryPct: null, battery: 3.0 })).toBe(100);
    expect(batteryPct({ batteryPct: null, battery: 1.5 })).toBe(50);
  });

  it("colours by the served band, matching the bootloader LED", () => {
    expect(batteryColor({ batteryLevel: "full" })).toBe("var(--s-Full)");
    expect(batteryColor({ batteryLevel: "ok" })).toBe("var(--s-Running)");
    expect(batteryColor({ batteryLevel: "low" })).toBe("var(--s-Stopping)");
  });

  it("shows no band when there is none to show", () => {
    expect(batteryColor({ batteryLevel: null })).toBe("var(--muted)");
  });
});
