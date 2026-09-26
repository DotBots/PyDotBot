import React, { useCallback } from "react";

import { BotGlyph, TRAVEL_BODY_OPACITY, botFootprintPx, robotDraw } from "./BotGlyph";
import { headingToGlyphRotation } from "./frame";
import type { RobotDrawing } from "./robotDrawing";
import type { BotPose, LH2Position, RgbLed, UnifiedBot } from "./types";
import { ResetBadge, batteryColor, batteryPct, stateColor } from "./viewChrome";

// The selection ring hugs the robot: its footprint plus this on every side.
const SELECTION_PAD_PX = 3;
// A waypoint diamond is a fraction of the body of the robot it belongs to,
// held between a floor it can still be seen at and a cap that keeps it a
// marker rather than an object: a waypoint is a point on the floor.
export const WAYPOINT_OF_BODY = 0.3;
export const WAYPOINT_MIN_PX = 7;
export const WAYPOINT_MAX_PX = 14;
// Two poses this close, in mm, draw the same body.
const SAME_MM = 1e-6;

/** What a robot's marker draws of it. Where it is drawn is the animator's. */
export type MarkerBot = Pick<
  UnifiedBot,
  "id" | "state" | "severity" | "resetCause" | "battery" | "batteryPct" | "batteryLevel" | "led" | "pose" | "axle"
>;

/**
 * How a robot is drawn at this zoom. The robot is an object on the floor, so
 * it is drawn at the floor's own scale; zooming out floors it at a size that
 * can still be seen and clicked.
 */
export function botDraw(
  b: Pick<UnifiedBot, "pose" | "axle">,
  drawing: RobotDrawing,
  perMm: number,
  botCount: number,
) {
  let draw = robotDraw(b.pose, drawing, perMm, botCount);
  // The robot's own axle estimate places the body.
  if (b.axle && b.pose && draw.shape.kind === "board") {
    const dx = b.axle.x - b.pose.axle.x;
    const dy = b.axle.y - b.pose.axle.y;
    const move = (p: LH2Position): LH2Position => ({ x: p.x + dx, y: p.y + dy });
    const body = draw.shape.body;
    draw = {
      ...draw,
      centre: move(draw.centre),
      shape: {
        ...draw.shape,
        body: {
          ...body,
          outline: body.outline.map(move),
          wheels: body.wheels.map((w) => w.map(move)),
          centre: move(body.centre),
          nose: move(body.nose),
          axle: move(body.axle),
        },
      },
    };
  }
  const { footprintPx } = draw;
  return {
    draw,
    footprintPx,
    // What sits around the robot - selection, badges, labels - is chrome,
    // and keeps its size on screen whatever the camera does.
    selectionPx: footprintPx + SELECTION_PAD_PX * 2,
    // Sized from the body, never from the possible footprint's ring.
    waypointPx: Math.min(
      WAYPOINT_MAX_PX,
      Math.max(
        WAYPOINT_MIN_PX,
        (draw.shape.kind === "sensor"
          ? botFootprintPx(perMm, b.pose ? b.pose.envelope_mm : 0)
          : footprintPx) * WAYPOINT_OF_BODY,
      ),
    ),
    batteryPx: Math.max(14, Math.min(28, footprintPx)),
  };
}

const near = (a: LH2Position, b: LH2Position, da: LH2Position, db: LH2Position) =>
  Math.abs(a.x - da.x - (b.x - db.x)) < SAME_MM && Math.abs(a.y - da.y - (b.y - db.y)) < SAME_MM;

/** Whether two poses draw the same body about their photodiode, wherever it is. */
function sameBody(a: BotPose | null, b: BotPose | null): boolean {
  if (a === b) return true;
  if (!a || !b) return false;
  if (
    a.heading_deg !== b.heading_deg ||
    a.heading_source !== b.heading_source ||
    a.reach_mm !== b.reach_mm ||
    a.core_mm !== b.core_mm ||
    a.envelope_mm !== b.envelope_mm ||
    a.outline.length !== b.outline.length ||
    a.wheels.length !== b.wheels.length
  ) {
    return false;
  }
  const pa = a.photodiode;
  const pb = b.photodiode;
  const points = (p: BotPose) => [p.axle, p.centre, p.nose, p.led, ...p.outline, ...p.wheels.flat()];
  const qa = points(a);
  const qb = points(b);
  return qa.length === qb.length && qa.every((q, i) => near(q, qb[i], pa, pb));
}

