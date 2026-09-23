import { describe, expect, it } from "vitest";

import { BotPose, CameraDetection, PyDotBot, SwarmitNode } from "./types";
import {
  deriveLink,
  derivePose,
  deriveState,
  merge,
  severityOf,
  withDetection,
} from "./useFleet";

const pose = (over: Partial<BotPose> = {}): BotPose => ({
  heading_deg: 90,
  heading_source: "travel",
  photodiode: { x: 0, y: 0 },
  axle: { x: 0, y: 0 },
  centre: { x: 0, y: 0 },
  nose: { x: 0, y: 0 },
  led: { x: 0, y: 0 },
  outline: [],
  ...over,
});

const py = (over: Partial<PyDotBot> = {}): PyDotBot => ({
  address: "badcafe111111111",
  application: 0,
  status: 0,
  ...over,
});

const sw = (over: Partial<SwarmitNode> = {}): SwarmitNode => ({
  device: "DotBotV3",
  status: "Running",
  battery: 3900,
  pos_x: 100,
  pos_y: 200,
  ...over,
});

describe("deriveState (the sandbox axis)", () => {
  it("reports only what swarmit says, ignoring the control plane", () => {
    // The two axes are independent: a bot can be mid-Programming and unheard
    // at the same time, and the old single state hid the sandbox in that case.
    expect(deriveState(sw({ status: "Programming" }))).toBe("Programming");
    for (const s of ["Running", "Programming", "Bootloader", "Stopping", "Resetting"]) {
      expect(deriveState(sw({ status: s }))).toBe(s);
    }
  });

  it("has no sandbox state for a bot swarmit does not know", () => {
    // Saying "Running" here claimed a sandbox a bare-mode bot does not have.
    expect(deriveState(undefined)).toBeNull();
  });

  it("does not invent a state for a lifecycle value it does not know", () => {
    expect(deriveState(sw({ status: "Off" }))).toBeNull();
  });
});

describe("deriveLink (the control-plane axis)", () => {
  it("maps PyDotBot's DotBotStatus", () => {
    expect(deriveLink(py({ status: 0 }))).toBe("active");
    expect(deriveLink(py({ status: 1 }))).toBe("inactive");
    expect(deriveLink(py({ status: 2 }))).toBe("lost");
  });

  it("is unknown for a bot the control plane has never seen", () => {
    expect(deriveLink(undefined)).toBe("unknown");
  });
});

describe("the two axes stay independent", () => {
  it("keeps the sandbox state on a bot the control plane has lost", () => {
    const [b] = merge({ aaaa: py({ address: "aaaa", status: 2 }) }, { aaaa: sw({ status: "Programming" }) });
    expect(b.state).toBe("Programming");
    expect(b.link).toBe("lost");
    expect(b.drivable).toBe(false);
  });

  it("drives a bare-mode bot that has no sandbox at all", () => {
    const [b] = merge({ aaaa: py({ address: "aaaa", status: 0 }) }, {});
    expect(b.state).toBeNull();
    expect(b.link).toBe("active");
    expect(b.drivable).toBe(true);
  });

  it("will not drive a swarmit bot the control plane cannot reach", () => {
    const [b] = merge({}, { aaaa: sw({ status: "Running" }) });
    expect(b.link).toBe("unknown");
    expect(b.drivable).toBe(false);
  });
});

