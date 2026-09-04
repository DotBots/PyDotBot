// The fake world: a differential-drive swarm with Reynolds steering, run in a
// worker so a thousand bots do not compete with the renderer for the main
// thread. No DOM, no imports, so vitest exercises it directly.
//
// It is a showcase, not the simulator: it shares the simulator's geometry and
// motor constants (dotbot_simulator.py) so the motion is the right size and
// speed, and nothing else.

/** Motor speed constant, RPM. */
const KV = 700;
/** Motor reduction ratio. */
const GEAR = 50;
/** Wheel diameter, mm. */
const WHEEL_D = 44;
/** Distance between the two wheels, mm. */
const WHEELBASE = 78;
/** Approximate DotBot footprint, mm - the map's Real-scale figure. */
export const BOT_FOOTPRINT_MM = 80;

const DEG = Math.PI / 180;

/** Wheel speed in mm/s for a PWM value, the simulator's conversion. */
export function wheelSpeedFromPwm(pwm: number): number {
  const p = Math.max(-100, Math.min(100, pwm));
  return (p * WHEEL_D * KV) / (GEAR * 127);
}

/** Wheel speed at full throttle, mm/s. */
export const MAX_WHEEL_SPEED = wheelSpeedFromPwm(100);

export interface Pose {
  x: number;
  y: number;
  heading: number; // degrees, 0 = +y, positive clockwise
}

export interface Vec {
  x: number;
  y: number;
}

/**
 * One differential-drive step. Positions are arena mm, heading is the arena
 * frame's (0 = +y, clockwise positive), wheel speeds are mm/s.
 */
export function unicycleStep(pose: Pose, vLeft: number, vRight: number, dt: number): Pose {
  const v = (vRight + vLeft) / 2;
  // Heading runs clockwise while the simulator's theta runs the other way, so
  // the yaw term is negated: the left wheel leading turns the bot clockwise.
  const yawDeg = (-(vRight - vLeft) / WHEELBASE) * (180 / Math.PI);
  const h = pose.heading * DEG;
  return {
    x: pose.x + v * -Math.sin(h) * dt,
    y: pose.y + v * Math.cos(h) * dt,
    heading: wrapDeg(pose.heading + yawDeg * dt),
  };
}

/** Degrees folded into (-180, 180]. */
export function wrapDeg(deg: number): number {
  let d = deg % 360;
  if (d > 180) d -= 360;
  if (d <= -180) d += 360;
  return d;
}

/** The heading whose forward vector points along v, in (-180, 180]. */
export function headingOf(v: Vec): number {
  return wrapDeg(Math.atan2(-v.x, v.y) / DEG);
}

/** Full-speed desired velocity straight at the target. */
export function seek(from: Vec, target: Vec, maxSpeed: number): Vec {
  const dx = target.x - from.x;
  const dy = target.y - from.y;
  const d = Math.hypot(dx, dy);
  if (d < 1e-6) return { x: 0, y: 0 };
  return { x: (dx / d) * maxSpeed, y: (dy / d) * maxSpeed };
}

/** Seek that eases off inside slowRadius, so the bot stops on the target. */
export function arrive(from: Vec, target: Vec, maxSpeed: number, slowRadius: number): Vec {
  const dx = target.x - from.x;
  const dy = target.y - from.y;
  const d = Math.hypot(dx, dy);
  if (d < 1e-6) return { x: 0, y: 0 };
  const speed = d < slowRadius ? (maxSpeed * d) / slowRadius : maxSpeed;
  return { x: (dx / d) * speed, y: (dy / d) * speed };
}

/**
 * Reynolds separation: a push away from every neighbour inside radius,
 * weighted by how close it is, normalised to maxSpeed.
 */
export function separation(from: Vec, neighbours: Vec[], radius: number, maxSpeed: number): Vec {
  let sx = 0;
  let sy = 0;
  for (const n of neighbours) {
    const dx = from.x - n.x;
    const dy = from.y - n.y;
    const d = Math.hypot(dx, dy);
    if (d < 1e-6 || d > radius) continue;
    // 1/d, so the push grows sharply as two bots close on each other.
    sx += (dx / d) * (radius / d - 1);
    sy += (dy / d) * (radius / d - 1);
  }
  const m = Math.hypot(sx, sy);
  if (m < 1e-9) return { x: 0, y: 0 };
  return { x: (sx / m) * maxSpeed, y: (sy / m) * maxSpeed };
}

