import React from "react";

import { BotBody, BotGlyph, botBody } from "./BotGlyph";
import { poseAt } from "./poseGesture";
import type { BotPose, LH2Position } from "./types";

// A pose waypoint on the map: the robot's own silhouette with its axle on the
// waypoint, or, with no body to borrow or too small to read, a diamond with a
// tick toward the heading. The caller places this at the anchor, in screen
// pixels, the way it places a robot.

/** Screen pixels from the nose, or the tick's end, to the rotate knob. */
export const KNOB_GAP_PX = 10;
export const KNOB_R_PX = 5;

export type PoseLook = "unarmed" | "aiming" | "queued" | "active";

export type PoseShape =
  | { kind: "board"; pose: BotPose; body: BotBody; footprintPx: number }
  | { kind: "arrow" };

/** Screen pixels of footprint a pose needs before it is drawn as the robot. */
export const POSE_BOARD_MIN_PX = 12;

/**
 * What a pose at `anchor` facing `heading` is drawn as: the borrowed body
 * when there is one and it is big enough to read, a circle with an arrow
 * otherwise.
 */
export function poseShape(
  template: BotPose | null,
  anchor: LH2Position,
  heading: number,
  pxPerMm: number,
): PoseShape {
  if (!template) return { kind: "arrow" };
  const pose = poseAt(template, anchor, heading);
  const body = botBody(pose);
  if (!body) return { kind: "arrow" };
  const footprintPx = body.spanMm * pxPerMm;
  return footprintPx >= POSE_BOARD_MIN_PX ? { kind: "board", pose, body, footprintPx } : { kind: "arrow" };
}

/** How far from its axle the robot reaches, board and tyres, in mm. */
export function axleReachMm(pose: BotPose): number {
  const points = [...pose.outline, ...pose.wheels.flat()];
  return Math.max(0, ...points.map((p) => Math.hypot(p.x - pose.axle.x, p.y - pose.axle.y)));
}

/** The unit vector a heading faces, in screen axes. */
export const facing = (heading: number): LH2Position => {
  const r = (heading * Math.PI) / 180;
  return { x: -Math.sin(r), y: Math.cos(r) };
};

/** Where the knob sits, in screen pixels from the anchor. */
export function knobOffset(shape: PoseShape, heading: number, pxPerMm: number, tickPx: number): LH2Position {
  const f = facing(heading);
  if (shape.kind === "arrow") {
    return { x: f.x * (tickPx + KNOB_GAP_PX), y: f.y * (tickPx + KNOB_GAP_PX) };
  }
  const { nose, axle } = shape.pose;
  const ahead = ((nose.x - axle.x) * f.x + (nose.y - axle.y) * f.y) * pxPerMm;
  return { x: f.x * (ahead + KNOB_GAP_PX), y: f.y * (ahead + KNOB_GAP_PX) };
}

interface PoseMarkerProps {
  template: BotPose | null;
  anchor: LH2Position;
  heading: number;
  pxPerMm: number;
  /** The robot's LED colour, or the accent. */
  color: string;
  look: PoseLook;
  /** The waypoint's place in its queue, from 1. */
  index?: number;
  /** How many robots share this pose, when more than one. */
  shared?: number;
  /** Diamond size, as the plain waypoints around it are drawn. */
  diamondPx: number;
  knob?: boolean;
  onKnobDown?: (e: React.PointerEvent) => void;
  testId?: string;
}