describe("merge", () => {
  it("unions both planes and sorts by id", () => {
    const bots = merge(
      { bbbb: py({ address: "bbbb" }) },
      { aaaa: sw(), bbbb: sw() },
    );
    expect(bots.map((b) => b.id)).toEqual(["aaaa", "bbbb"]);
  });

  it("prefers the controller position, falls back to swarmit", () => {
    const [a] = merge(
      { a: py({ address: "a", lh2_position: { x: 1, y: 2 } }) },
      { a: sw() },
    );
    expect(a.position).toEqual({ x: 1, y: 2 });
    const [b] = merge({}, { b: sw() });
    expect(b.position).toEqual({ x: 100, y: 200 });
  });

  // swarmit reports (0, 0) for a bot it has never located, and a real fix
  // cannot land on the origin - drawing it puts the whole uncalibrated fleet
  // in one arena corner and reads as a real cluster.
  it("does not treat swarmit's (0, 0) no-fix sentinel as a position", () => {
    const [a] = merge({}, { a: sw({ pos_x: 0, pos_y: 0 }) });
    expect(a.position).toBeNull();
    const [b] = merge({}, { b: sw({ pos_x: 0, pos_y: 400 }) });
    expect(b.position).toEqual({ x: 0, y: 400 });
  });

  it("treats direction -1000 (unknown) as no heading", () => {
    const [a] = merge({ a: py({ address: "a", direction: -1000 }) }, {});
    expect(a.heading).toBeNull();
    const [b] = merge({ b: py({ address: "b", direction: 45, lh2_position: { x: 1, y: 1 } }) }, {});
    expect(b.heading).toBe(45);
  });

  it("converts a swarmit-only battery from mV to V", () => {
    const [a] = merge({}, { a: sw({ battery: 3900 }) });
    expect(a.battery).toBeCloseTo(3.9);
  });

  it("only an active Running control-plane bot is drivable", () => {
    const [a] = merge({ a: py({ address: "a" }) }, {});
    expect(a.drivable).toBe(true);
    // swarmit-only (e.g. sitting in the bootloader): never drivable
    const [b] = merge({}, { b: sw({ status: "Bootloader" }) });
    expect(b.drivable).toBe(false);
    // known to the controller but flashing right now: not drivable
    const [c] = merge(
      { c: py({ address: "c" }) },
      { c: sw({ status: "Programming" }) },
    );
    expect(c.drivable).toBe(false);
  });

  it("maps firmware AUTO mode to nav=auto", () => {
    const [a] = merge({ a: py({ address: "a", mode: 1 }) }, {});
    expect(a.nav).toBe("auto");
    const [b] = merge({ b: py({ address: "b", mode: 0 }) }, {});
    expect(b.nav).toBe("drive");
  });
});

describe("severityOf", () => {
  const node = (over: Partial<SwarmitNode>): SwarmitNode => ({
    device: "DotBotV3",
    status: "Running",
    battery: 3900,
    pos_x: 0,
    pos_y: 0,
    ...over,
  });

  it("renders swarmit's tier rather than re-deriving it", () => {
    expect(severityOf(node({ reset_severity: "crashed" }))).toBe("crashed");
    expect(severityOf(node({ reset_severity: "hung" }))).toBe("hung");
    expect(severityOf(node({ reset_severity: "normal" }))).toBe("normal");
  });

  it("is normal when swarmit said nothing, so a badge needs evidence", () => {
    expect(severityOf(undefined)).toBe("normal");
    expect(severityOf(node({}))).toBe("normal");
    expect(severityOf(node({ reset_severity: "something-new" }))).toBe("normal");
  });
});

describe("merge takes the reset label from the server", () => {
  it("passes reset_cause through and reports it missing rather than guessing", () => {
    const [a] = merge({}, { A: { device: "DotBotV3", status: "Running", battery: 3900, pos_x: 0, pos_y: 0, reset_cause: "stopped" } });
    expect(a.resetCause).toBe("stopped");
    const [b] = merge({}, { B: { device: "DotBotV3", status: "Running", battery: 3900, pos_x: 0, pos_y: 0 } });
    expect(b.resetCause).toBeNull();
  });
});

describe("withDetection (one camera's latest view of its own area)", () => {
  const detection = (area: string, sequence: number): CameraDetection => ({
    area,
    camera_id: "7b21c0d9f3a1",
    sequence,
    timestamp: 1758100000.123,
    status: "none",
    candidates: 0,
    elapsed_ms: 4.2,
  });

  it("keys by area", () => {
    expect(withDetection({}, detection("dev-corner", 1))).toEqual({
      "dev-corner": detection("dev-corner", 1),
    });
  });

  it("replaces the area's own, and leaves the other areas alone", () => {
    const previous = {
      "dev-corner": detection("dev-corner", 1),
      annex: detection("annex", 9),
    };
    const next = withDetection(previous, detection("dev-corner", 2));
    expect(next["dev-corner"].sequence).toBe(2);
    expect(next.annex.sequence).toBe(9);
    expect(previous["dev-corner"].sequence).toBe(1);
  });
});

