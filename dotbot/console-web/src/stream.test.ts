import { describe, expect, it } from "vitest";

import { FleetStream, mergePatch } from "./stream";
import { PyDotBot } from "./types";

const bot = (address: string, over: Partial<PyDotBot> = {}): PyDotBot => ({
  address,
  application: 0,
  status: 0,
  trail: [],
  ...over,
});

const hello = { type: "hello", protocol: 1, run: "r1", seq: 4, hz: 10, unacked_hz: 1, window: 2, trail: 3, acks: true, resumed: false } as const;

describe("mergePatch (RFC 7396)", () => {
  it("replaces values, recurses into objects and deletes on null", () => {
    expect(
      mergePatch({ a: 1, b: { c: 2, d: 3 }, e: [1, 2] }, { a: null, b: { c: 5 }, e: [3] }),
    ).toEqual({ b: { c: 5, d: 3 }, e: [3] });
  });
});

describe("FleetStream", () => {
  it("takes a snapshot only once its last part arrives, and acks that", () => {
    const fleet = new FleetStream(3);
    expect(fleet.apply(hello)).toEqual({ ack: null, robots: false });
    expect(
      fleet.apply({ type: "snapshot", seq: 7, part: 1, parts: 2, robots: [bot("a")] }),
    ).toEqual({ ack: null, robots: false });
    expect(Object.keys(fleet.robots)).toEqual([]);
    expect(
      fleet.apply({ type: "snapshot", seq: 7, part: 2, parts: 2, robots: [bot("b")] }),
    ).toEqual({ ack: 7, robots: true });
    expect(Object.keys(fleet.robots)).toEqual(["a", "b"]);
    expect(fleet.resumeQuery()).toBe("&since=7&run=r1");
  });

  it("applies a delta as merge patches, nulls clearing a field", () => {
    const fleet = new FleetStream(3);
    fleet.apply(hello);
    fleet.apply({
      type: "snapshot", seq: 7, part: 1, parts: 1,
      robots: [bot("a", { battery: 3, waypoints_reason: "PROGRESS", mode: 1 })],
    });
    const result = fleet.apply({
      type: "delta", seq: 9,
      robots: { a: { battery: 2.9, waypoints_reason: null, mode: 0 } },
    });
    expect(result).toEqual({ ack: 9, robots: true });
    expect(fleet.robots.a).toEqual(bot("a", { battery: 2.9, mode: 0 }));
  });

  it("appends trail points, keeps the newest, and resets on request", () => {
    const fleet = new FleetStream(3);
    fleet.apply({ type: "snapshot", seq: 1, part: 1, parts: 1, robots: [bot("a", { trail: [{ x: 1, y: 1 }] })] });
    fleet.apply({ type: "delta", seq: 2, robots: { a: { trail_append: [{ x: 2, y: 2 }, { x: 3, y: 3 }, { x: 4, y: 4 }] } } });
    expect(fleet.robots.a.trail!.map((p) => p.x)).toEqual([2, 3, 4]);
    fleet.apply({ type: "delta", seq: 3, robots: { a: { trail_reset: true, trail_append: [{ x: 9, y: 9 }] } } });
    expect(fleet.robots.a.trail!.map((p) => p.x)).toEqual([9]);
    expect("trail_append" in fleet.robots.a).toBe(false);
  });

  it("adds a new robot from its whole object and drops a removed one", () => {
    const fleet = new FleetStream(3);
    fleet.apply({ type: "snapshot", seq: 1, part: 1, parts: 1, robots: [bot("a")] });
    fleet.apply({
      type: "delta", seq: 2,
      robots: { b: bot("b", { trail: [{ x: 5, y: 5 }] }) as never, a: null },
    });
    expect(Object.keys(fleet.robots)).toEqual(["b"]);
    expect(fleet.robots.b.trail).toEqual([{ x: 5, y: 5 }]);
  });

  it("acks an event without touching the robots", () => {
    const fleet = new FleetStream(0);
    expect(fleet.apply({ type: "event", seq: 5, event: "calibration_session", data: null })).toEqual({
      ack: 5,
      robots: false,
    });
  });
});