export const PoseMarker: React.FC<PoseMarkerProps> = ({
  template,
  anchor,
  heading,
  pxPerMm,
  color,
  look,
  index,
  shared,
  diamondPx,
  knob = false,
  onKnobDown,
  testId,
}) => {
  const shape = poseShape(template, anchor, heading, pxPerMm);
  const f = facing(heading);
  const tickPx = diamondPx * 1.8;
  const ghost = look === "unarmed" || look === "aiming";
  const faint = look === "unarmed";
  const k = knobOffset(shape, heading, pxPerMm, tickPx);
  // The arrow says "the robot will face this way": from the nose, or from
  // the circle's rim, out along the heading, with a head.
  const ringR = Math.max(5, diamondPx * 0.6);
  const noseOut =
    shape.kind === "board"
      ? ((shape.pose.nose.x - anchor.x) * f.x + (shape.pose.nose.y - anchor.y) * f.y) * pxPerMm
      : ringR;
  const arrowFrom = noseOut + 1;
  const arrowTo = noseOut + (shape.kind === "board" ? Math.max(9, shape.footprintPx * 0.35) : tickPx);
  const head = 5;
  const side = { x: -f.y, y: f.x };
  const tip = { x: f.x * arrowTo, y: f.y * arrowTo };
  const headPoints = [
    tip,
    { x: tip.x - f.x * head * 1.6 + side.x * head, y: tip.y - f.y * head * 1.6 + side.y * head },
    { x: tip.x - f.x * head * 1.6 - side.x * head, y: tip.y - f.y * head * 1.6 - side.y * head },
  ]
    .map((q) => `${q.x},${q.y}`)
    .join(" ");

  let glyph: React.ReactNode = null;
  if (shape.kind === "board") {
    const dx = (shape.pose.photodiode.x - anchor.x) * pxPerMm;
    const dy = (shape.pose.photodiode.y - anchor.y) * pxPerMm;
    glyph = (
      <div
        style={{
          position: "absolute",
          left: dx,
          top: dy,
          transform: "translate(-50%, -50%)",
          opacity: faint ? 0.55 : look === "active" ? 0.85 : 1,
        }}
      >
        <BotGlyph
          state={color}
          led={null}
          shape={{ kind: "board", body: shape.body }}
          pxPerMm={pxPerMm}
          footprintPx={Math.max(shape.footprintPx, 16)}
          ghost={ghost || look === "queued"}
          outlineColor={ghost ? "var(--text)" : color}
        />
      </div>
    );
  }

  const half = Math.max(arrowTo + head, Math.hypot(k.x, k.y)) + KNOB_R_PX + 4;
  const labelAt = shape.kind === "board" ? Math.max(12, shape.footprintPx * 0.55) : ringR + 7;
  return (
    <div
      data-testid={testId}
      data-pose-shape={shape.kind}
      data-heading={Math.round(heading)}
      data-look={look}
      style={{ position: "absolute", width: 0, height: 0, pointerEvents: "none" }}
    >
      {glyph}
      <svg
        width={2 * half}
        height={2 * half}
        viewBox={`${-half} ${-half} ${2 * half} ${2 * half}`}
        style={{ position: "absolute", left: -half, top: -half, overflow: "visible" }}
      >
        {shape.kind === "arrow" && (
          <circle
            data-layer="pose-ring"
            r={ringR}
            fill={look === "active" ? color : "var(--canvas)"}
            fillOpacity={look === "active" ? 1 : 0.85}
            stroke={color}
            strokeWidth={2}
            strokeDasharray={ghost ? "3 2" : undefined}
            opacity={faint ? 0.6 : 1}
          />
        )}
        <g data-layer="pose-arrow" opacity={faint ? 0.6 : 1}>
          <line
            x1={f.x * arrowFrom}
            y1={f.y * arrowFrom}
            x2={tip.x - f.x * head}
            y2={tip.y - f.y * head}
            stroke={color}
            strokeWidth={2.5}
            strokeLinecap="round"
          />
          <polygon points={headPoints} fill={color} stroke="var(--canvas)" strokeWidth={0.75} />
        </g>
        {index !== undefined && (
          <text
            x={-f.x * labelAt}
            y={-f.y * labelAt + 3.5}
            textAnchor="middle"
            style={{ font: "700 10px/1 var(--font-mono)", paintOrder: "stroke" }}
            fill="var(--text)"
            stroke="var(--canvas)"
            strokeWidth={3}
          >
            {index}
          </text>
        )}
        {shared !== undefined && shared > 1 && (
          <text
            data-layer="pose-shared"
            x={10}
            y={-10}
            style={{ font: "600 9px/1 var(--font-mono)", paintOrder: "stroke" }}
            fill="var(--s-Programming)"
            stroke="var(--canvas)"
            strokeWidth={3}
          >
            ×{shared}
          </text>
        )}
        {knob && (
          <circle
            data-testid={testId ? `${testId}-knob` : undefined}
            cx={k.x}
            cy={k.y}
            r={KNOB_R_PX}
            fill="var(--surface)"
            stroke={color}
            strokeWidth={2}
            style={{ pointerEvents: "auto", cursor: "grab" }}
            onPointerDown={onKnobDown}
          />
        )}
      </svg>
    </div>
  );
};