/**
 * Wheel commands, in PWM, that carry the bot along `desired`. Body-relative
 * and open loop, the same model the console's drive pad uses.
 */
export function driveTowards(
  pose: Pose,
  desired: Vec,
  maxPwm: number,
  yawGain = 1.6,
): { left: number; right: number } {
  const mag = Math.hypot(desired.x, desired.y);
  if (mag < 1e-6) return { left: 0, right: 0 };
  const err = wrapDeg(headingOf(desired) - pose.heading);
  // Facing away, the bot turns on the spot rather than driving off course.
  const align = Math.max(0, Math.cos(err * DEG));
  const forward = maxPwm * Math.min(1, mag / MAX_WHEEL_SPEED) * align;
  const yaw = Math.max(-maxPwm, Math.min(maxPwm, yawGain * err));
  const clamp = (v: number) => Math.max(-100, Math.min(100, v));
  return { left: clamp(forward + yaw), right: clamp(forward - yaw) };
}

/** Deterministic RNG, so a seeded world replays and a test can assert on it. */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export interface WorldConfig {
  count: number;
  placement: "grid" | "random";
  seed: number;
}

export interface WorldTuning {
  /** 0..100, the follow app's speed slider. */
  speedPct: number;
  /** 1..6, the follow app's spread slider, in footprints. */
  spread: number;
  wanderWhenIdle: boolean;
  /** Multiplies the battery drain, so a charging cycle can be watched sooner. */
  drainScale: number;
}

export const DEFAULT_TUNING: WorldTuning = {
  speedPct: 60,
  spread: 2,
  wanderWhenIdle: true,
  drainScale: 1,
};

/** A full battery, volts. The simulator's own model starts here too. */
export const FULL_BATTERY_V = 3.0;

/**
 * Volts lost per mm driven. At the default 60% speed a bot covers about
 * 290 mm/s, so it falls the 40 mV to the charging demo's default threshold in
 * a little under a minute of driving. A parked bot does not drain.
 */
export const DRAIN_V_PER_MM = 2.5e-6;

/**
 * Arena side for a bot count, in mm. The controller's default 2 m room holds a
 * hundred bots and not a thousand, so the fake arena grows with the count and
 * keeps the swarm at a density a person can see through.
 */
export function arenaSideFor(count: number): number {
  return Math.max(2000, Math.round(Math.sqrt(count) * BOT_FOOTPRINT_MM * 2.6));
}

/** How far a bot steers away from the arena edge, mm. */
const WALL_MARGIN = BOT_FOOTPRINT_MM * 2;

/** How hard separation bends a bot with no target of its own. */
const BLOB_SEPARATION = 1.7;

/** And one holding an assigned slot, which its neighbours are not aiming at. */
const HOLD_SEPARATION = 0.7;

export class FakeWorld {
  readonly count: number;
  readonly side: number;
  readonly x: Float64Array;
  readonly y: Float64Array;
  readonly heading: Float64Array;
  readonly hue: Float32Array;
  /** Last reported battery, volts, as the charging demo reads it. */
  readonly battery: Float64Array;
  /** Where an app sent each bot, x, y per bot, read where `hasTarget` is set. */
  readonly targets: Float64Array;
  readonly hasTarget: Uint8Array;
  /** Bots an app is holding still, a docked one being the case that exists. */
  readonly held: Uint8Array;
  /** How close to its target a bot has to be to stop, mm. */
  arriveMm = 40;
  private readonly wanderAngle: Float64Array;
  private readonly rng: () => number;
  private tuning: WorldTuning = { ...DEFAULT_TUNING };
  private target: Vec | null = null;
  /** Bot index the Drive stick owns, or -1. */
  private drivenIndex = -1;
  private drivenWheels = { left: 0, right: 0 };
  /** Cells of a uniform grid over the arena, for O(n) neighbour lookup. */
  private cellSize = BOT_FOOTPRINT_MM * 4;
  private cells = new Map<number, number[]>();
  /** Peak wheel speed over the last step, mm/s - what "is anything moving". */
  private lastMotion = 0;

