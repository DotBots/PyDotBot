import { assignTargets, gather, toPoints, type Points } from "./assign";
import { FULL_BATTERY_V, type FakeWorld } from "./fakeWorld";
import {
  figureOverlay,
  fillPoints,
  formation,
  hueByAngle,
  regionSlots,
  ringTargets,
  shareByArea,
  spareRing,
  splitByProximity,
} from "./formations";
import type { Box, OverlayItem, Vec2 } from "./types";

// The demos, inside the page. Each one turns what the map collected into a
// target per bot, an overlay and a status line, exactly as its Python script
// does against a controller; the world drives the bots to whatever lands here.

/** Radians the show's phase advances per second at 100% tempo. */
export const PHASE_RATE = 0.12;

/** How far from a corner each charging pad sits, mm. */
export const PAD_INSET_MM = 350;

/** Radius of a pad, mm. A bot within it counts as docked. */
export const PAD_RADIUS_MM = 180;

/** A released bot is left alone this long, so it clears the pad first. */
export const COOLDOWN_S = 20;

/** Points an overlay draws before it stops being worth the fill calls. */
export const MAX_OVERLAY_POINTS = 400;

/** How often a set of targets is recomputed while an input is being dragged. */
const REPLAN_MS = 200;

export type FakeAppSpec =
  | { kind: "none" }
  | { kind: "goals"; pins: Vec2[]; radius: number; arrive: number }
  | { kind: "region"; rects: Box[]; arrive: number }
  | { kind: "show"; figure: string; tempo: number; playing: boolean; arrive: number }
  | { kind: "letters"; word: string; ink: Vec2[]; arrive: number };

export interface ChargingSpec {
  /** Below this, in mV, a bot leaves for a pad. */
  threshold: number;
  /** How long it sits there, seconds. */
  dwell: number;
  /** Charging is the selected app, so its pads and badges are what shows. */
  selected: boolean;
}

export const DEFAULT_CHARGING: ChargingSpec = {
  threshold: 2960,
  dwell: 20,
  selected: false,
};

/** What an app hands the page each time round: what to draw and what to say. */
export interface AppOut {
  items: OverlayItem[];
  status: string | null;
}

/** One pad per corner of the arena. */
export function padPoints(side: number, inset = PAD_INSET_MM): Points {
  return Float64Array.from([
    inset,
    inset,
    side - inset,
    inset,
    inset,
    side - inset,
    side - inset,
    side - inset,
  ]);
}

function point(x: number, y: number, r: number, color: OverlayItem["color"], label?: string) {
  return { type: "point" as const, x, y, r, ...(label ? { label } : {}), color };
}

export class AppRunner {
  private spec: FakeAppSpec = { kind: "none" };
  private charging: ChargingSpec = { ...DEFAULT_CHARGING };
  /** What the current plan was made for; a different one is a replan. */
  private planKey = "";
  private plannedAt = -Infinity;
  /** A fixed target per bot, for every app but the show. */
  private targets: Points = new Float64Array(0);
  /** The show's slot per bot, held while the figure runs so the ring turns. */
  private slots: Int32Array = new Int32Array(0);
  private phase = 0;
  /** Bot index to the pad it holds, and when it docked. */
  private holding = new Map<number, number>();
  private since = new Map<number, number>();
  private released = new Map<number, number>();
  /** The identity hues, kept while the show is painting by angle. */
  private baseHue: Float32Array | null = null;
  /** Set whenever the LED colours moved, so the worker re-sends them. */
  hueDirty = false;

  setSpec(spec: FakeAppSpec): void {
    this.spec = spec;
  }

  /** Forget everything tied to a fleet, which a reseed replaces wholesale. */
  reset(): void {
    this.planKey = "";
    this.plannedAt = -Infinity;
    this.targets = new Float64Array(0);
    this.slots = new Int32Array(0);
    this.holding.clear();
    this.since.clear();
    this.released.clear();
    this.baseHue = null;
  }

  setCharging(charging: ChargingSpec): void {
    this.charging = charging;
  }

  /** Where the show's cycle stands, in radians. */
  get showPhase(): number {
    return this.phase;
  }

  step(world: FakeWorld, dt: number, nowMs: number): void {
    if (this.spec.kind === "show" && this.spec.playing) {
      this.phase += PHASE_RATE * (this.spec.tempo / 100) * dt;
    }
    this.plan(world, nowMs);
    this.writeTargets(world);
    this.runCharging(world, nowMs / 1000);
  }

