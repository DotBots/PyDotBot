import { useEffect, useRef, useState } from "react";

import { LH2Position, UnifiedBot } from "./types";

// Position updates arrive at whatever rate the source reports them: ~20Hz
// from the simulator, sparser and irregular from real LH2 hardware. A fixed
// CSS transition duration is picked independent of that rate, so it is
// either too long (a fast update interrupts the transition already in
// flight, changing its direction/speed mid-motion) or too short relative to
// the interval between updates (the bot glides for the transition duration,
// then holds still until the next update -- the "saccade" reported on both
// simulated and real bots, on the old frontend too, where there was no
// transition at all and every update snapped instantly).
//
// Using the previous observed update interval as the next animation's
// duration keeps the animation running for roughly the whole gap between
// updates, whatever that gap turns out to be, instead of assuming a rate.
export const MIN_DURATION_MS = 60;
export const MAX_DURATION_MS = 600;

// A jump bigger than this fraction of the arena diagonal in a single update
// is treated as a teleport (bot re-added, position reset by an operator)
// rather than motion, and rendered instantly instead of animated across the
// whole arena.
export const TELEPORT_FRACTION = 0.35;

export interface PosState {
  from: LH2Position;
  to: LH2Position;
  t0: number;
  duration: number;
  lastUpdateAt: number;
}

export function dist(a: LH2Position, b: LH2Position): number {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

export function lerpPos(a: LH2Position, b: LH2Position, t: number): LH2Position {
  return { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t };
}

export function positionAt(state: PosState, now: number): LH2Position {
  const t = state.duration > 0 ? Math.min(1, (now - state.t0) / state.duration) : 1;
  return lerpPos(state.from, state.to, t);
}

// Folds one new target position into the previous animation state. `now`
// and `mapDiagonal` are passed in (rather than read from globals) so this
// stays a pure function the hook can be tested through.
export function nextPosState(
  prev: PosState | undefined,
  target: LH2Position,
  now: number,
  mapDiagonal: number,
): PosState {
  if (!prev) {
    return { from: target, to: target, t0: now, duration: 0, lastUpdateAt: now };
  }
  if (prev.to.x === target.x && prev.to.y === target.y) return prev;

  const teleport = dist(prev.to, target) > mapDiagonal * TELEPORT_FRACTION;
  const interval = now - prev.lastUpdateAt;
  const current = positionAt(prev, now);
  return {
    from: teleport ? target : current,
    to: target,
    t0: now,
    duration: teleport ? 0 : Math.max(MIN_DURATION_MS, Math.min(MAX_DURATION_MS, interval)),
    lastUpdateAt: now,
  };
}

// Smoothed per-bot positions, keyed by bot id. Only bots with a known
// position are present. Re-renders on every animation frame while at least
// one bot is mid-transition; callers read from the returned map instead of
// `bot.position` for the animated glyph, and keep using `bot.position`
// directly for anything that should update instantly (trails, waypoints).
export function useSmoothPositions(
  bots: UnifiedBot[],
  mapDiagonal: number,
): Map<string, LH2Position> {
  const statesRef = useRef<Map<string, PosState>>(new Map());
  const [, tick] = useState(0);

  useEffect(() => {
    const now = performance.now();
    for (const b of bots) {
      if (!b.position) continue;
      const prev = statesRef.current.get(b.id);
      statesRef.current.set(b.id, nextPosState(prev, b.position, now, mapDiagonal));
    }
  }, [bots, mapDiagonal]);

  useEffect(() => {
    let raf: number;
    const loop = () => {
      tick((n) => n + 1);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);

  const now = performance.now();
  const result = new Map<string, LH2Position>();
  for (const [id, state] of statesRef.current) {
    result.set(id, positionAt(state, now));
  }
  return result;
}
