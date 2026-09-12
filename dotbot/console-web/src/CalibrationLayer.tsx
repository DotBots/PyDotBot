import React from "react";

import { BOT_GLYPH_BOX, BotGlyph } from "./BotGlyph";
import { noseHeading, sessionRect } from "./calibration";
import { areaToFraction } from "./frame";
import type { Area, CalibrationSession } from "./types";

// Calibration mode drawn over the map: the rectangle the session's points
// span, its corners numbered in capture order, the captured ones ticked and
// the current one carrying a robot glyph whose nose shows the placement.
//
// Press order is point order, so no corner name and no robot identity is
// ever typed; the numbers are the whole correspondence.

const pctOf = (x: number, y: number, box: Area) => {
  const { fx, fy } = areaToFraction({ x, y }, box);
  return { left: `${fx * 100}%`, top: `${fy * 100}%` };
};

// The numbers are chrome, not objects on the floor, so they keep their size
// whatever the map's real-scale layer does to the robot glyphs.
const Marker: React.FC<{
  index: number;
  captured: boolean;
  current: boolean;
  nose: string;
}> = ({ index, captured, current, nose }) => (
  <div
    style={{
      position: "absolute",
      left: "50%",
      top: "50%",
      transform: "translate(-50%, -50%)",
      pointerEvents: "none",
    }}
  >
    {/* The badge is what sits on the point; the glyph stands above it, so
        numbering the corner does not move the mark it names. */}
    {current && (
      <div
        style={{
          position: "absolute",
          left: "50%",
          bottom: "100%",
          transform: "translateX(-50%)",
          marginBottom: 2,
          opacity: 0.9,
        }}
      >
        <BotGlyph color="var(--accent)" heading={noseHeading(nose)} size={BOT_GLYPH_BOX * 0.7} />
      </div>
    )}
    <div
      style={{
        font: "700 11px/1 var(--font-mono)",
        padding: "3px 7px",
        borderRadius: 9,
        whiteSpace: "nowrap",
        border: `1px solid ${current ? "var(--accent)" : "var(--hairline)"}`,
        background: current ? "var(--accent)" : "var(--surface)",
        color: current ? "#fff" : captured ? "var(--s-Running)" : "var(--muted)",
      }}
    >
      {captured ? "✓" : index}
    </div>
  </div>
);

interface CalibrationLayerProps {
  session: CalibrationSession;
  /** The part of the frame the map draws, so the rectangle lands on it. */
  viewport: Area;
}

export const CalibrationLayer: React.FC<CalibrationLayerProps> = ({
  session,
  viewport,
}) => {
  const rect = sessionRect(session);
  if (!rect) return null;
  const topLeft = areaToFraction({ x: rect.x, y: rect.y }, viewport);
  const bottomRight = areaToFraction(
    { x: rect.x + rect.w, y: rect.y + rect.h },
    viewport,
  );

  return (
    <>
      <div
        style={{
          position: "absolute",
          left: `${topLeft.fx * 100}%`,
          top: `${topLeft.fy * 100}%`,
          width: `${(bottomRight.fx - topLeft.fx) * 100}%`,
          height: `${(bottomRight.fy - topLeft.fy) * 100}%`,
          border: "1.5px solid var(--accent)",
          background: "rgba(228,3,46,.05)",
          borderRadius: 4,
          pointerEvents: "none",
          zIndex: 4,
        }}
      >
        <span
          style={{
            position: "absolute",
            right: 0,
            bottom: "100%",
            marginBottom: 4,
            fontSize: 10,
            color: "var(--accent)",
            whiteSpace: "nowrap",
          }}
        >
          calibrating {session.at}
        </span>
      </div>
      {session.points.map((p) => (
        <div
          key={p.index}
          style={{
            position: "absolute",
            ...pctOf(p.x, p.y, viewport),
            width: 0,
            height: 0,
            zIndex: 5,
          }}
        >
          <Marker
            index={p.index}
            captured={p.captured}
            current={session.outstanding === p.index}
            nose={p.nose}
          />
        </div>
      ))}
    </>
  );
};

/**
 * The rectangle as a thumbnail, for the phone card. Not navigation: it
 * answers which corner is next, from a crouch.
 */
export const RectThumb: React.FC<{ session: CalibrationSession; size?: number }> = ({
  session,
  size = 120,
}) => {
  const rect = sessionRect(session);
  if (!rect || rect.w === 0 || rect.h === 0) return null;
  const pad = 0.12;
  const box: Area = {
    x: rect.x - rect.w * pad,
    y: rect.y - rect.h * pad,
    w: rect.w * (1 + 2 * pad),
    h: rect.h * (1 + 2 * pad),
  };
  return (
    <div
      style={{
        position: "relative",
        width: "100%",
        maxWidth: size,
        aspectRatio: `${rect.w} / ${rect.h}`,
        border: "1px solid var(--hairline)",
        borderRadius: 6,
        background: "var(--canvas)",
        alignSelf: "center",
        flex: "none",
      }}
    >
      <div
        style={{
          position: "absolute",
          left: `${pad / (1 + 2 * pad) * 100}%`,
          top: `${pad / (1 + 2 * pad) * 100}%`,
          right: `${pad / (1 + 2 * pad) * 100}%`,
          bottom: `${pad / (1 + 2 * pad) * 100}%`,
          border: "1px solid var(--accent)",
          borderRadius: 3,
        }}
      />
      {session.points.map((p) => (
        <div
          key={p.index}
          style={{
            position: "absolute",
            ...pctOf(p.x, p.y, box),
            width: 20,
            height: 20,
            margin: "-10px 0 0 -10px",
            borderRadius: "50%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            font: "700 10px/1 var(--font-mono)",
            border: `1px solid ${
              session.outstanding === p.index ? "var(--accent)" : "var(--hairline)"
            }`,
            background:
              session.outstanding === p.index ? "var(--accent)" : "var(--surface)",
            color:
              session.outstanding === p.index
                ? "#fff"
                : p.captured
                  ? "var(--s-Running)"
                  : "var(--muted)",
          }}
        >
          {p.captured ? "✓" : p.index}
        </div>
      ))}
    </div>
  );
};
