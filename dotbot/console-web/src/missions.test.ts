import { describe, expect, it } from "vitest";

import { deriveMissions } from "./TestbedRail";
import { PlannedMission, UnifiedBot } from "./types";

const bot = (id: string, over: Partial<UnifiedBot> = {}): UnifiedBot => ({
  id,
  state: "Running",
  position: { x: 0, y: 0 },
  heading: null,
  battery: 3.9,
  led: null,
  deviceType: "DotBotV3",
  application: 0,
  drivable: true,
  nav: "drive",
  waypoints: [],
  trail: [],
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