describe("the body the controller expanded the fix into", () => {
  const at = { x: 1500, y: 300 };

  it("rides with the controller's position", () => {
    const p = pose();
    expect(derivePose(py({ lh2_position: at, pose: p }), sw(), "active").pose).toBe(p);
  });

  it("loses its heading when the bot is placed from swarmit", () => {
    // swarmit reports a point and no heading: keeping the controller's would
    // put a board on a stale orientation at a fresh position.
    const heard = py({
      lh2_position: at,
      pose: pose({ photodiode: at, centre: { x: 1500, y: 271 }, reach_mm: 89, core_mm: 18 }),
    });
    const placed = derivePose(heard, sw(), "lost").pose!;
    expect(placed.heading_source).toBe("none");
    expect(placed.photodiode).toEqual({ x: 100, y: 200 });
    expect(placed.centre).toEqual({ x: 100, y: 171 });
    expect(placed).toMatchObject({ reach_mm: 89, core_mm: 18 });
  });

  it("is a bare point from swarmit when the controller never sized the bot", () => {
    expect(derivePose(py({ status: 2 }), sw(), "lost").pose).toBeNull();
    expect(derivePose(undefined, sw({ status: "Bootloader" }), "unknown").pose).toBeNull();
  });

  it("is dropped with the position it belongs to", () => {
    expect(derivePose(py({ pose: pose() }), sw({ pos_x: 0, pos_y: 0 }), "active").pose).toBeNull();
  });

  it("reaches the merged bot", () => {
    const p = pose();
    const [b] = merge(
      { aaaa: py({ address: "aaaa", lh2_position: at, pose: p }) },
      { aaaa: sw({ status: "Running" }) },
    );
    expect(b.pose).toBe(p);
  });

  it("is carried for a bot that reported no heading, flagged as such", () => {
    // The controller always expands a valid fix; the flag is what says the
    // orientation is unknown, and the console keys on that rather than on the
    // field being absent.
    const p = pose({ heading_source: "none", heading_deg: 0 });
    const [b] = merge(
      { aaaa: py({ address: "aaaa", direction: -1000, lh2_position: at, pose: p }) },
      { aaaa: sw({ status: "Running" }) },
    );
    expect(b.heading).toBeNull();
    expect(b.pose?.heading_source).toBe("none");
  });
});

describe("derivePose (whose pose is live)", () => {
  const stale = { x: 1500, y: 300 };

  it("takes the controller's while its link is active", () => {
    expect(derivePose(py({ lh2_position: stale }), sw(), "active").position).toEqual(stale);
  });

  it("takes swarmit's once the controller stops hearing the app", () => {
    for (const link of ["inactive", "lost"] as const) {
      expect(derivePose(py({ lh2_position: stale }), sw(), link).position).toEqual({ x: 100, y: 200 });
    }
  });

  it("takes swarmit's for a bot in its bootloader the merge still has an app record for", () => {
    const [b] = merge(
      { aaaa: py({ address: "aaaa", status: 2, lh2_position: stale }) },
      { aaaa: sw({ status: "Bootloader", pos_x: 700, pos_y: 800 }) },
    );
    expect(b.position).toEqual({ x: 700, y: 800 });
    expect(b.pose).toBeNull();
  });

  it("keeps a bootloader bot's size from the controller's last pose", () => {
    const [b] = merge(
      { aaaa: py({ address: "aaaa", status: 1, lh2_position: stale, pose: pose({ photodiode: stale, reach_mm: 89 }) }) },
      { aaaa: sw({ status: "Bootloader", pos_x: 700, pos_y: 800 }) },
    );
    expect(b.pose).toMatchObject({ heading_source: "none", photodiode: { x: 700, y: 800 }, reach_mm: 89 });
  });

  it("keeps the controller's stale position when swarmit has never located the bot", () => {
    expect(derivePose(py({ lh2_position: stale }), sw({ pos_x: 0, pos_y: 0 }), "lost").position).toEqual(stale);
  });

  it("takes the controller's heading only with its position", () => {
    const heard = py({ lh2_position: stale, direction: 90 });
    expect(derivePose(heard, sw(), "active").heading).toBe(90);
    expect(derivePose(heard, sw(), "lost")).toEqual({
      position: { x: 100, y: 200 },
      heading: null,
      pose: null,
    });
    expect(derivePose(heard, sw({ pos_x: 0, pos_y: 0 }), "lost").heading).toBe(90);
    const unplaced = py({ direction: 90 });
    expect(derivePose(unplaced, sw({ pos_x: 0, pos_y: 0 }), "active")).toEqual({
      position: null,
      heading: null,
      pose: null,
    });
  });

  it("does not draw swarmit's unlocated origin", () => {
    expect(derivePose(undefined, sw({ pos_x: 0, pos_y: 0 }), "unknown").position).toBeNull();
  });
});
