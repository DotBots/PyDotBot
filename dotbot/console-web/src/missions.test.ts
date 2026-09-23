import { describe, expect, it } from "vitest";

import { deriveMissions } from "./TestbedRail";
import {
  canRedoMission,
  lastMissionTargets,
  PlannedMission,
  UnifiedBot,
} from "./types";

const bot = (id: string, over: Partial<UnifiedBot> = {}): UnifiedBot => ({
  id,
  state: "Running",
  link: "active",
  position: { x: 0, y: 0 },
  heading: null,
  battery: 3.9,
  led: null,
  deviceType: "DotBotV3",
  application: 0,
  pose: null,
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

describe("deriveMissions", () => {
  it("keeps a planned mission bound to its bots", () => {
    const planned: PlannedMission[] = [
      {
        key: "aaaa",
        ids: ["aaaa"],
        waypoints: [
          { x: 1, y: 1 },
          { x: 2, y: 2 },
        ],
      },
    ];
    const [m] = deriveMissions([bot("aaaa")], planned);
    expect(m.phase).toBe("planned");
    expect(m.n).toBe(2);
    expect(m.ids).toEqual(["aaaa"]);
  });

  it("drops a planned mission whose bots are gone", () => {
    const planned: PlannedMission[] = [
      { key: "gone", ids: ["gone"], waypoints: [{ x: 1, y: 1 }] },
    ];
    expect(deriveMissions([bot("aaaa")], planned)).toEqual([]);
  });

  it("groups active bots by the mission TAIL (own start prepended)", () => {
    // The controller stores [own-start, ...targets] per bot: same targets,
    // different starts, must land in ONE mission.
    const t = [
      { x: 500, y: 500 },
      { x: 900, y: 900 },
    ];
    const a = bot("aaaa", { nav: "auto", waypoints: [{ x: 1, y: 1 }, ...t] });
    const b = bot("bbbb", { nav: "auto", waypoints: [{ x: 2, y: 2 }, ...t] });
    const missions = deriveMissions([a, b], []);
    expect(missions).toHaveLength(1);
    expect(missions[0].phase).toBe("active");
    expect(missions[0].count).toBe(2);
    expect(missions[0].n).toBe(2);
  });

  it("treats a single-entry waypoint list as the target itself", () => {
    const a = bot("aaaa", { nav: "auto", waypoints: [{ x: 500, y: 500 }] });
    const [m] = deriveMissions([a], []);
    expect(m.n).toBe(1);
  });

  it("ignores bots that are not navigating", () => {
    const a = bot("aaaa", { waypoints: [{ x: 1, y: 1 }] }); // nav=drive
    expect(deriveMissions([a], [])).toEqual([]);
  });
});

describe("the last mission a bot can repeat", () => {
  const targets = [
    { x: 900, y: 900 },
    { x: 1200, y: 300 },
  ];

  it("is the tail the controller kept after the bot arrived", () => {
    const a = bot("aaaa", { waypoints: [{ x: 500, y: 500 }, ...targets] });
    expect(lastMissionTargets(a)).toEqual(targets);
    expect(canRedoMission(a)).toBe(true);
  });

  it("is nothing for a bot that has run none", () => {
    const a = bot("aaaa");
    expect(lastMissionTargets(a)).toEqual([]);
    expect(canRedoMission(a)).toBe(false);
  });

  it("is nothing when a stop left only the bot's own position", () => {
    const a = bot("aaaa", { waypoints: [{ x: 700, y: 700 }] });
    expect(lastMissionTargets(a)).toEqual([]);
    expect(canRedoMission(a)).toBe(false);
  });

  it("is refused while the bot is still under way", () => {
    const a = bot("aaaa", { nav: "auto", waypoints: [{ x: 1, y: 1 }, ...targets] });
    expect(canRedoMission(a)).toBe(false);
  });

  it("is refused for a bot that cannot be driven", () => {
    const a = bot("aaaa", { drivable: false, waypoints: [{ x: 1, y: 1 }, ...targets] });
    expect(canRedoMission(a)).toBe(false);
  });
});