const sameLed = (a: RgbLed | null, b: RgbLed | null) =>
  a === b || (!!a && !!b && a.red === b.red && a.green === b.green && a.blue === b.blue);

/** Whether a robot's marker would draw the same for both, position aside. */
export function sameMarkerBot(a: MarkerBot, b: MarkerBot): boolean {
  if (a === b) return true;
  if (
    a.id !== b.id ||
    a.state !== b.state ||
    a.severity !== b.severity ||
    a.resetCause !== b.resetCause ||
    a.batteryLevel !== b.batteryLevel ||
    batteryPct(a) !== batteryPct(b) ||
    !sameLed(a.led, b.led) ||
    !sameBody(a.pose, b.pose)
  ) {
    return false;
  }
  // The robot's own axle estimate, as an offset from the pose's.
  if (!a.axle || !b.axle || !a.pose || !b.pose) return !a.axle === !b.axle;
  return near(a.axle, b.axle, a.pose.axle, b.pose.axle);
}

export interface BotMarkerProps {
  bot: MarkerBot;
  selected: boolean;
  hovered: boolean;
  /** How solid the board is drawn, from the camera layers under the robot. */
  solid: number;
  /** The camera's inverse scale: chrome keeps its size on screen. */
  chrome: number;
  perMm: number;
  drawing: RobotDrawing;
  botCount: number;
  batteryBars: boolean;
  attach: (id: string, el: HTMLElement | null) => void;
  onPointerDown: (e: React.PointerEvent, id: string) => void;
  onHover: React.Dispatch<React.SetStateAction<string | null>>;
}

/**
 * One robot on the map: the glyph, its chrome and the chip label. It
 * re-renders only when what it draws changes; its position is written by the
 * animator `attach` hands the element to.
 */
