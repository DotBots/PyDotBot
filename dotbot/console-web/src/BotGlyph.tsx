import React from "react";

// The map marker, traced from the DotBot v3 board outline: one PCB, wide at the
// front and narrower between the wheels, with the tyres outboard of the narrow
// section. Geometry is authored in a 32-unit box centred on the bot with -y
// along its heading, so one unit is size/32 px and every number below scales
// with the size prop.
export const BOT_GLYPH_BOX = 48;

// What the robot itself spans inside that box - 25 of the 32 units - for
// callers matching the glyph to a real-world footprint.
export const BOT_GLYPH_SPAN = (BOT_GLYPH_BOX * 25) / 32;

const BOARD =
  "M-10.7,-11.9 L10.7,-11.9 Q12,-11.9 12,-10.6 L12,-2.4 Q12,-1.1 10.7,-1.1 " +
  "L6.9,-1.1 L6.9,10.6 Q6.9,11.9 5.6,11.9 L-5.6,11.9 Q-6.9,11.9 -6.9,10.6 " +
  "L-6.9,-1.1 L-10.7,-1.1 Q-12,-1.1 -12,-2.4 L-12,-10.6 Q-12,-11.9 -10.7,-11.9 Z";

const TREAD_Y = [2.2, 5.3, 8.4];

interface BotGlyphProps {
  color: string;
  heading: number | null; // degrees, 0 = north (+y), positive counterclockwise
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
      // CSS rotates clockwise in screen coords, so the angle is negated.
      transform: heading === null ? undefined : `rotate(${-heading}deg)`,
    }}
  >
    {heading === null ? (
      // Drawing the outline unrotated would assert a north the bot never
      // reported, so a headingless bot gets a body with no front.
      <circle r="8.5" fill={color} />
    ) : (
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
    )}
  </svg>
);
