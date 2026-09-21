import React from "react";

import { headingToGlyphRotation } from "./frame";

// The map marker, traced from the DotBot v3 board outline: one PCB, wide at the
// front and narrower between the wheels, with the tyres outboard of the narrow
// section. Geometry is authored nose-up in a 32-unit box centred on the bot, so
// one unit is size/32 px and every number below scales with the size prop.
export const BOT_GLYPH_BOX = 48;

// What the robot itself spans inside that box - 25 of the 32 units - for
// callers matching the glyph to a real-world footprint.
export const BOT_GLYPH_SPAN = (BOT_GLYPH_BOX * 25) / 32;

/**
 * The robot's footprint on the floor. The v3 PCB outline is 94.00 mm across
 * by 95.00 mm deep, and the tyres fill the steps in its sides, so what the
 * robot occupies is about that square.
 */
export const BOT_FOOTPRINT_MM = 95;

/** Screen pixels a bot is drawn at however far the map zooms out. */
export const BOT_MIN_PX = 8;

/**
 * The footprint a bot is drawn at, in screen pixels: its true size, floored
 * where true size would be a speck too small to see or to click.
 */
export function botFootprintPx(pxPerMm: number): number {
  return Math.max(BOT_MIN_PX, BOT_FOOTPRINT_MM * pxPerMm);
}

/** The glyph box that draws a footprint of `footprintPx`. */
export function glyphBoxPx(footprintPx: number): number {
  return (footprintPx * BOT_GLYPH_BOX) / BOT_GLYPH_SPAN;
}

const BOARD =
  "M-10.7,-11.9 L10.7,-11.9 Q12,-11.9 12,-10.6 L12,-2.4 Q12,-1.1 10.7,-1.1 " +
  "L6.9,-1.1 L6.9,10.6 Q6.9,11.9 5.6,11.9 L-5.6,11.9 Q-6.9,11.9 -6.9,10.6 " +
  "L-6.9,-1.1 L-10.7,-1.1 Q-12,-1.1 -12,-2.4 L-12,-10.6 Q-12,-11.9 -10.7,-11.9 Z";

const TREAD_Y = [2.2, 5.3, 8.4];

/** How much of the robot is drawn: the board, or a mark. */
export type GlyphLevel = "detail" | "dot";

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
 * Which glyph a bot of this on-screen size gets. Zoom decides it; a crowded
 * map is marks at any zoom, since detail nobody can pick apart only costs
 * legibility.
 */
export function glyphLevel(footprintPx: number, botCount: number): GlyphLevel {
  if (botCount > GLYPH_CROWD_BOTS) return "dot";
  return footprintPx >= GLYPH_DETAIL_PX ? "detail" : "dot";
}

interface BotGlyphProps {
  color: string;
  heading: number | null; // degrees, 0 = +y, positive clockwise in the arena frame
  // A DotBot: drawn as the board even when it reports no heading, nose-up.
  footprint?: boolean;
  size?: number;
  level?: GlyphLevel;
}

const body = (color: string, board: boolean, level: GlyphLevel) => {
  if (!board) return <circle r="8.5" fill={color} />;
  // Too small for a front to read: position and state are all that is left.
  if (level === "dot") return <rect x="-10" y="-10" width="20" height="20" rx="3" fill={color} />;
  return (
    <>
      <g fill="var(--tyre)">
        <rect x="-12.5" y="0.2" width="5.4" height="11.3" rx="1.7" />
        <rect x="7.1" y="0.2" width="5.4" height="11.3" rx="1.7" />
      </g>
      <g fill="#000" opacity={0.52}>
        {TREAD_Y.map((y) => (
          <React.Fragment key={y}>
            <rect x="-11.9" y={y} width="4.2" height="1.1" rx="0.55" />
            <rect x="7.7" y={y} width="4.2" height="1.1" rx="0.55" />
          </React.Fragment>
        ))}
      </g>
      <path d={BOARD} fill={color} />
    </>
  );
};

export const BotGlyph: React.FC<BotGlyphProps> = ({
  color,
  heading,
  footprint = false,
  size = BOT_GLYPH_BOX,
  level = "detail",
}) => {
  const board = footprint || heading !== null;
  return (
    <svg
      viewBox="-16 -16 32 32"
      width={size}
      height={size}
      style={{
        display: "block",
        overflow: "visible",
        filter: "drop-shadow(0 0 .9px rgba(0,0,0,.6)) drop-shadow(0 1px 2px rgba(0,0,0,.45))",
        transform:
          heading === null || level === "dot"
            ? undefined
            : `rotate(${headingToGlyphRotation(heading)}deg)`,
      }}
    >
      {body(color, board, level)}
    </svg>
  );
};
