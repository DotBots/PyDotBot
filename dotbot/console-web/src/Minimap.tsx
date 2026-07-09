import React, { useRef } from "react";

import { Camera } from "./MapView";
import { MapSize, UnifiedBot } from "./types";

export interface ViewGeom {
  w: number;
  h: number;
  side: number;
}

interface MinimapProps {
  bots: UnifiedBot[];
  mapSize: MapSize;
  cam: Camera;
  setCam: React.Dispatch<React.SetStateAction<Camera>>;
  geom: ViewGeom | null;
}

// Whole-arena overview with the current map viewport as a rectangle.
// Dragging moves the camera (the design pans exclusively through here).
export const Minimap: React.FC<MinimapProps> = ({ bots, mapSize, cam, setCam, geom }) => {
  const boxRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

  // Fraction of the arena visible in the map wrapper, derived from the camera:
  // wrapper coords of arena-fraction f: w/2 + (f - 0.5) * side * scale + tx.
  const viewportRect = () => {
    if (!geom) return null;
    const { w, h, side } = geom;
    const span = (extent: number, t: number) => {
      const min = 0.5 - (extent / 2 + t) / (side * cam.scale);
      const max = 0.5 + (extent / 2 - t) / (side * cam.scale);
      return [Math.max(0, min), Math.min(1, max)];
    };
    const [x0, x1] = span(w, cam.tx);
    const [y0, y1] = span(h, cam.ty);
    return { x0, x1, y0, y1 };
  };

  const centerOn = (clientX: number, clientY: number) => {
    const el = boxRef.current;
    if (!el || !geom) return;
    const r = el.getBoundingClientRect();
    const fx = Math.max(0, Math.min(1, (clientX - r.left) / r.width));
    const fy = Math.max(0, Math.min(1, (clientY - r.top) / r.height));
    setCam((c) => ({
      ...c,
      tx: -(fx - 0.5) * geom.side * c.scale,
      ty: -(fy - 0.5) * geom.side * c.scale,
    }));
  };

  const rect = viewportRect();

  return (
    <div
      style={{
        width: 196,
        flex: "none",
        background: "var(--surface)",
        padding: 12,
        display: "flex",
        flexDirection: "column",
        gap: 6,
      }}
    >
      <div
        style={{
          fontSize: 10,
          letterSpacing: ".6px",
          textTransform: "uppercase",
          color: "var(--muted)",
        }}
      >
        Arena &middot; {mapSize.width}&times;{mapSize.height}mm
      </div>
      <div
        ref={boxRef}
        title="Drag to move the map view"
        onPointerDown={(e) => {
          dragging.current = true;
          (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
          centerOn(e.clientX, e.clientY);
        }}
        onPointerMove={(e) => dragging.current && centerOn(e.clientX, e.clientY)}
        onPointerUp={() => (dragging.current = false)}
        style={{
          position: "relative",
          flex: 1,
          background: "var(--canvas)",
          border: "1px solid var(--hairline)",
          borderRadius: 5,
          overflow: "hidden",
          cursor: "grab",
          touchAction: "none",
        }}
      >
        {bots
          .filter((b) => b.position)
          .map((b) => (
            <div
              key={b.id}
              style={{
                position: "absolute",
                left: `${(b.position!.x / mapSize.width) * 100}%`,
                top: `${(b.position!.y / mapSize.height) * 100}%`,
                width: 4,
                height: 4,
                marginLeft: -2,
                marginTop: -2,
                borderRadius: "50%",
                background: b.led
                  ? `rgb(${b.led.red},${b.led.green},${b.led.blue})`
                  : `var(--s-${b.state})`,
                opacity: b.state === "Inactive" ? 0.4 : 1,
              }}
            />
          ))}
        {rect && (
          <div
            style={{
              position: "absolute",
              left: `${rect.x0 * 100}%`,
              top: `${rect.y0 * 100}%`,
              width: `${(rect.x1 - rect.x0) * 100}%`,
              height: `${(rect.y1 - rect.y0) * 100}%`,
              border: "1px solid var(--accent)",
              background: "rgba(228,3,46,.06)",
              pointerEvents: "none",
            }}
          />
        )}
      </div>
    </div>
  );
};
