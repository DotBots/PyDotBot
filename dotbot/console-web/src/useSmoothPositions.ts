import { useEffect, useLayoutEffect, useRef } from "react";

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

/** Whether any state is still mid-transition at `now`. */
export function animating(states: Iterable<PosState>, now: number): boolean {
  for (const s of states) if (now < s.t0 + s.duration) return true;
  return false;
}

/** Where an element goes for a floor point: CSS left and top, in percent. */
export type Place = (p: LH2Position) => { left: number; top: number };

/**
 * Glides each robot's element to its latest position by writing its `left`
 * and `top` directly, one animation frame at a time, so a moving fleet costs
 * no React render at all. React owns everything else about the element and
 * never sets those two properties.
 */
export class PositionAnimator {
  private states = new Map<string, PosState>();
  private elements = new Map<string, HTMLElement>();
  // The robots mid-transition, the only ones a frame writes.
  private moving = new Set<string>();
  private raf: number | null = null;

  constructor(private place: Place) {}

  /** Folds in the fleet's latest positions; a robot seen first is placed at once. */
  update(bots: { id: string; position: LH2Position | null }[], mapDiagonal: number): void {
    const now = performance.now();
    const present = new Set<string>();
    for (const b of bots) {
      if (!b.position) continue;
      present.add(b.id);
      const prev = this.states.get(b.id);
      const next = nextPosState(prev, b.position, now, mapDiagonal);
      if (next === prev) continue;
      this.states.set(b.id, next);
      if (next.duration > 0) this.moving.add(b.id);
      else this.write(b.id, now);
    }
    for (const id of this.states.keys()) {
      if (present.has(id)) continue;
      this.states.delete(id);
      this.moving.delete(id);
    }
    this.kick();
  }

  /** A new mapping from floor to element, which moves every robot at once. */
  setPlace(place: Place): void {
    this.place = place;
    const now = performance.now();
    for (const id of this.elements.keys()) this.write(id, now);
  }

  /** The element drawing robot `id`, or null once it is gone. */
  attach(id: string, el: HTMLElement | null): void {
    if (!el) {
      this.elements.delete(id);
      return;
    }
    this.elements.set(id, el);
    this.write(id, performance.now());
  }

  stop(): void {
    if (this.raf !== null) cancelAnimationFrame(this.raf);
    this.raf = null;
  }

  private kick(): void {
    if (this.raf === null && this.moving.size > 0) {
      this.raf = requestAnimationFrame(this.frame);
    }
  }

  private frame = (): void => {
    this.raf = null;
    const now = performance.now();
    for (const id of this.moving) {
      // Written once more at or past its end, so it lands on its target.
      this.write(id, now);
      if (!animating([this.states.get(id)!], now)) this.moving.delete(id);
    }
    this.kick();
  };

  private write(id: string, now: number): void {
    const el = this.elements.get(id);
    const state = this.states.get(id);
    if (!el || !state) return;
    const { left, top } = this.place(positionAt(state, now));
    el.style.left = `${left}%`;
    el.style.top = `${top}%`;
  }
}

/**
 * One animator for the map's lifetime, fed every fleet update. `place` must
 * keep its identity until the mapping it computes changes.
 */
export function usePositionAnimator(
  bots: UnifiedBot[],
  mapDiagonal: number,
  place: Place,
): PositionAnimator {
  const ref = useRef<PositionAnimator | null>(null);
  if (ref.current === null) ref.current = new PositionAnimator(place);
  const animator = ref.current;
  // Layout effects, so a robot's element is placed before it is first painted:
  // they run after its marker has attached it.
  useLayoutEffect(() => animator.setPlace(place), [animator, place]);
  useLayoutEffect(() => animator.update(bots, mapDiagonal), [animator, bots, mapDiagonal]);
  useEffect(() => () => animator.stop(), [animator]);
  return animator;
}
