import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { connectStream, FleetStream, mergePatch, reconnectDelay, RECONNECT_MAX_MS } from "./stream";
import { PyDotBot } from "./types";

const bot = (address: string, over: Partial<PyDotBot> = {}): PyDotBot => ({
  address,
  application: 0,
  status: 0,
  trail: [],
  ...over,
});

const hello = { type: "hello", protocol: 2, run: "r1", seq: 4, hz: 10, unacked_hz: 1, window: 2, trail: 3, acks: true, resumed: false } as const;

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

  it("drops a robot the controller forgot, and takes it whole when it is back", () => {
    const fleet = new FleetStream(3);
    fleet.apply({ type: "snapshot", seq: 1, part: 1, parts: 1, robots: [bot("a", { battery: 3 }), bot("b")] });
    expect(fleet.apply({ type: "delta", seq: 2, robots: { a: null } })).toEqual({ ack: 2, robots: true });
    expect(Object.keys(fleet.robots)).toEqual(["b"]);
    fleet.apply({ type: "delta", seq: 3, robots: { a: bot("a") as unknown as Record<string, unknown> } });
    expect(fleet.robots.a).toEqual(bot("a"));
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

  it("adds a new robot from its whole object", () => {
    const fleet = new FleetStream(3);
    fleet.apply({ type: "snapshot", seq: 1, part: 1, parts: 1, robots: [bot("a")] });
    fleet.apply({
      type: "delta", seq: 2,
      robots: { b: bot("b", { trail: [{ x: 5, y: 5 }] }) as never },
    });
    expect(Object.keys(fleet.robots)).toEqual(["a", "b"]);
    expect(fleet.robots.b.trail).toEqual([{ x: 5, y: 5 }]);
  });

  it("does not resume a new run from the old run's seq while its snapshot is in flight", () => {
    const fleet = new FleetStream(3);
    fleet.apply(hello);
    fleet.apply({ type: "snapshot", seq: 7, part: 1, parts: 1, robots: [bot("a")] });
    expect(fleet.resumeQuery()).toBe("&since=7&run=r1");
    fleet.apply({ ...hello, run: "r2", seq: 2 });
    expect(fleet.resumeQuery()).toBe("");
    fleet.apply({ type: "snapshot", seq: 2, part: 1, parts: 2, robots: [bot("a")] });
    expect(fleet.resumeQuery()).toBe("");
    fleet.apply({ type: "snapshot", seq: 2, part: 2, parts: 2, robots: [bot("b")] });
    expect(fleet.resumeQuery()).toBe("&since=2&run=r2");
  });

  it("keeps its cursor when the hello resumes the same run", () => {
    const fleet = new FleetStream(3);
    fleet.apply(hello);
    fleet.apply({ type: "snapshot", seq: 7, part: 1, parts: 1, robots: [bot("a")] });
    fleet.apply({ ...hello, seq: 9, resumed: true });
    expect(fleet.resumeQuery()).toBe("&since=7&run=r1");
  });

  it("acks an event without touching the robots", () => {
    const fleet = new FleetStream(0);
    expect(fleet.apply({ type: "event", seq: 5, event: "calibration_session", data: null })).toEqual({
      ack: 5,
      robots: false,
    });
  });
});

class FakeSocket {
  static OPEN = 1;
  static instances: FakeSocket[] = [];
  readyState = 0;
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  constructor(readonly url: string) {
    FakeSocket.instances.push(this);
  }
  send(data: string) {
    this.sent.push(data);
  }
  close() {
    if (this.readyState === 3) return;
    this.readyState = 3;
    this.onclose?.();
  }
  open() {
    this.readyState = FakeSocket.OPEN;
    this.onopen?.();
  }
  receive(frame: unknown) {
    this.onmessage?.({ data: JSON.stringify(frame) });
  }
}

