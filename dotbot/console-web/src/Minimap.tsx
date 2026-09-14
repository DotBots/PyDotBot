import React, { useEffect, useRef, useState } from "react";

import { areaColor } from "./areaColor";
import { areaToFraction, siteExtentArea } from "./frame";
import { MINIMAP_TARGET_PX, gridStepMm } from "./grid";
import { minimapLabel } from "./localization";
import { stateColor } from "./viewChrome";

import { Camera, clampCam, ViewGeom } from "./MapView";
import { Area, Site, UnifiedBot } from "./types";

interface MinimapProps {
  bots: UnifiedBot[];
  /** The part of the frame the map draws, which the box tracks. */
  viewport: Area;
  site: Site | null;
  /** The area names this browser hides, ticked under Layers > Areas. */
  hiddenAreas: Set<string>;
  selection: Set<string>;
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
  hiddenAreas,
  selection,
  cam,
  setCam,
  geom,
}) => {
  const boxRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);
  // The panel is a fixed width but its height follows the site's aspect, so
  // the grid step is picked from what the box actually measures.
  const [boxPx, setBoxPx] = useState({ w: 190, h: 190 });
  useEffect(() => {
    const el = boxRef.current;
    if (!el) return;
    const update = () => {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.height > 0) setBoxPx({ w: r.width, h: r.height });
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const viewportRect = () => {
    if (!geom) return null;
    const { w, h, boxW, boxH } = geom;
    const span = (extent: number, drawn: number, t: number) => {
      const min = 0.5 - (extent / 2 + t) / (drawn * cam.scale);
      const max = 0.5 + (extent / 2 - t) / (drawn * cam.scale);
      return [Math.max(0, min), Math.min(1, max)];
    };
    const [x0, x1] = span(w, boxW, cam.tx);
    const [y0, y1] = span(h, boxH, cam.ty);
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
        {
          ...c,
          tx: -(fx - 0.5) * geom.boxW * c.scale,
          ty: -(fy - 0.5) * geom.boxH * c.scale,
        },
        geom,
      ),
    );
  };

  const rect = viewportRect();
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
  // The same metric grid the map draws, at the minimap's own scale: lines on
  // whole metric steps of the frame, anchored at the site's zero.
  const stepMm = gridStepMm(
    Math.min(boxPx.w / box.w, boxPx.h / box.h),
    MINIMAP_TARGET_PX,
  );
  const grid = {
    backgroundImage:
      "linear-gradient(90deg, var(--grid) 0 1px, transparent 1px 100%)," +
      "linear-gradient(180deg, var(--grid) 0 1px, transparent 1px 100%)",
    backgroundSize: `${(stepMm / box.w) * boxPx.w}px 100%, 100% ${(stepMm / box.h) * boxPx.h}px`,
    backgroundPosition: `${((0 - box.x) / box.w) * boxPx.w}px 0, 0 ${((0 - box.y) / box.h) * boxPx.h}px`,
  } as const;
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
        <div
          style={{
            textTransform: "uppercase",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
          title={minimapLabel(site)}
        >
          {minimapLabel(site)}
        </div>
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
            ...grid,
            border: "1px solid var(--muted)",
            overflow: "hidden",
            cursor: "grab",
            touchAction: "none",
        // Drag surface: a pan or marquee would otherwise smear a text
        // selection across the UI and race the browser's native drag.
        userSelect: "none",
          }}
        >
          {(site?.areas ?? [])
            .filter((a) => !hiddenAreas.has(a.name ?? ""))
            .map((a) => (
              <div
                key={`mini-${a.name}`}
                style={{
                  position: "absolute",
                  ...areaBox(a),
                  border: `1px dashed ${areaColor(a.name ?? "", (site?.areas ?? []).map((o) => o.name))}`,
                  opacity: 0.85,
                  pointerEvents: "none",
                }}
              />
            ))}
          {bots
            .filter((b) => b.position)
            .map((b) => {
              // A dot at minimap scale, where the site is a couple of hundred
              // pixels across: a glow would merge neighbours into a blob. The
              // selected one is ringed rather than grown, so the fleet keeps
              // its spacing.
              const selected = selection.has(b.id);
              return (
                <div
                  key={b.id}
                  style={{
                    position: "absolute",
                    left: `${areaToFraction(b.position!, box).fx * 100}%`,
                    top: `${areaToFraction(b.position!, box).fy * 100}%`,
                    width: 3,
                    height: 3,
                    borderRadius: "50%",
                    transform: "translate(-50%, -50%)",
                    background: stateColor(b.state),
                    boxShadow: selected ? "0 0 0 1.5px var(--accent)" : undefined,
                    zIndex: selected ? 2 : 1,
                  }}
                />
              );
            })}
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
