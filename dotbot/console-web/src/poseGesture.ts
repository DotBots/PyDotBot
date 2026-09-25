import type { BotPose, LH2Position, Waypoint } from "./types";

// Placing a waypoint, and a pose: a press that is released quickly and still
// queues a position; one held or dragged turns into the robot's silhouette,
// which faces the cursor once the cursor is far enough out to aim with.
//
// Headings are the console's convention throughout, which is also the
// robot's: forward = (-sin h, +cos h) in frame axes, x right and y down, so
// 0 faces down the map and 270 faces right.

/** How long a still press is held before it becomes a pose. */
export const HOLD_MS = 350;
/** When the ring announcing the hold starts to fill. */
export const RING_MS = 150;
/** How far a press moves before it is a drag rather than a click. */
export const DRAG_PX = 5;
/** How far out the cursor has to be before the silhouette faces it. */
export const ARM_PX = 24;
/** The detent Shift snaps a heading to. */
export const SNAP_DEG = 15;

export type GesturePhase = "pressing" | "silhouette" | "rotating";

export interface PoseGesture {
  phase: GesturePhase;
  /** Where the press landed, in client pixels, for the drag threshold. */
  press: { x: number; y: number };
  /** The point the silhouette pivots on, in client pixels. */
  pivot: { x: number; y: number };
  /** What a quick release queues: the point pressed, in frame mm. */
  at: LH2Position;
  /** Where a pose is anchored, in frame mm: the axle's resting point. */
  poseAt: LH2Position;
  /** The heading the silhouette is drawn at. */
  heading: number;
  t0: number;
}

/** A heading in [0, 360). */
export function normDeg(deg: number): number {
  const d = deg % 360;
  return d < 0 ? d + 360 : d === 0 ? 0 : d;
}

/** The heading that faces along (dx, dy), in frame or screen axes alike. */
export function headingOf(dx: number, dy: number): number {
  return normDeg((Math.atan2(-dx, dy) * 180) / Math.PI);
}

/** A heading on the nearest `step` detent. */
export function snapDeg(deg: number, step = SNAP_DEG): number {
  return normDeg(Math.round(deg / step) * step);
}

export function startGesture(
  press: { x: number; y: number },
  at: LH2Position,
  t0: number,
  heading: number,
  pivot: { x: number; y: number } = press,
  poseAt: LH2Position = at,
): PoseGesture {
  return { phase: "pressing", press, pivot, at, poseAt, heading, t0 };
}

/** The gesture once `t` has passed with the button still down. */
export function tickGesture(g: PoseGesture, t: number): PoseGesture {
  if (g.phase === "pressing" && t - g.t0 >= HOLD_MS) return { ...g, phase: "silhouette" };
  return g;
}

/** The gesture with the cursor at (x, y); `snap` is Shift, read live. */
export function moveGesture(
  g: PoseGesture,
  x: number,
  y: number,
  t: number,
  snap: boolean,
): PoseGesture {
  let next = tickGesture(g, t);
  if (
    next.phase === "pressing" &&
    Math.hypot(x - g.press.x, y - g.press.y) >= DRAG_PX
  ) {
    next = { ...next, phase: "silhouette" };
  }
  if (next.phase === "pressing") return next;
  const dx = x - g.pivot.x;
  const dy = y - g.pivot.y;
  if (Math.hypot(dx, dy) < ARM_PX) return { ...next, phase: "silhouette" };
  const free = headingOf(dx, dy);
  return { ...next, phase: "rotating", heading: snap ? snapDeg(free) : free };
}

/**
 * What releasing at (x, y) queues. A heading is only ever set by pointing:
 * a release inside the arming radius is a position, and so is a press held
 * where it landed without the silhouette having turned.
 */
export function releaseGesture(
  g: PoseGesture,
  x: number,
  y: number,
  t: number,
  snap: boolean,
): Waypoint {
  const last = moveGesture(g, x, y, t, snap);
  const still = g.phase !== "rotating" && Math.hypot(x - g.press.x, y - g.press.y) < DRAG_PX;
  if (last.phase !== "rotating" || still) return { ...g.at };
  return { ...g.poseAt, heading_deg: last.heading };
}

/** The bearing from `from` to `to`, or null when they coincide. */
export function bearing(from: LH2Position, to: LH2Position): number | null {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  if (Math.hypot(dx, dy) < 1) return null;
  return headingOf(dx, dy);
}

// --- the silhouette -------------------------------------------------------

/**
 * A robot's pose moved so its axle rests on `axle`, facing `heading`. The
 * body is the one the controller expanded for `template`, turned about its
 * axle by the difference in headings, so the silhouette is the real robot.
 */
export function poseAt(template: BotPose, axle: LH2Position, heading: number): BotPose {
  const d = ((heading - template.heading_deg) * Math.PI) / 180;
  const c = Math.cos(d);
  const s = Math.sin(d);
  const move = (p: LH2Position): LH2Position => {
    const x = p.x - template.axle.x;
    const y = p.y - template.axle.y;
    return { x: axle.x + x * c - y * s, y: axle.y + x * s + y * c };
  };
  return {
    ...template,
    heading_deg: normDeg(heading),
    heading_source: "ekf",
    photodiode: move(template.photodiode),
    axle: { ...axle },
    centre: move(template.centre),
    nose: move(template.nose),
    led: move(template.led),
    outline: template.outline.map(move),
    wheels: template.wheels.map((w) => w.map(move)),
  };
}

/**
 * A body to borrow for a silhouette: the first of `ids` with one, else any
 * robot's, since a fleet shares one geometry. A pose expanded on a placeholder
 * heading still has the right shape about its own axle, so it serves too.
 */
export function silhouetteTemplate(
  bots: { id: string; pose: BotPose | null }[],
  ids: Iterable<string>,
): BotPose | null {
  const wanted = new Set(ids);
  const usable = (p: BotPose | null): p is BotPose => !!p && p.outline.length >= 3;
  return (
    bots.find((b) => wanted.has(b.id) && usable(b.pose))?.pose ??
    bots.find((b) => usable(b.pose))?.pose ??
    null
  );
}

/** Whether a waypoint carries a heading, which makes it a pose. */
export const isPose = (w: Waypoint): w is Waypoint & { heading_deg: number } =>
  typeof w.heading_deg === "number" && Number.isFinite(w.heading_deg);

/**
 * Wheel steps over a queued pose: one per notch, and one per `pxPerStep` of
 * accumulated trackpad scroll so a two-finger swipe does not spin it.
 */
export function wheelSteps(
  carry: number,
  deltaY: number,
  deltaMode: number,
  pxPerStep = 60,
): { steps: number; carry: number } {
  if (deltaMode !== 0) {
    const steps = Math.sign(deltaY) * Math.max(1, Math.round(Math.abs(deltaY) / 3));
    return { steps, carry: 0 };
  }
  // A mouse notch arrives as one large pixel delta; count it as a step.
  if (Math.abs(deltaY) >= 100) return { steps: Math.sign(deltaY), carry: 0 };
  const total = carry + deltaY;
  const steps = Math.trunc(total / pxPerStep);
  return { steps, carry: total - steps * pxPerStep };
}
