// The controller stream, /controller/ws/stream: a hello, a snapshot of the
// fleet in parts, then deltas (RFC 7396 merge patches over the REST object,
// plus trail_append / trail_reset; null for a robot forgotten) and events. Every applied frame is acked,
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
  /** The run a hello announced, taken as `run` with the snapshot that follows. */
  private pendingRun: string | null = null;

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
        if (!frame.resumed || frame.run !== this.run) {
          // A snapshot follows; until it completes there is nothing to resume from
          this.seq = null;
          this.run = null;
        }
        this.pendingRun = frame.run;
        return { ack: null, robots: false };
      case "snapshot":
        if (frame.part === 1) this.parts = [];
        this.parts.push(...frame.robots);
        if (frame.part < frame.parts) return { ack: null, robots: false };
        this.robots = Object.fromEntries(this.parts.map((r) => [r.address, r]));
        this.parts = [];
        this.seq = frame.seq;
        this.run = this.pendingRun;
        return { ack: frame.seq, robots: true };
      case "delta":
        for (const [address, patch] of Object.entries(frame.robots)) {
          if (patch === null) {
            // Forgotten by the controller
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

/** Reconnect delays: doubling from the first, capped, with up to half again as jitter. */
export const RECONNECT_MIN_MS = 1000;
export const RECONNECT_MAX_MS = 30000;

export function reconnectDelay(attempt: number, random: () => number = Math.random): number {
  const base = Math.min(RECONNECT_MAX_MS, RECONNECT_MIN_MS * 2 ** attempt);
  return base + base * 0.5 * random();
}

/**
 * Keep a stream open to `baseUrl`, reconnecting with capped exponential
 * backoff after it closes and resuming from the last applied seq. Returns the
 * function that stops it.
 */
export function connectStream(
  baseUrl: string,
  fleet: FleetStream,
  handlers: StreamHandlers,
): () => void {
  let ws: WebSocket | null = null;
  let closed = false;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let attempt = 0;
  const connect = () => {
    timer = null;
    if (closed) return;
    const socket = new WebSocket(`${baseUrl}${fleet.resumeQuery()}`);
    ws = socket;
    socket.onopen = () => {
      if (closed || ws !== socket) return;
      attempt = 0;
      handlers.onUp(true);
    };
    socket.onclose = () => {
      if (ws !== socket) return;
      ws = null;
      if (closed) return;
      handlers.onUp(false);
      timer = setTimeout(connect, reconnectDelay(attempt++));
    };
    socket.onerror = () => socket.close();
    socket.onmessage = (ev) => {
      if (closed || ws !== socket) return;
      let frame: StreamFrame;
      try {
        frame = JSON.parse(ev.data);
      } catch {
        return;
      }
      const { ack, robots } = fleet.apply(frame);
      if (robots) handlers.onRobots(fleet.robots);
      if (frame.type === "event") handlers.onEvent(frame);
      if (ack !== null && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ ack }));
      }
    };
  };
  connect();
  return () => {
    closed = true;
    if (timer !== null) clearTimeout(timer);
    timer = null;
    const socket = ws;
    ws = null;
    socket?.close();
  };
}