describe("connectStream", () => {
  beforeEach(() => {
    FakeSocket.instances = [];
    vi.useFakeTimers();
    vi.stubGlobal("WebSocket", FakeSocket);
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  const handlers = () => ({ onRobots: vi.fn(), onEvent: vi.fn(), onUp: vi.fn() });

  it("acks each applied frame, not a hello or a partial snapshot", () => {
    const fleet = new FleetStream(3);
    const h = handlers();
    const stop = connectStream("ws://c/stream?trail=3", fleet, h);
    const ws = FakeSocket.instances[0];
    ws.open();
    expect(h.onUp).toHaveBeenCalledWith(true);
    ws.receive(hello);
    ws.receive({ type: "snapshot", seq: 7, part: 1, parts: 2, robots: [bot("a")] });
    ws.receive({ type: "snapshot", seq: 7, part: 2, parts: 2, robots: [bot("b")] });
    ws.receive({ type: "event", seq: 8, event: "x", data: null });
    expect(ws.sent.map((m) => JSON.parse(m))).toEqual([{ ack: 7 }, { ack: 8 }]);
    expect(h.onRobots).toHaveBeenCalledTimes(1);
    expect(h.onEvent).toHaveBeenCalledTimes(1);
    stop();
  });

  it("reconnects after a close, resuming from the last seq, with growing delays", () => {
    const fleet = new FleetStream(3);
    const h = handlers();
    const stop = connectStream("ws://c/stream?trail=3", fleet, h);
    const first = FakeSocket.instances[0];
    first.open();
    first.receive(hello);
    first.receive({ type: "snapshot", seq: 7, part: 1, parts: 1, robots: [bot("a")] });
    first.close();
    expect(h.onUp).toHaveBeenLastCalledWith(false);
    vi.advanceTimersByTime(999);
    expect(FakeSocket.instances).toHaveLength(1);
    vi.advanceTimersByTime(1000);
    expect(FakeSocket.instances).toHaveLength(2);
    expect(FakeSocket.instances[1].url).toBe("ws://c/stream?trail=3&since=7&run=r1");
    FakeSocket.instances[1].close();
    vi.advanceTimersByTime(1999);
    expect(FakeSocket.instances).toHaveLength(2);
    vi.advanceTimersByTime(1500);
    expect(FakeSocket.instances).toHaveLength(3);
    stop();
  });

  it("drops the resume query once a hello announces a new run", () => {
    const fleet = new FleetStream(3);
    const stop = connectStream("ws://c/stream?trail=3", fleet, handlers());
    const first = FakeSocket.instances[0];
    first.open();
    first.receive(hello);
    first.receive({ type: "snapshot", seq: 7, part: 1, parts: 1, robots: [bot("a")] });
    first.close();
    vi.advanceTimersByTime(2000);
    const second = FakeSocket.instances[1];
    second.open();
    second.receive({ ...hello, run: "r2", seq: 1 });
    second.close();
    vi.advanceTimersByTime(2000);
    expect(FakeSocket.instances[2].url).toBe("ws://c/stream?trail=3");
    stop();
  });

  it("stops for good: no reconnect is pending and no handler fires after stop", () => {
    const h = handlers();
    const stop = connectStream("ws://c/stream", new FleetStream(3), h);
    const ws = FakeSocket.instances[0];
    ws.open();
    ws.close();
    stop();
    vi.advanceTimersByTime(60000);
    expect(FakeSocket.instances).toHaveLength(1);
    const calls = h.onUp.mock.calls.length;
    ws.onopen?.();
    ws.receive(hello);
    expect(h.onUp.mock.calls.length).toBe(calls);
  });

  it("caps the backoff", () => {
    expect(reconnectDelay(0, () => 0)).toBe(1000);
    expect(reconnectDelay(3, () => 0)).toBe(8000);
    expect(reconnectDelay(20, () => 0)).toBe(RECONNECT_MAX_MS);
    expect(reconnectDelay(20, () => 1)).toBe(RECONNECT_MAX_MS * 1.5);
  });
});