  private keyFor(world: FakeWorld): string {
    const s = this.spec;
    switch (s.kind) {
      case "goals":
        return `goals:${world.count}:${s.radius}:${s.pins.map((p) => `${p.x},${p.y}`).join("|")}`;
      case "region":
        return `region:${world.count}:${s.rects
          .map((r) => `${r.x},${r.y},${r.w},${r.h}`)
          .join("|")}`;
      case "show":
        return `show:${world.count}:${s.figure}`;
      case "letters":
        return `letters:${world.count}:${s.word}:${s.ink.length}`;
      default:
        return "none";
    }
  }

  private plan(world: FakeWorld, nowMs: number): void {
    const key = this.keyFor(world);
    if (key === this.planKey) return;
    // An input being dragged re-keys every sample; the assignment is the one
    // part of a tick that a thousand bots make expensive.
    if (nowMs - this.plannedAt < REPLAN_MS) return;
    this.planKey = key;
    this.plannedAt = nowMs;

    const n = world.count;
    const from = new Float64Array(n * 2);
    for (let i = 0; i < n; i++) {
      from[i * 2] = world.x[i];
      from[i * 2 + 1] = world.y[i];
    }

    const s = this.spec;
    if (s.kind === "goals" && s.pins.length > 0) {
      this.targets = ringTargets(from, toPoints(s.pins), s.radius, world.side, world.side);
    } else if (s.kind === "region" && s.rects.length > 0) {
      let slots = regionSlots(s.rects, n);
      if (slots.length < n * 2) {
        // Rounding can leave a bot without a slot; it stays where it is.
        const padded = new Float64Array(n * 2);
        padded.set(slots, 0);
        padded.set(from.subarray(slots.length), slots.length);
        slots = padded;
      }
      this.targets = gather(slots, assignTargets(from, slots));
    } else if (s.kind === "letters" && s.ink.length > 0) {
      const ink = toPoints(s.ink);
      const spares = spareRing(n - s.ink.length, world.side, world.side);
      const slots = new Float64Array(ink.length + spares.length);
      slots.set(ink, 0);
      slots.set(spares, ink.length);
      this.targets = gather(slots, assignTargets(from, slots));
    } else if (s.kind === "show") {
      const points = formation(s.figure, n, world.side, world.side, this.phase);
      this.slots = assignTargets(from, points);
      this.targets = new Float64Array(0);
    } else {
      this.targets = new Float64Array(0);
      this.slots = new Int32Array(0);
    }
  }

  private writeTargets(world: FakeWorld): void {
    const n = world.count;
    world.held.fill(0);
    const s = this.spec;
    world.arriveMm = s.kind === "none" ? 40 : s.arrive;

    if (s.kind === "show" && this.slots.length === n) {
      const points = formation(s.figure, n, world.side, world.side, this.phase);
      const hues = hueByAngle(points, world.side, world.side);
      if (this.baseHue === null) this.baseHue = Float32Array.from(world.hue);
      for (let i = 0; i < n; i++) {
        const slot = this.slots[i];
        world.targets[i * 2] = points[slot * 2];
        world.targets[i * 2 + 1] = points[slot * 2 + 1];
        world.hasTarget[i] = 1;
        world.hue[i] = hues[slot];
      }
      this.hueDirty = true;
      return;
    }

    this.restoreHues(world);
    if (this.targets.length === n * 2) {
      world.targets.set(this.targets);
      world.hasTarget.fill(1);
    } else {
      world.hasTarget.fill(0);
    }
  }

  private restoreHues(world: FakeWorld): void {
    if (this.baseHue === null) return;
    if (this.baseHue.length === world.hue.length) world.hue.set(this.baseHue);
    this.baseHue = null;
    this.hueDirty = true;
  }

  // ------------------------------------------------------------- charging

  private resting(bot: number, now: number): boolean {
    return now - (this.released.get(bot) ?? -COOLDOWN_S) < COOLDOWN_S;
  }

  private nearestFree(world: FakeWorld, bot: number, pads: Points): number | undefined {
    const taken = new Set(this.holding.values());
    let best: number | undefined;
    let bestCost = Infinity;
    for (let p = 0; p < pads.length >> 1; p++) {
      if (taken.has(p)) continue;
      const dx = pads[p * 2] - world.x[bot];
      const dy = pads[p * 2 + 1] - world.y[bot];
      const c = dx * dx + dy * dy;
      if (c < bestCost) {
        bestCost = c;
        best = p;
      }
    }
    return best;
  }

  private release(world: FakeWorld, bot: number, now: number): void {
    this.holding.delete(bot);
    this.since.delete(bot);
    this.released.set(bot, now);
    world.battery[bot] = FULL_BATTERY_V;
    world.held[bot] = 0;
    world.hasTarget[bot] = 0;
  }

