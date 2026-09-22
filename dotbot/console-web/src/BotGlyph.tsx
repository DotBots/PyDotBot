import React from "react";

import type { BotPose, LH2Position } from "./types";

// The map marker: one robot in three layers, the board outline, a line from
// its centre to its nose, and a dot on the photodiode the fix came from.
//
// The robot's shape is not authored here. The controller expands each
// photodiode fix into a body pose against its own geometry record and ships
// the board path with it, already rotated into the arena frame, so this module
// scales that path to the screen and nothing more. The camera layer draws its
// detector's pose in the same three layers from the same record, which is why
// the two read as the same robot.
//
// A pose whose heading the robot never reported is drawn as the photodiode
// point alone. A guessed body is worse than a dot, and a dot is honest about
// what is known.

/** Screen pixels a bot is drawn at however far the map zooms out. */
export const BOT_MIN_PX = 8;

/**
 * Screen pixels of footprint the board outline needs before it reads. Judged
 * from the map at each zoom level, with a bot turned 45 degrees so the
 * outline is at its hardest to make out: at 17 px the stepped board and one
 * tyre are still there, at 11 px it is a coloured blob.
 */
export const GLYPH_DETAIL_PX = 16;

/** Past this many bots the map drops a level: the detail is lost in a crowd. */
export const GLYPH_CROWD_BOTS = 200;

/**
 * How solid a body built on a travel bearing is drawn. The bearing is the
 * robot's direction of travel, which is its heading only while it drives
 * straight, so the body is drawn as an estimate rather than as a measurement.
 */
export const TRAVEL_BODY_OPACITY = 0.78;

/** Radius of the photodiode dot, in millimetres, as the camera layer draws it. */
const SENSOR_DOT_MM = 4;

/** How much of the robot is drawn: the board, or a mark. */
export type GlyphLevel = "detail" | "dot";

/**
 * Which glyph a bot of this on-screen size gets. Zoom decides it; a crowded
 * map is marks at any zoom, since detail nobody can pick apart only costs
 * legibility.
 */
export function glyphLevel(footprintPx: number, botCount: number): GlyphLevel {
  if (botCount > GLYPH_CROWD_BOTS) return "dot";
  return footprintPx >= GLYPH_DETAIL_PX ? "detail" : "dot";
}

/**
 * One robot's body to draw, in millimetres from its own photodiode fix, so it
 * can be hung off the point the map already places the bot at.
 *
 * `spanMm` is the body's own size, measured along its heading and across it,
 * rather than the box it happens to occupy in the arena frame - a square board
 * turned 45 degrees spans half again as much there, and the chrome around it
 * would grow and shrink as the robot turned.
 */
export interface BotBody {
  outline: LH2Position[];
  wheels: LH2Position[][];
  centre: LH2Position;
  nose: LH2Position;
  spanMm: number;
  source: BotPose["heading_source"];
}

/** Whether a pose says enough about the robot's orientation to draw a body. */
export function hasHeading(pose: BotPose | null | undefined): boolean {
  return !!pose && pose.heading_source !== "none";
}

/**
 * The body to draw around a fix at `sensor`, or null when there is nothing to
 * draw one from: no pose, no fix, no heading, or an outline too short to be a
 * polygon.
 */
export function botBody(
  pose: BotPose | null | undefined,
  sensor: LH2Position | null,
): BotBody | null {
  if (!pose || !sensor || !hasHeading(pose)) return null;
  if (pose.outline.length < 3) return null;
  const rel = (p: LH2Position): LH2Position => ({
    x: p.x - sensor.x,
    y: p.y - sensor.y,
  });
  const outline = pose.outline.map(rel);
  const theta = (pose.heading_deg * Math.PI) / 180;
  const forward: LH2Position = { x: -Math.sin(theta), y: Math.cos(theta) };
  const across: LH2Position = { x: -forward.y, y: forward.x };
  const extent = (axis: LH2Position): number => {
    const along = outline.map((p) => p.x * axis.x + p.y * axis.y);
    return Math.max(...along) - Math.min(...along);
  };
  return {
    outline,
    wheels: (pose.wheels ?? []).map((wheel) => wheel.map(rel)),
    centre: rel(pose.centre),
    nose: rel(pose.nose),
    spanMm: Math.max(extent(forward), extent(across)),
    source: pose.heading_source,
  };
}