export const BotMarker = React.memo(function BotMarker({
  bot: b,
  selected,
  hovered,
  solid,
  chrome,
  perMm,
  drawing,
  botCount,
  batteryBars,
  attach,
  onPointerDown,
  onHover,
}: BotMarkerProps) {
  const ref = useCallback((el: HTMLDivElement | null) => attach(b.id, el), [attach, b.id]);
  const stc = stateColor(b.state);
  const pct = batteryPct(b);
  const blink = b.state === "Programming" || b.state === "Resetting";
  // A robot drawn as a mark is one nobody reads per-robot detail on, so its
  // own indicators go with the board: the selection ring and the reset badge
  // stay, being how a robot is found rather than what it says.
  const { draw, footprintPx, selectionPx, batteryPx } = botDraw(b, drawing, perMm, botCount);
  // The board is drawn where the pose puts it, which is not where the
  // photodiode is: the chrome goes with the board, so the ring and the label
  // stay around the robot rather than around its sensor.
  const bodyDx = draw.centre.x * perMm;
  const bodyDy = draw.centre.y * perMm;
  // A body built on the travel bearing is an estimate: it is right while the
  // robot drives straight and wrong the rest of the time, so it is drawn as one.
  const bodySolid = solid * (draw.estimate ? TRAVEL_BODY_OPACITY : 1);
  // The board turns with the heading; the ring around it turns too, so it
  // hugs the board whichever way the robot faces.
  const turned = draw.turned;
  const turn = turned ? headingToGlyphRotation(b.pose!.heading_deg) : 0;
  // How far below the centre a turned box reaches, as a fraction of its half side.
  const reach = turned
    ? Math.abs(Math.cos((turn * Math.PI) / 180)) + Math.abs(Math.sin((turn * Math.PI) / 180))
    : 1;
  return (
    <div
      ref={ref}
      id={`bot-${b.id}`}
      onPointerDown={(e) => onPointerDown(e, b.id)}
      onPointerEnter={() => onHover(b.id)}
      onPointerLeave={() => onHover((h) => (h === b.id ? null : h))}
      style={{
        position: "absolute",
        transform: `translate(-50%, -50%) scale(${chrome})`,
        cursor: "pointer",
        zIndex: selected ? 6 : 2,
        width: 0,
        height: 0,
      }}
    >
      {/* Everything that marks the robot out rides on its body, which is not
          where its sensor is. */}
      <div style={{ position: "absolute", left: bodyDx, top: bodyDy, width: 0, height: 0 }}>
        {/* last-reset warning, centred over the glyph body */}
        <div
          style={{
            position: "absolute",
            left: "50%",
            top: "50%",
            transform: "translate(-50%, -50%)",
            zIndex: 3,
          }}
        >
          <ResetBadge bot={b} size={13} />
        </div>
        {/* selection ring, hugging the board */}
        {selected && (
          <div
            data-testid={`selection-${b.id}`}
            style={{
              position: "absolute",
              left: "50%",
              top: "50%",
              width: selectionPx,
              height: selectionPx,
              transform: `translate(-50%, -50%) rotate(${turn}deg)`,
              border: "1.5px solid var(--accent)",
              // Square around a board, round around anything round.
              borderRadius: turned ? 3 : "50%",
              boxShadow: "0 0 0 3px color-mix(in srgb, var(--accent) 14%, transparent)",
            }}
          />
        )}
        {/* battery bar */}
        {batteryBars && draw.battery && (
          <div
            data-testid={`battery-${b.id}`}
            style={{
              position: "absolute",
              left: "50%",
              top: -footprintPx / 2 - 11,
              transform: "translateX(-50%)",
              width: batteryPx,
              height: 3,
              background: "rgba(255,255,255,.2)",
              borderRadius: 2,
            }}
          >
            <div style={{ height: "100%", width: `${pct}%`, background: batteryColor(b), borderRadius: 2 }} />
          </div>
        )}
        {/* chip label: selected or hovered only */}
        {(selected || hovered) && (
          <div
            style={{
              position: "absolute",
              left: "50%",
              top: ((selected ? selectionPx : footprintPx) / 2) * reach + 3,
              transform: "translateX(-50%)",
              font: "600 9px/1 var(--font-mono)",
              letterSpacing: ".5px",
              color: "var(--text)",
              background: "var(--elevated)",
              padding: "2px 5px",
              borderRadius: 3,
              whiteSpace: "nowrap",
              boxShadow: "0 1px 3px rgba(0,0,0,.4)",
              pointerEvents: "none",
            }}
          >
            {b.id.slice(-4).toUpperCase()}
          </div>
        )}
      </div>
      {/* The body, hung off the photodiode fix this container sits on: the
          pose puts it where it belongs. */}
      <div
        data-testid={`glyph-${b.id}`}
        data-shape={draw.shape.kind}
        style={{
          position: "absolute",
          left: "50%",
          top: "50%",
          transform: "translate(-50%, -50%)",
          opacity: bodySolid < 1 ? bodySolid : undefined,
          animation: blink ? "dbBlink 1.1s ease-in-out infinite" : undefined,
        }}
      >
        <BotGlyph state={stc} led={b.led} shape={draw.shape} pxPerMm={perMm} footprintPx={footprintPx} />
      </div>
    </div>
  );
}, sameMarkerProps);

function sameMarkerProps(a: BotMarkerProps, b: BotMarkerProps): boolean {
  return (
    a.selected === b.selected &&
    a.hovered === b.hovered &&
    a.solid === b.solid &&
    a.chrome === b.chrome &&
    a.perMm === b.perMm &&
    a.drawing === b.drawing &&
    a.botCount === b.botCount &&
    a.batteryBars === b.batteryBars &&
    a.attach === b.attach &&
    a.onPointerDown === b.onPointerDown &&
    a.onHover === b.onHover &&
    sameMarkerBot(a.bot, b.bot)
  );
}
