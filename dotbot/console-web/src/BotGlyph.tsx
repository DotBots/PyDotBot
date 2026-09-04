import React from "react";

import { headingToGlyphRotation } from "./arenaFrame";

// The map marker, traced from the DotBot v3 board outline: one PCB, wide at the
// front and narrower between the wheels, with the tyres outboard of the narrow
// section. Geometry is authored nose-up in a 32-unit box centred on the bot, so
// one unit is size/32 px and every number below scales with the size prop.
export const BOT_GLYPH_BOX = 48;

// What the robot itself spans inside that box - 25 of the 32 units - for
// callers matching the glyph to a real-world footprint.
export const BOT_GLYPH_SPAN = (BOT_GLYPH_BOX * 25) / 32;

// Geometry in the 32-unit nose-up box, exported so a canvas renderer draws the
// same robot as the SVG marker.
export const BOARD =
  "M-10.7,-11.9 L10.7,-11.9 Q12,-11.9 12,-10.6 L12,-2.4 Q12,-1.1 10.7,-1.1 " +
  "L6.9,-1.1 L6.9,10.6 Q6.9,11.9 5.6,11.9 L-5.6,11.9 Q-6.9,11.9 -6.9,10.6 " +
  "L-6.9,-1.1 L-10.7,-1.1 Q-12,-1.1 -12,-2.4 L-12,-10.6 Q-12,-11.9 -10.7,-11.9 Z";

export const TYRES = [
  { x: -12.5, y: 0.2, w: 5.4, h: 11.3, r: 1.7 },
  { x: 7.1, y: 0.2, w: 5.4, h: 11.3, r: 1.7 },
];

const TREAD_Y = [2.2, 5.3, 8.4];

export const TREADS = TREAD_Y.flatMap((y) => [
  { x: -11.9, y, w: 4.2, h: 1.1, r: 0.55 },
  { x: 7.7, y, w: 4.2, h: 1.1, r: 0.55 },
]);

interface BotGlyphProps {
  color: string;
  heading: number | null; // degrees, 0 = +y, positive clockwise in the arena frame
  size?: number;
}

export const BotGlyph: React.FC<BotGlyphProps> = ({ color, heading, size = BOT_GLYPH_BOX }) => (
  <svg
    viewBox="-16 -16 32 32"
    width={size}
    height={size}
    style={{
      display: "block",
      overflow: "visible",
      filter: "drop-shadow(0 0 .9px rgba(0,0,0,.6)) drop-shadow(0 1px 2px rgba(0,0,0,.45))",
      transform:
        heading === null ? undefined : `rotate(${headingToGlyphRotation(heading)}deg)`,
    }}
  >
    {heading === null ? (
      // Drawing the outline unrotated would assert a north the bot never
      // reported, so a headingless bot gets a body with no front.
      <circle r="8.5" fill={color} />
    ) : (
      <>
        <g fill="var(--tyre)">
          {TYRES.map((t) => (
            <rect key={t.x} x={t.x} y={t.y} width={t.w} height={t.h} rx={t.r} />
          ))}
        </g>
        <g fill="#000" opacity={0.52}>
          {TREADS.map((t) => (
            <rect key={`${t.x},${t.y}`} x={t.x} y={t.y} width={t.w} height={t.h} rx={t.r} />
          ))}
        </g>
        <path d={BOARD} fill={color} />
      </>
    )}
  </svg>
);