/**
 * The footprint a bot is drawn at, in screen pixels: its true size, floored
 * where true size would be a speck too small to see or to click. A bot with
 * no body is that floor, being a point rather than an area.
 */
export function botFootprintPx(pxPerMm: number, spanMm: number): number {
  return Math.max(BOT_MIN_PX, spanMm * pxPerMm);
}

/** How far from the fix the body reaches, in millimetres, tyres included. */
function reachMm(body: BotBody): number {
  const points = [...body.outline, ...body.wheels.flat()];
  return Math.max(...points.map((p) => Math.hypot(p.x, p.y)));
}

interface BotGlyphProps {
  color: string;
  /** Null draws the photodiode point alone. */
  body: BotBody | null;
  pxPerMm: number;
  footprintPx: number;
  level?: GlyphLevel;
}

/**
 * The bot as one SVG whose origin is its photodiode fix, so the caller places
 * it at the point it already has and the body falls where the pose puts it.
 */
export const BotGlyph: React.FC<BotGlyphProps> = ({
  color,
  body,
  pxPerMm,
  footprintPx,
  level = "detail",
}) => {
  const px = (p: LH2Position): LH2Position => ({
    x: p.x * pxPerMm,
    y: p.y * pxPerMm,
  });
  const detail = body !== null && level === "detail";
  // Half the box the drawing needs, measured from the fix at its origin.
  const half = !body
    ? footprintPx / 2
    : detail
      ? reachMm(body) * pxPerMm
      : Math.hypot(body.centre.x, body.centre.y) * pxPerMm + footprintPx / 2;
  const side = 2 * (half + 2);
  const mark = body ? px(body.centre) : { x: 0, y: 0 };
  const stroke = Math.max(0.6, footprintPx / 40);
  return (
    <svg
      viewBox={`${-side / 2} ${-side / 2} ${side} ${side}`}
      width={side}
      height={side}
      style={{
        display: "block",
        filter: "drop-shadow(0 0 .9px rgba(0,0,0,.6)) drop-shadow(0 1px 2px rgba(0,0,0,.45))",
      }}
    >
      {!body && <circle r={footprintPx / 2} fill={color} />}
      {body && !detail && (
        <rect
          x={mark.x - footprintPx / 2}
          y={mark.y - footprintPx / 2}
          width={footprintPx}
          height={footprintPx}
          rx={Math.min(3, footprintPx / 4)}
          fill={color}
        />
      )}
      {detail && (
        <>
          {/* the tyres, at the place and size the record gives them: the
              board is drawn over them, so only what sticks out shows */}
          {body!.wheels.map((wheel, i) => (
            <polygon
              key={i}
              data-layer="wheel"
              points={wheel.map((p) => `${p.x * pxPerMm},${p.y * pxPerMm}`).join(" ")}
              fill="var(--tyre)"
              stroke="rgba(0,0,0,.45)"
              strokeWidth={stroke}
            />
          ))}
          <polygon
            data-layer="board"
            points={body!.outline.map((p) => `${p.x * pxPerMm},${p.y * pxPerMm}`).join(" ")}
            fill={color}
            stroke="rgba(0,0,0,.45)"
            strokeWidth={stroke}
          />
          {/* which way it faces: the centre of the board out to its nose */}
          <line
            x1={mark.x}
            y1={mark.y}
            x2={px(body!.nose).x}
            y2={px(body!.nose).y}
            stroke="rgba(255,255,255,.95)"
            strokeWidth={Math.max(1, footprintPx / 16)}
            strokeLinecap="round"
          />
          {/* the photodiode, which is the point the lighthouse reported, at
              the size the camera layer draws its own */}
          <circle
            r={Math.max(1.1, SENSOR_DOT_MM * pxPerMm)}
            fill="#111"
            stroke="rgba(255,255,255,.85)"
            strokeWidth={stroke}
          />
        </>
      )}
    </svg>
  );
};
