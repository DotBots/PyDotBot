import React, { useEffect, useRef } from "react";

import type { RgbLed, UnifiedBot } from "../types";
import { useFleet } from "../useFleet";

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

/** A fleet is idle once nothing has arrived for this long, in ms. */
const IDLE_AFTER_MS = 1200;

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
  const seenAt = useRef(0);

  useEffect(() => {
    const { poses, hues, addresses, applications } = fleetToPoses(bots);
    handle.poses.current = poses;
    handle.hues.current = hues;
    handle.addresses.current = addresses;
    handle.applications.current = applications;
    handle.moving.current = true;
    handle.version.current++;
    seenAt.current = Date.now();
    onFleet(addresses.length, Math.max(mapSize.width, mapSize.height));
  }, [bots, mapSize, handle, onFleet]);

  // A still fleet must let the render loop sleep, which it only does once
  // `moving` goes false.
  useEffect(() => {
    const timer = setInterval(() => {
      if (Date.now() - seenAt.current > IDLE_AFTER_MS) handle.moving.current = false;
    }, 400);
    return () => clearInterval(timer);
  }, [handle]);

  return null;
};