  constructor(cfg: WorldConfig) {
    this.count = Math.max(1, Math.floor(cfg.count));
    this.side = arenaSideFor(this.count);
    this.x = new Float64Array(this.count);
    this.y = new Float64Array(this.count);
    this.heading = new Float64Array(this.count);
    this.hue = new Float32Array(this.count);
    this.battery = new Float64Array(this.count);
    this.targets = new Float64Array(this.count * 2);
    this.hasTarget = new Uint8Array(this.count);
    this.held = new Uint8Array(this.count);
    this.wanderAngle = new Float64Array(this.count);
    this.rng = mulberry32(cfg.seed);
    this.place(cfg.placement);
  }

  private place(placement: "grid" | "random") {
    const cols = Math.ceil(Math.sqrt(this.count));
    const pitch = this.side / (cols + 1);
    for (let i = 0; i < this.count; i++) {
      if (placement === "grid") {
        this.x[i] = pitch * (1 + (i % cols));
        this.y[i] = pitch * (1 + Math.floor(i / cols));
      } else {
        this.x[i] = WALL_MARGIN + this.rng() * (this.side - 2 * WALL_MARGIN);
        this.y[i] = WALL_MARGIN + this.rng() * (this.side - 2 * WALL_MARGIN);
      }
      this.heading[i] = this.rng() * 360 - 180;
      this.wanderAngle[i] = this.rng() * Math.PI * 2;
      // The LED colour is the bot's identity here; a hue wheel keeps a
      // thousand of them distinguishable in a blob.
      this.hue[i] = (i * 137.508) % 360;
      // A spread of a few mV, so a charging cycle is a queue rather than the
      // whole fleet crossing the threshold on the same tick.
      this.battery[i] = FULL_BATTERY_V - this.rng() * 0.02;
    }
  }

  setTuning(t: Partial<WorldTuning>) {
    this.tuning = { ...this.tuning, ...t };
  }

  /** Where the swarm seeks, in arena mm, or null to let it wander. */
  setTarget(t: Vec | null) {
    this.target = t;
  }

  /** Hand one bot to the Drive stick; -1 releases it. */
  setDriven(index: number, left = 0, right = 0) {
    this.drivenIndex = index;
    this.drivenWheels = { left, right };
  }

  /** True while any wheel is turning fast enough to be worth a frame. */
  get moving(): boolean {
    return this.lastMotion > 1;
  }

  private rebuildCells(radius: number) {
    this.cellSize = Math.max(radius, BOT_FOOTPRINT_MM);
    this.cells.clear();
    const s = this.cellSize;
    for (let i = 0; i < this.count; i++) {
      const key = (Math.floor(this.x[i] / s) << 16) ^ (Math.floor(this.y[i] / s) & 0xffff);
      const cell = this.cells.get(key);
      if (cell) cell.push(i);
      else this.cells.set(key, [i]);
    }
  }

  private neighbours(i: number, out: Vec[]): Vec[] {
    out.length = 0;
    const s = this.cellSize;
    const cx = Math.floor(this.x[i] / s);
    const cy = Math.floor(this.y[i] / s);
    for (let dx = -1; dx <= 1; dx++) {
      for (let dy = -1; dy <= 1; dy++) {
        const cell = this.cells.get(((cx + dx) << 16) ^ ((cy + dy) & 0xffff));
        if (!cell) continue;
        for (const j of cell) {
          if (j !== i) out.push({ x: this.x[j], y: this.y[j] });
        }
      }
    }
    return out;
  }

  /** A slow random walk: the wander angle drifts and the bot chases it. */
  private wander(i: number, maxSpeed: number, dt: number): Vec {
    this.wanderAngle[i] += (this.rng() - 0.5) * 2.5 * dt;
    return {
      x: Math.cos(this.wanderAngle[i]) * maxSpeed * 0.45,
      y: Math.sin(this.wanderAngle[i]) * maxSpeed * 0.45,
    };
  }

  /** Seek the pointer, or drift, which is what a bot with no target does. */
  private roam(pose: Vec, i: number, maxSpeed: number, sepRadius: number, dt: number): Vec {
    if (this.target !== null) return arrive(pose, this.target, maxSpeed, sepRadius * 3);
    return this.tuning.wanderWhenIdle ? this.wander(i, maxSpeed, dt) : { x: 0, y: 0 };
  }

