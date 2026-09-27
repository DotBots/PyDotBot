// The controller stream, /controller/ws/stream: a hello, a snapshot of the
// fleet in parts, then deltas (RFC 7396 merge patches over the REST object,
// plus trail_append / trail_reset) and events. Every applied frame is acked,
// which is what lets the controller serve this client above 1 Hz.

import { PyDotBot } from "./types";

export interface StreamHello {
  type: "hello";
  protocol: number;
  run: string;
  seq: number;
  hz: number;
  unacked_hz: number;
  window: number;
  trail: number;
  acks: boolean;
  resumed: boolean;
}

export interface StreamSnapshot {
  type: "snapshot";
  seq: number;
  part: number;
  parts: number;
  robots: PyDotBot[];
}

export type RobotPatch = Record<string, unknown> & {
  trail_append?: PyDotBot["trail"];
  trail_reset?: boolean;
};

export interface StreamDelta {
  type: "delta";
  seq: number;
  robots: Record<string, RobotPatch | null>;
}

export interface StreamEvent {
  type: "event";
  seq: number;
  event: string;
  data: unknown;
}

export type StreamFrame = StreamHello | StreamSnapshot | StreamDelta | StreamEvent;

/** RFC 7396: `patch` applied to `target`, which is left untouched. */
export function mergePatch(target: unknown, patch: unknown): unknown {
  if (patch === null || typeof patch !== "object" || Array.isArray(patch)) return patch;
  const result: Record<string, unknown> =
    target !== null && typeof target === "object" && !Array.isArray(target)
      ? { ...(target as Record<string, unknown>) }
      : {};
  for (const [key, value] of Object.entries(patch as Record<string, unknown>)) {
    if (value === null) delete result[key];
    else result[key] = mergePatch(result[key], value);
  }
  return result;
}

/** One robot's patch, applied in place; its trail keeps `trailMax` points. */
export function applyRobotPatch(robot: PyDotBot, patch: RobotPatch, trailMax: number): void {
  const bot = robot as unknown as Record<string, unknown>;
  for (const [key, value] of Object.entries(patch)) {
    if (key === "trail_append" || key === "trail_reset") continue;
    if (value === null) delete bot[key];
    else bot[key] = mergePatch(bot[key], value);
  }
  if (patch.trail_reset) robot.trail = [];
  if (patch.trail_append?.length) {
    robot.trail = [...(robot.trail ?? []), ...patch.trail_append].slice(-trailMax);
  }
}

/**
 * The fleet a stream client holds, and where it resumes from. `robots` is
 * replaced by a whole snapshot and mutated in place by deltas.
 */
export class FleetStream {
  robots: Record<string, PyDotBot> = {};
  seq: number | null = null;
  run: string | null = null;
  private parts: PyDotBot[] = [];

  constructor(readonly trail: number) {}

  /** Where a new connection resumes from, as query parameters. */
  resumeQuery(): string {
    return this.seq === null || this.run === null
      ? ""
      : `&since=${this.seq}&run=${encodeURIComponent(this.run)}`;
  }

  /**
   * Take one frame. Returns the seq to ack, or null when there is nothing to
   * ack yet (a hello, or a snapshot part before the last).
   */
  apply(frame: StreamFrame): { ack: number | null; robots: boolean } {
    switch (frame.type) {
      case "hello":
        this.run = frame.run;
        return { ack: null, robots: false };
      case "snapshot":
        if (frame.part === 1) this.parts = [];
        this.parts.push(...frame.robots);
        if (frame.part < frame.parts) return { ack: null, robots: false };
        this.robots = Object.fromEntries(this.parts.map((r) => [r.address, r]));
        this.parts = [];
        this.seq = frame.seq;
        return { ack: frame.seq, robots: true };
      case "delta":
        for (const [address, patch] of Object.entries(frame.robots)) {
          if (patch === null) {
            delete this.robots[address];
          } else if (this.robots[address] === undefined || "address" in patch) {
            // A robot new to this client arrives as its whole object
            this.robots[address] = { ...(patch as unknown as PyDotBot) };
          } else {
            applyRobotPatch(this.robots[address], patch, this.trail);
          }
        }
        this.seq = frame.seq;
        return { ack: frame.seq, robots: true };
      case "event":
        this.seq = frame.seq;
        return { ack: frame.seq, robots: false };
    }
  }
}

export interface StreamHandlers {
  onRobots: (robots: Record<string, PyDotBot>) => void;
  onEvent: (event: StreamEvent) => void;
  onUp: (up: boolean) => void;
}

/**
 * Keep a stream open to `baseUrl`, reconnecting a second after it closes and
 * resuming from the last applied seq. Returns the function that stops it.
 */
export function connectStream(
  baseUrl: string,
  fleet: FleetStream,
  handlers: StreamHandlers,
): () => void {
  let ws: WebSocket | null = null;
  let closed = false;
  const connect = () => {
    ws = new WebSocket(`${baseUrl}${fleet.resumeQuery()}`);
    ws.onopen = () => handlers.onUp(true);
    ws.onclose = () => {
      handlers.onUp(false);
      if (!closed) setTimeout(connect, 1000);
    };
    ws.onerror = () => ws?.close();
    ws.onmessage = (ev) => {
      let frame: StreamFrame;
      try {
        frame = JSON.parse(ev.data);
      } catch {
        return;
      }
      const { ack, robots } = fleet.apply(frame);
      if (robots) handlers.onRobots(fleet.robots);
      if (frame.type === "event") handlers.onEvent(frame);
      if (ack !== null && ws?.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ ack }));
      }
    };
  };
  connect();
  return () => {
    closed = true;
    ws?.close();
  };
}
