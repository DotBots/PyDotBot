import React from "react";

import type { RobotDrawing } from "./robotDrawing";
import type { BotPose, LH2Position, RgbLed } from "./types";

// The map marker. One colour rule holds at every level: the robot's fill is
// its swarmit state, a known heading is a white bar, and the LED colour is one
// sensor mark on the photodiode - hollow when the colour is unknown.
//
// The robot's shape is not authored here. The controller expands each
// photodiode fix into a body pose against its own geometry record and ships
// the board path with it, already rotated into the arena frame, so this module
// scales that path to the screen and nothing more.
//
// A pose whose heading the robot never reported is drawn as the sensor point
// alone. A guessed body is worse than a point, and a point is honest about
// what is known. Around it the possible footprint shows the room the body can
// take: the reach and the core radii the controller ships with the pose,
// which hold whichever way the robot faces.

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

/** On-screen diameter of a robot drawn as its sensor point, whatever the zoom. */
export const SENSOR_POINT_PX = 14;

/** Width of the heading bar a sensor point carries when its heading is known. */
const SENSOR_BAR_PX = 2.5;

/** On-screen diameter below which the possible footprint's ring is not drawn. */
export const FOOTPRINT_MIN_PX = 26;

const WHITE = "rgba(255,255,255,.95)";
const DARK = "rgba(0,0,0,.7)";

/** A sensor mark's fill for an LED commanded off. */
export const LED_OFF = "#161616";
const SHADOW =
  "drop-shadow(0 0 .9px rgba(0,0,0,.6)) drop-shadow(0 1px 2px rgba(0,0,0,.45))";

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
 * One robot's body to draw, in millimetres from the pose's photodiode, so it
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
  /** The robot's plan-view size, from the pose. */
  envelopeMm: number;
  source: BotPose["heading_source"];
}

/** Whether a pose says enough about the robot's orientation to draw a body. */
export function hasHeading(pose: BotPose | null | undefined): boolean {
  return !!pose && pose.heading_source !== "none";
}

/**
 * The body to draw around the pose's photodiode, or null when there is
 * nothing to draw one from: no pose, no heading, or an outline too short to
 * be a polygon.
 */
