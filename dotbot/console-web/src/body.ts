// A robot's body from its pose: the shape of its model, as the controller's
// `robot_models` event gives it (axle at the origin, facing 0 degrees),
// turned by the pose's heading about the origin and moved onto its axle.

import { BotPose, LH2Position, RobotPose } from "./types";

export type RobotShapes = Record<string, BotPose>;

export const ROBOT_MODEL_DEFAULT = "dotbot-v3";

export function bodyOf(shape: BotPose, pose: RobotPose): BotPose {
  const theta = (pose.heading_deg * Math.PI) / 180;
  const cos = Math.cos(theta);
  const sin = Math.sin(theta);
  const place = (p: LH2Position): LH2Position => ({
    x: pose.x + p.x * cos - p.y * sin,
    y: pose.y + p.x * sin + p.y * cos,
  });
  return {
    heading_deg: pose.heading_deg,
    heading_source: pose.heading_source,
    photodiode: place(shape.photodiode),
    axle: place(shape.axle),
    centre: place(shape.centre),
    nose: place(shape.nose),
    led: place(shape.led),
    outline: shape.outline.map(place),
    wheels: shape.wheels.map((wheel) => wheel.map(place)),
    reach_mm: shape.reach_mm,
    core_mm: shape.core_mm,
    envelope_mm: shape.envelope_mm,
  };
}

// A pose object is replaced, never mutated, when the robot moves, so its body
// is built once per pose and shared by every rebuild until the next one.
const bodies = new WeakMap<RobotPose, { shape: BotPose; body: BotPose }>();

/** The body `pose` places for a robot of `model`, or null with no shape for it. */
export function robotBody(
  pose: RobotPose,
  model: string | undefined,
  shapes: RobotShapes,
): BotPose | null {
  const shape = shapes[model ?? ROBOT_MODEL_DEFAULT];
  if (!shape) return null;
  const cached = bodies.get(pose);
  if (cached && cached.shape === shape) return cached.body;
  const body = bodyOf(shape, pose);
  bodies.set(pose, { shape, body });
  return body;
}
