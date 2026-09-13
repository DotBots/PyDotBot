import React, { useRef } from "react";

import { areaToFraction, siteExtentArea } from "./frame";
import { minimapLines } from "./localization";
import { stateColor } from "./viewChrome";

import { Camera, clampCam, ViewGeom } from "./MapView";
import { Area, Site, UnifiedBot } from "./types";

interface MinimapProps {
  bots: UnifiedBot[];
  /** The part of the frame the map draws, which the box tracks. */
  viewport: Area;
  site: Site | null;
  activeAreas: Area[];
  cam: Camera;
  setCam: React.Dispatch<React.SetStateAction<Camera>>;
  geom: ViewGeom | null;
}

// The whole site, with every area as a faint outline and the current map
// viewport as a box. It says where the operator is rather than following
// them, so it does not zoom with the viewport; dragging moves the camera.
export const Minimap: React.FC<MinimapProps> = ({
  bots,
  viewport,
  site,
  activeAreas,
  cam,
  setCam,
  geom,
}) => {
  const boxRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

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
    setCam((c) =>
      clampCam(
        { ...c, tx: -(fx - 0.5) * geom.side * c.scale, ty: -(fy - 0.5) * geom.side * c.scale },
        geom,
      ),
    );
  };

  const rect = viewportRect();
  const shown = new Set(activeAreas.map((a) => a.name ?? "").filter(Boolean));
  // The whole site, never the viewport: the box below is what moves.
  const box: Area = siteExtentArea(site) ?? viewport;
  // viewportRect speaks fractions of the drawn viewport; the minimap draws
  // the site, so the box has to be re-expressed against it.
  const onBox = (fraction: number, axis: "x" | "y") => {
    const frame =
      axis === "x"
        ? viewport.x + fraction * viewport.w
        : viewport.y + fraction * viewport.h;
    return axis === "x" ? (frame - box.x) / box.w : (frame - box.y) / box.h;
  };
  const areaBox = (a: Area) => {
    const tl = areaToFraction({ x: a.x, y: a.y }, box);
    const br = areaToFraction({ x: a.x + a.w, y: a.y + a.h }, box);
    return {
      left: `${tl.fx * 100}%`,
      top: `${tl.fy * 100}%`,
      width: `${(br.fx - tl.fx) * 100}%`,
      height: `${(br.fy - tl.fy) * 100}%`,
    };
  };

  return (
    <div
      style={{
        width: 214,
        flex: "none",
        background: "var(--surface)",
        padding: 12,
        display: "flex",
        flexDirection: "column",
        gap: 6,
      }}
    >
      <div style={{ fontSize: 9.5, lineHeight: 1.4, letterSpacing: ".4px", color: "var(--muted)" }}>
        {minimapLines(site, activeAreas).map((line, i) => (
          <div
            key={i}
            style={{
              textTransform: "uppercase",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
            title={line}
          >
            {line}
          </div>
        ))}
      </div>
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", minHeight: 0 }}>
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
            aspectRatio: `${box.w} / ${box.h}`,
            height: "100%",
            maxWidth: "100%",
            background: "var(--canvas)",
            border: "1px solid var(--hairline)",
            borderRadius: 5,
            overflow: "hidden",
            cursor: "grab",
            touchAction: "none",
        // Drag surface: a pan or marquee would otherwise smear a text
        // selection across the UI and race the browser's native drag.
        userSelect: "none",
          }}
        >
          {(site?.areas ?? []).map((a) => (
            <div
              key={`mini-${a.name}`}
              style={{
                position: "absolute",
                ...areaBox(a),
                border: `1px ${shown.has(a.name ?? "") ? "solid" : "dashed"} var(--hairline)`,
                background: shown.has(a.name ?? "") ? "rgba(228,3,46,.05)" : "transparent",
                pointerEvents: "none",
              }}
            />
          ))}
          {bots
            .filter((b) => b.position)
            .map((b) => (
              <div
                key={b.id}
                style={{
                  position: "absolute",
                  left: `${areaToFraction(b.position!, box).fx * 100}%`,
                  top: `${areaToFraction(b.position!, box).fy * 100}%`,
                  width: 5,
                  height: 5,
                  borderRadius: "50%",
                  transform: "translate(-50%, -50%)",
                  background: stateColor(b.state),
                  boxShadow: `0 0 4px ${stateColor(b.state)}`,
                }}
              />
            ))}
          {rect && (
            <div
              style={{
                position: "absolute",
                left: `${onBox(rect.x0, "x") * 100}%`,
                top: `${onBox(rect.y0, "y") * 100}%`,
                width: `${(onBox(rect.x1, "x") - onBox(rect.x0, "x")) * 100}%`,
                height: `${(onBox(rect.y1, "y") - onBox(rect.y0, "y")) * 100}%`,
                border: "1px solid var(--accent)",
                background: "rgba(228,3,46,.06)",
                pointerEvents: "none",
              }}
            />
          )}
        </div>
      </div>
    </div>
  );
};
