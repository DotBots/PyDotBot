import React, { useCallback, useEffect, useRef } from "react";

import type { RgbLed, UnifiedBot } from "../types";
import { useFleet } from "../useFleet";
import { nextPosState, positionAt, type PosState } from "../useSmoothPositions";

// The controller world: the same fleet the console draws, in the arrays the
// playground renderer wants. The merge, the WebSocket and the reconnect loop
// stay in useFleet - this only reshapes what comes out of it.

export interface WorldHandle {
  /** x, y, heading triples in arena mm and degrees. */
  poses: React.MutableRefObject<Float32Array>;
  hues: React.MutableRefObject<Float32Array>;
  moving: React.MutableRefObject<boolean>;
  version: React.MutableRefObject<number>;
  /** Bot addresses, in the order the pose arrays hold them. */
  addresses: React.MutableRefObject<string[]>;
  /** Each bot's ApplicationType, which its REST path carries. */
  applications: React.MutableRefObject<number[]>;
}

/** LED hue, 0..360. Grey and unlit LEDs have none, so the address supplies one. */
export function hueOf(led: RgbLed | null, address: string): number {
  if (led !== null) {
    const r = led.red / 255;
    const g = led.green / 255;
    const b = led.blue / 255;
    const max = Math.max(r, g, b);
    const min = Math.min(r, g, b);
    const span = max - min;
    if (span > 0.02) {
      let hue: number;
      if (max === r) hue = ((g - b) / span) % 6;
      else if (max === g) hue = (b - r) / span + 2;
      else hue = (r - g) / span + 4;
      return ((hue * 60) % 360 + 360) % 360;
    }
  }
  // FNV-1a over the address: stable across reloads, so a bot keeps its colour.
  let hash = 0x811c9dc5;
  for (let i = 0; i < address.length; i++) {
    hash = Math.imul(hash ^ address.charCodeAt(i), 0x01000193) >>> 0;
  }
  return hash % 360;
}

/**
 * The bots that have a position, as pose and hue arrays. Bots the controller
 * has never located are dropped rather than drawn at the origin.
 */
export function fleetToPoses(bots: UnifiedBot[]): {
  poses: Float32Array;
  hues: Float32Array;
  addresses: string[];
  applications: number[];
} {
  const placed = bots.filter((b) => b.position !== null);
  const poses = new Float32Array(placed.length * 3);
  const hues = new Float32Array(placed.length);
  const addresses: string[] = [];
  const applications: number[] = [];
  placed.forEach((bot, i) => {
    poses[i * 3] = bot.position!.x;
    poses[i * 3 + 1] = bot.position!.y;
    poses[i * 3 + 2] = bot.heading ?? 0;
    hues[i] = hueOf(bot.led, bot.id);
    addresses.push(bot.id);
    applications.push(bot.application);
  });
  return { poses, hues, addresses, applications };
}

/** One bot between two fixes: the glide it is on and the heading arc it turns through. */
export interface Motion {
  pos: PosState;
  headingFrom: number;
  headingTo: number;
}

/** Shortest signed arc from one heading to another, in degrees. */
export function headingArc(from: number, to: number): number {
  return ((((to - from) % 360) + 540) % 360) - 180;
}

/** Where a bot is drawn at `now`, and whether it is still mid-glide. */
export function sampleMotion(
  m: Motion,
  now: number,
): { x: number; y: number; heading: number; live: boolean } {
  const { x, y } = positionAt(m.pos, now);
  const t = m.pos.duration > 0 ? Math.min(1, (now - m.pos.t0) / m.pos.duration) : 1;
  return { x, y, heading: m.headingFrom + headingArc(m.headingFrom, m.headingTo) * t, live: t < 1 };
}

/**
 * Folds the fleet's latest fixes into per-bot motions. A first fix places the
 * bot instantly; each later one starts a glide from wherever it was drawn
 * last, timed by the console's rule in useSmoothPositions. Bots without a
 * position are dropped.
 */
export function foldMotion(
  prev: Map<string, Motion>,
  bots: UnifiedBot[],
  now: number,
  mapDiagonal: number,
): Map<string, Motion> {
  const next = new Map<string, Motion>();
  for (const b of bots) {
    if (b.position === null) continue;
    const was = prev.get(b.id);
    const heading = b.heading ?? 0;
    next.set(b.id, {
      pos: nextPosState(was?.pos, b.position, now, mapDiagonal),
      headingFrom: was ? sampleMotion(was, now).heading : heading,
      headingTo: heading,
    });
  }
  return next;
}

interface FeedProps {
  handle: WorldHandle;
  onFleet: (count: number, side: number) => void;
}

/**
 * Mounted only while the controller world is selected, so switching to the
 * fake world closes the WebSocket instead of leaving it retrying. It renders
 * nothing: the fleet lands in refs, and the canvas reads them per frame.
 */
export const ControllerFeed: React.FC<FeedProps> = ({ handle, onFleet }) => {
  const { bots, mapSize } = useFleet();
  const motions = useRef<Map<string, Motion>>(new Map());
  const raf = useRef(0);

  // Writes every bot's interpolated pose once per frame and stops when the
  // last glide has landed, which is what lets the canvas loop sleep. A fresh
  // snapshot restarts it.
  const frame = useCallback(() => {
    const now = performance.now();
    const poses = handle.poses.current;
    let live = false;
    handle.addresses.current.forEach((id, i) => {
      const m = motions.current.get(id);
      if (!m) return;
      const s = sampleMotion(m, now);
      poses[i * 3] = s.x;
      poses[i * 3 + 1] = s.y;
      poses[i * 3 + 2] = s.heading;
      live = live || s.live;
    });
    handle.version.current++;
    if (live) {
      raf.current = requestAnimationFrame(frame);
    } else {
      raf.current = 0;
      handle.moving.current = false;
    }
  }, [handle]);

  useEffect(() => {
    const now = performance.now();
    motions.current = foldMotion(
      motions.current,
      bots,
      now,
      Math.hypot(mapSize.width, mapSize.height),
    );
    const { poses, hues, addresses, applications } = fleetToPoses(bots);
    handle.poses.current = poses;
    handle.hues.current = hues;
    handle.addresses.current = addresses;
    handle.applications.current = applications;
    handle.moving.current = true;
    onFleet(addresses.length, Math.max(mapSize.width, mapSize.height));
    if (raf.current === 0) raf.current = requestAnimationFrame(frame);
  }, [bots, mapSize, handle, onFleet, frame]);

  useEffect(
    () => () => {
      if (raf.current !== 0) cancelAnimationFrame(raf.current);
    },
    [],
  );

  return null;
};
