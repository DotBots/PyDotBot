import React from "react";

import { candidates } from "./stationRule";
import type { Rect } from "./types";

const CELLS = 16;

/** A small map of who gives the fix, by the robots' rule, over `extent`:
 * each station's hue where its box decides, grey where the boxes do not. */
export const FixThumb: React.FC<{ boxes: Record<number, Rect>; extent: [number, number]; size?: number }> = ({
  boxes,
  extent,
  size = 40,
}) => {
  const [w, h] = extent;
  const scale = size / Math.max(w, h, 1);
  const cw = w / CELLS;
  const ch = h / CELLS;
  const cells: React.ReactNode[] = [];
  for (let i = 0; i < CELLS; i++) {
    for (let j = 0; j < CELLS; j++) {
      const who = candidates(boxes, (j + 0.5) * cw, (i + 0.5) * ch);
      if (who.length === 0) continue;
      const fill = who.length === 1 ? `var(--st-${who[0] % 2})` : "var(--muted)";
      cells.push(
        <rect
          key={`${i}-${j}`}
          x={j * cw * scale}
          y={i * ch * scale}
          width={cw * scale + 0.3}
          height={ch * scale + 0.3}
          fill={fill}
          fillOpacity={who.length === 1 ? 0.55 : 0.35}
        />,
      );
    }
  }
  return (
    <svg
      data-testid="fix-thumb"
      width={w * scale}
      height={h * scale}
      style={{ flex: "none", borderRadius: 3, outline: "1px solid var(--hairline)", background: "var(--canvas)" }}
      aria-hidden
    >
      {cells}
    </svg>
  );
};