  /** Arrive on the assigned point, and ask for nothing once inside it. */
  private hold(i: number, pose: Vec, maxSpeed: number, sepRadius: number): Vec {
    const target = { x: this.targets[i * 2], y: this.targets[i * 2 + 1] };
    const d = Math.hypot(target.x - pose.x, target.y - pose.y);
    if (d <= this.arriveMm) return { x: 0, y: 0 };
    return arrive(pose, target, maxSpeed, Math.max(sepRadius * 3, this.arriveMm * 3));
  }

  /** A push back inside the arena, growing as the bot nears an edge. */
  private walls(i: number, maxSpeed: number): Vec {
    let vx = 0;
    let vy = 0;
    const m = WALL_MARGIN;
    if (this.x[i] < m) vx += (1 - this.x[i] / m) * maxSpeed;
    if (this.x[i] > this.side - m) vx -= (1 - (this.side - this.x[i]) / m) * maxSpeed;
    if (this.y[i] < m) vy += (1 - this.y[i] / m) * maxSpeed;
    if (this.y[i] > this.side - m) vy -= (1 - (this.side - this.y[i]) / m) * maxSpeed;
    return { x: vx, y: vy };
  }

  step(dt: number) {
    const maxPwm = Math.max(0, Math.min(100, this.tuning.speedPct));
    const maxSpeed = wheelSpeedFromPwm(maxPwm);
    const sepRadius = BOT_FOOTPRINT_MM * Math.max(1, this.tuning.spread);
    this.rebuildCells(sepRadius);
    const scratch: Vec[] = [];
    let motion = 0;

    for (let i = 0; i < this.count; i++) {
      const pose = { x: this.x[i], y: this.y[i], heading: this.heading[i] };
      let left: number;
      let right: number;

      if (i === this.drivenIndex) {
        left = this.drivenWheels.left;
        right = this.drivenWheels.right;
      } else if (this.held[i] === 1) {
        left = 0;
        right = 0;
      } else {
        const holding = this.hasTarget[i] === 1;
        const goal = holding
          ? this.hold(i, pose, maxSpeed, sepRadius)
          : this.roam(pose, i, maxSpeed, sepRadius, dt);
        const sep = separation(pose, this.neighbours(i, scratch), sepRadius, maxSpeed);
        const wall = this.walls(i, maxSpeed);
        // Separation outweighs the goal, so a blob spreads instead of piling
        // onto one point; the walls outrank both. A bot with a slot of its own
        // only needs enough of it to not sit on a neighbour.
        const push = holding ? HOLD_SEPARATION : BLOB_SEPARATION;
        const desired = {
          x: goal.x + sep.x * push + wall.x * 3,
          y: goal.y + sep.y * push + wall.y * 3,
        };
        const mag = Math.hypot(desired.x, desired.y);
        if (mag > maxSpeed) {
          desired.x = (desired.x / mag) * maxSpeed;
          desired.y = (desired.y / mag) * maxSpeed;
        }
        ({ left, right } = driveTowards(pose, desired, maxPwm));
      }

      const vL = wheelSpeedFromPwm(left);
      const vR = wheelSpeedFromPwm(right);
      const next = unicycleStep(pose, vL, vR, dt);
      this.x[i] = Math.max(0, Math.min(this.side, next.x));
      this.y[i] = Math.max(0, Math.min(this.side, next.y));
      this.heading[i] = next.heading;
      motion = Math.max(motion, Math.abs(vL), Math.abs(vR));
      const travelled = (Math.abs(vL + vR) / 2) * dt;
      this.battery[i] = Math.max(
        0,
        this.battery[i] - travelled * DRAIN_V_PER_MM * this.tuning.drainScale,
      );
    }
    this.lastMotion = motion;
  }

  /**
   * x, y, heading per bot, packed for transfer to the renderer. Hues go once,
   * at seed time, since they never change.
   */
  snapshot(): Float32Array {
    const out = new Float32Array(this.count * 3);
    for (let i = 0; i < this.count; i++) {
      out[i * 3] = this.x[i];
      out[i * 3 + 1] = this.y[i];
      out[i * 3 + 2] = this.heading[i];
    }
    return out;
  }
}