  private runCharging(world: FakeWorld, now: number): void {
    const pads = padPoints(world.side);
    const thresholdV = this.charging.threshold / 1000;
    for (let i = 0; i < world.count; i++) {
      let pad = this.holding.get(i);
      if (pad === undefined) {
        if (world.battery[i] >= thresholdV || this.resting(i, now)) continue;
        pad = this.nearestFree(world, i, pads);
        if (pad === undefined) continue;
        this.holding.set(i, pad);
        this.since.delete(i);
      }
      const px = pads[pad * 2];
      const py = pads[pad * 2 + 1];
      const docked = this.since.get(i);
      if (docked !== undefined && now - docked >= this.charging.dwell) {
        this.release(world, i, now);
        continue;
      }
      world.targets[i * 2] = px;
      world.targets[i * 2 + 1] = py;
      world.hasTarget[i] = 1;
      const distance = Math.hypot(world.x[i] - px, world.y[i] - py);
      // The dwell starts at the pad's edge, as the demo's script has it, but
      // the bot carries on to the middle of it and parks there.
      if (docked === undefined && distance <= PAD_RADIUS_MM) this.since.set(i, now);
      if (distance <= world.arriveMm) world.held[i] = 1;
    }
    // A world that was reseeded is a smaller one; a pad cannot stay claimed by
    // a bot that no longer exists.
    for (const bot of [...this.holding.keys()]) {
      if (bot >= world.count) {
        this.holding.delete(bot);
        this.since.delete(bot);
      }
    }
  }

  // -------------------------------------------------------------- overlay

  /** What the canvas draws and the panel says, for the selected app. */
  out(world: FakeWorld): AppOut {
    if (this.charging.selected) return this.chargingOut(world);
    const s = this.spec;
    const n = world.count;
    switch (s.kind) {
      case "goals": {
        if (s.pins.length === 0) return { items: [], status: "waiting for a pin on the map" };
        const groups = splitByProximity(bodies(world), toPoints(s.pins));
        const items = s.pins.map((p, i) => {
          let count = 0;
          for (let b = 0; b < n; b++) if (groups[b] === i) count++;
          return point(p.x, p.y, s.radius, "accent", String(count));
        });
        return { items, status: `${n} bots over ${s.pins.length} pins` };
      }
      case "region": {
        if (s.rects.length === 0) {
          return { items: [], status: "waiting for a region on the map" };
        }
        const counts = shareByArea(s.rects, n);
        const items: OverlayItem[] = s.rects.map((r, i) => ({
          type: "rect",
          x: r.x,
          y: r.y,
          w: r.w,
          h: r.h,
          label: `${counts[i]} bots`,
          color: "accent",
        }));
        let drawn = 0;
        s.rects.forEach((r, i) => {
          const slots = fillPoints(r, counts[i]);
          for (let k = 0; k < slots.length >> 1 && drawn < MAX_OVERLAY_POINTS; k++, drawn++) {
            items.push(point(slots[k * 2], slots[k * 2 + 1], 24, "muted"));
          }
        });
        return { items, status: `${n} bots over ${s.rects.length} regions` };
      }
      case "show": {
        const points = formation(s.figure, n, world.side, world.side, this.phase);
        return {
          items: figureOverlay(s.figure, points),
          status: `${s.figure}, ${s.playing ? "playing" : "paused"}, ${n} bots`,
        };
      }
      case "letters": {
        if (s.ink.length === 0) return { items: [], status: null };
        const items = s.ink
          .slice(0, MAX_OVERLAY_POINTS)
          .map((p) => point(p.x, p.y, 40, "muted"));
        return {
          items,
          status: `${s.word}: ${s.ink.length} bots spelling, ${n - s.ink.length} parked`,
        };
      }
      default:
        return { items: [], status: null };
    }
  }

  private chargingOut(world: FakeWorld): AppOut {
    const pads = padPoints(world.side);
    const items: OverlayItem[] = [];
    for (let p = 0; p < pads.length >> 1; p++) {
      items.push(point(pads[p * 2], pads[p * 2 + 1], PAD_RADIUS_MM, "good", "pad"));
    }
    for (const bot of this.holding.keys()) {
      const docked = this.since.has(bot);
      items.push({
        type: "badge",
        address: String(bot),
        text: docked ? "charging" : "to a pad",
        color: docked ? "good" : "warn",
      });
    }
    const thresholdV = this.charging.threshold / 1000;
    let low = 0;
    for (let i = 0; i < world.count; i++) if (world.battery[i] < thresholdV) low++;
    return {
      items,
      status:
        `${this.holding.size} on pads, ${low} of ${world.count} below ` +
        `${this.charging.threshold.toFixed(0)} mV`,
    };
  }
}

/** Every bot's position as one point set, which the overlays count over. */
function bodies(world: FakeWorld): Points {
  const out = new Float64Array(world.count * 2);
  for (let i = 0; i < world.count; i++) {
    out[i * 2] = world.x[i];
    out[i * 2 + 1] = world.y[i];
  }
  return out;
}