export function botBody(pose: BotPose | null | undefined): BotBody | null {
  if (!pose || !hasHeading(pose)) return null;
  if (pose.outline.length < 3) return null;
  const sensor = pose.photodiode;
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
    wheels: pose.wheels.map((wheel) => wheel.map(rel)),
    centre: rel(pose.centre),
    nose: rel(pose.nose),
    spanMm: Math.max(extent(forward), extent(across)),
    envelopeMm: pose.envelope_mm,
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

/**
 * What one robot is drawn as. `board` is the full glyph; `mark` a disc with
 * a heading bar and no rim, for a board too small to read; `disc` the real-size
 * envelope with its heading, for a board big enough but lost in a crowd;
 * `sensor` the photodiode point with the possible footprint around it, whose
 * radii are in screen pixels and null where they are not drawn.
 */
export type RobotShape =
  | { kind: "board"; body: BotBody }
  | { kind: "mark"; body: BotBody }
  | { kind: "disc"; body: BotBody; radiusPx: number }
  | {
      kind: "sensor";
      ringPx: number | null;
      corePx: number | null;
      crowded: boolean;
      /** The heading as a bar out from the point, when the pose has one. */
      bar: HeadingBarShape | null;
    };

/** A unit vector in screen axes, and how far out from the point it is drawn. */
export interface HeadingBarShape {
  dir: LH2Position;
  lengthPx: number;
}

export interface RobotDraw {
  shape: RobotShape;
  /** Where the chrome around the robot sits, in mm from the photodiode. */
  centre: LH2Position;
  /** The size on screen the chrome is laid out around. */
  footprintPx: number;
  /** Whether the chrome turns with the heading, hugging a drawn board. */
  turned: boolean;
  /** A board built on the travel bearing, drawn fainter as an estimate. */
  estimate: boolean;
  battery: boolean;
}

/** How a robot with this pose is drawn at this zoom, in a fleet of `botCount`. */
export function robotDraw(
  pose: BotPose | null | undefined,
  drawing: RobotDrawing,
  pxPerMm: number,
  botCount: number,
): RobotDraw {
  const body = drawing.mode === "body" ? botBody(pose) : null;
  if (body) {
    const footprintPx = botFootprintPx(pxPerMm, body.spanMm);
    const flat = { centre: body.centre, turned: false, estimate: false };
    if (glyphLevel(footprintPx, botCount) === "detail") {
      return {
        shape: { kind: "board", body },
        centre: body.centre,
        footprintPx,
        turned: true,
        estimate: body.source === "travel",
        battery: true,
      };
    }
    // Too small to read is a mark; readable but crowded out is the envelope.
    if (footprintPx < GLYPH_DETAIL_PX) {
      return { ...flat, shape: { kind: "mark", body }, footprintPx, battery: false };
    }
    const discPx = botFootprintPx(pxPerMm, body.envelopeMm);
    return {
      ...flat,
      shape: { kind: "disc", body, radiusPx: discPx / 2 },
      footprintPx: discPx,
      battery: false,
    };
  }

  const reachPx = pose ? pose.reach_mm * pxPerMm : 0;
  const corePx = pose ? pose.core_mm * pxPerMm : 0;
  const ring = drawing.footprint && 2 * reachPx >= FOOTPRINT_MIN_PX;
  const core = drawing.footprint && 2 * corePx >= SENSOR_POINT_PX + 4;
  const envelopePx = botFootprintPx(pxPerMm, pose ? pose.envelope_mm : 0);
  return {
    shape: {
      kind: "sensor",
      ringPx: ring ? reachPx : null,
      corePx: core ? corePx : null,
      crowded: botCount > GLYPH_CROWD_BOTS,
      bar: headingBar(pose, Math.max(SENSOR_POINT_PX, reachPx)),
    },
    centre: { x: 0, y: 0 },
    footprintPx: ring ? 2 * reachPx : SENSOR_POINT_PX,
    turned: false,
    estimate: false,
    battery: glyphLevel(envelopePx, botCount) === "detail",
  };
}

/** The pose's heading as a bar `lengthPx` long, or null when it has none. */
function headingBar(pose: BotPose | null | undefined, lengthPx: number): HeadingBarShape | null {
  if (!pose || !hasHeading(pose)) return null;
  const dx = pose.nose.x - pose.centre.x;
  const dy = pose.nose.y - pose.centre.y;
  const n = Math.hypot(dx, dy);
  if (n === 0) return null;
  return { dir: { x: dx / n, y: dy / n }, lengthPx };
}

/** How far from the photodiode the body reaches, in millimetres, tyres included. */
function reachMm(body: BotBody): number {
  const points = [...body.outline, ...body.wheels.flat()];
  return Math.max(...points.map((p) => Math.hypot(p.x, p.y)));
}

interface BotGlyphProps {
  /** The swarmit state colour: the robot's fill at every level. */
  state: string;
  /** The LED colour the controller commanded, or null when it is unknown. */
  led: RgbLed | null;
  shape: RobotShape;
  pxPerMm: number;
  /** The circle's diameter, for `mark`. */
  footprintPx: number;
  /**
   * A pose not yet placed, drawn as a dashed outline over a faint fill, and
   * the board's stroke colour. Only the board level reads it.
   */
  ghost?: boolean;
  outlineColor?: string;
}

const Frame: React.FC<{ half: number; children: React.ReactNode; filter?: boolean }> = ({
  half,
  children,
  filter = true,
}) => {
  const side = 2 * (half + 3);
  return (
    <svg
      viewBox={`${-side / 2} ${-side / 2} ${side} ${side}`}
      width={side}
      height={side}
      style={{ display: "block", overflow: "visible", filter: filter ? SHADOW : undefined }}
    >
      {children}
    </svg>
  );
};

/** The CSS colour a sensor mark is filled with, or null for a hollow one. */
export function ledFill(led: RgbLed | null): string | null {
  if (!led) return null;
  if (led.red === 0 && led.green === 0 && led.blue === 0) return LED_OFF;
  return `rgb(${led.red},${led.green},${led.blue})`;
}

/**
 * The one mark in the LED colour, at the origin: a white rim inside a dark
 * one, so it reads on a fill of its own colour and on either theme.
 */
const SensorMark: React.FC<{ r: number; led: RgbLed | null }> = ({ r, led }) => {
  const rim = Math.max(0.6, r / 3);
  const halo = Math.max(0.5, rim * 0.8);
  const fill = ledFill(led);
  if (fill === null) {
    return (
      <g data-layer="sensor-mark" data-led="unknown">
        <circle r={r} fill="none" stroke={DARK} strokeWidth={rim + 2 * halo} />
        <circle r={r} fill="none" stroke={WHITE} strokeWidth={rim} />
      </g>
    );
  }
  return (
    <g data-layer="sensor-mark" data-led={fill}>
      <circle r={r + rim / 2 + halo} fill={DARK} />
      <circle r={r} fill={fill} stroke={WHITE} strokeWidth={rim} />
    </g>
  );
};

/** A white bar from `from` along `dir`, `length` px long. */
const HeadingBar: React.FC<{
  from: LH2Position;
  dir: LH2Position;
  length: number;
  width: number;
  layer: string;
}> = ({ from, dir, length, width, layer }) => (
  <line
    data-layer={layer}
    x1={from.x}
    y1={from.y}
    x2={from.x + dir.x * length}
    y2={from.y + dir.y * length}
    stroke={WHITE}
    strokeWidth={width}
    strokeLinecap="round"
  />
);

const unit = (from: LH2Position, to: LH2Position): LH2Position => {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const n = Math.hypot(dx, dy) || 1;
  return { x: dx / n, y: dy / n };
};

const SensorPoint: React.FC<{
  state: string;
  led: RgbLed | null;
  ringPx: number | null;
  corePx: number | null;
  crowded: boolean;
  bar: HeadingBarShape | null;
}> = ({ state, led, ringPx, corePx, crowded, bar }) => {
  const pointR = SENSOR_POINT_PX / 2;
  return (
    <Frame half={Math.max(pointR + 2, ringPx ?? 0, bar?.lengthPx ?? 0)} filter={false}>
      {ringPx !== null && (
        <>
          {/* a solid casing under the dashes, so the ring stands off a
              camera picture or a floor of its own colour */}
          <circle
            data-layer="reach-casing"
            r={ringPx}
            fill="none"
            stroke="var(--footprint-casing)"
            strokeWidth={crowded ? 2.5 : 3.5}
          />
          <circle
            data-layer="reach"
            r={ringPx}
            fill={crowded ? "none" : state}
            fillOpacity={crowded ? undefined : 0.1}
            stroke={state}
            strokeOpacity={crowded ? 0.8 : 1}
            strokeWidth={crowded ? 1.25 : 2}
            strokeDasharray={`${Math.max(4, ringPx / 6)} ${Math.max(3, ringPx / 10)}`}
          />
        </>
      )}
      {corePx !== null && (
        <circle
          data-layer="core"
          r={corePx}
          fill={state}
          fillOpacity={0.6}
          stroke={state}
          strokeOpacity={0.9}
          strokeWidth={1}
        />
      )}
      {bar && (
        <g>
          {/* a dark edge, so the white bar reads off a light floor too */}
          <line
            data-layer="sensor-heading-casing"
            x1={0}
            y1={0}
            x2={bar.dir.x * bar.lengthPx}
            y2={bar.dir.y * bar.lengthPx}
            stroke={DARK}
            strokeWidth={SENSOR_BAR_PX + 1.5}
            strokeLinecap="round"
          />
          <HeadingBar
            layer="sensor-heading"
            from={{ x: 0, y: 0 }}
            dir={bar.dir}
            length={bar.lengthPx}
            width={SENSOR_BAR_PX}
          />
        </g>
      )}
      {/* the point the lighthouse reported: the sensor mark, rimmed in the
          state colour */}
      <g style={{ filter: SHADOW }}>
        <circle data-layer="sensor" r={pointR} fill={state} />
        <SensorMark r={pointR / 2} led={led} />
      </g>
    </Frame>
  );
};

/**
 * The bot as one SVG whose origin is the pose's photodiode, so the caller places
 * it at the point it already has and the body falls where the pose puts it.
 */
export const BotGlyph: React.FC<BotGlyphProps> = ({
  state,
  led,
  shape,
  pxPerMm,
  footprintPx,
  ghost = false,
  outlineColor = "rgba(0,0,0,.45)",
}) => {
  if (shape.kind === "sensor") return <SensorPoint state={state} led={led} {...shape} />;
  const body = shape.body;
  const px = (p: LH2Position): LH2Position => ({
    x: p.x * pxPerMm,
    y: p.y * pxPerMm,
  });
  const centre = px(body.centre);
  const dir = unit(centre, px(body.nose));
  const offset = Math.hypot(centre.x, centre.y);

  if (shape.kind === "mark" || shape.kind === "disc") {
    const r = shape.kind === "disc" ? shape.radiusPx : footprintPx / 2;
    // Floors keep the bar and the mark legible on the smallest circle.
    const barW = shape.kind === "disc" ? Math.max(1.2, r / 5) : Math.min(3, Math.max(1.2, r / 3.2));
    const markR = shape.kind === "disc" ? Math.max(2, Math.min(7, r * 0.2)) : Math.max(1.1, r * 0.16);
    return (
      <Frame half={offset + r}>
        <circle data-layer={shape.kind} cx={centre.x} cy={centre.y} r={r} fill={state} />
        <HeadingBar layer="heading" from={centre} dir={dir} length={r - 0.5} width={barW} />
        <SensorMark r={markR} led={led} />
      </Frame>
    );
  }

  const stroke = Math.max(0.6, footprintPx / 40);
  return (
    <Frame half={reachMm(body) * pxPerMm}>
      {/* the tyres, at the place and size the record gives them: the board is
          drawn over them, so only what sticks out shows */}
      {body.wheels.map((wheel, i) => (
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
        points={body.outline.map((p) => `${p.x * pxPerMm},${p.y * pxPerMm}`).join(" ")}
        fill={state}
        fillOpacity={ghost ? 0.3 : undefined}
        stroke={outlineColor}
        strokeWidth={ghost ? Math.max(1.5, stroke) : stroke}
        strokeDasharray={ghost ? `${4 * Math.max(1, stroke)} ${3 * Math.max(1, stroke)}` : undefined}
      />
      <SensorMark r={Math.max(2.6, Math.min(12, footprintPx * 0.085))} led={led} />
    </Frame>
  );
};
