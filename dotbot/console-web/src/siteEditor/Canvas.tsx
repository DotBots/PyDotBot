import React, { useEffect, useRef, useState } from "react";

import { areaColor } from "../areaColor";
import { AREA_FALLBACK, siteViewMarginMm, withMargin } from "../frame";
import {
  axisTicks,
  canvasPx,
  frameMm,
  gridStepMm,
  gridSubStepMm,
  metreLabel,
  pxPerMm,
  rulerStepMm,
  ticksInSite,
} from "../grid";
import type { Area } from "../types";
import { FRAME_CAMERA, viewGeom } from "../zoom";
import { HANDLES, effectiveRole, moveRect, rectFromDrag, resizeRect } from "./edit";
import type { Handle, Rect } from "./edit";
import type { EditArea } from "./types";

// The site drawn to scale: the extent, the metric grid and its rulers, and
// every area in its role colour. Areas are moved, resized and drawn here; the
// numbers themselves live in the inspector.

export type Tool = "select" | "area";

const HANDLE_PX = 9;
const AREA_TINT = 0.12;

type Drag =
  | { kind: "move"; index: number; start: Rect; from: { x: number; y: number } }
  | { kind: "resize"; index: number; start: Rect; handle: Handle }
  | { kind: "draw"; from: { x: number; y: number }; to: { x: number; y: number } };

export interface CanvasProps {
  extent: [number, number] | null;
  areas: EditArea[];
  hidden: Set<string>;
  selected: number | null;
  tool: Tool;
  snapMm: number;
  onSelect: (index: number | null) => void;
  onChange: (index: number, rect: Rect) => void;
  onDraw: (rect: Rect) => void;
}

function handlePoint(r: Rect, h: Handle): { x: number; y: number } {
  const x = h.includes("w") ? r.x : h.includes("e") ? r.x + r.w : r.x + r.w / 2;
  const y = h.includes("n") ? r.y : h.includes("s") ? r.y + r.h : r.y + r.h / 2;
  return { x, y };
}

const CURSOR: Record<Handle, string> = {
  n: "ns-resize",
  s: "ns-resize",
  e: "ew-resize",
  w: "ew-resize",
  ne: "nesw-resize",
  sw: "nesw-resize",
  nw: "nwse-resize",
  se: "nwse-resize",
};

export function Canvas(props: CanvasProps) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 800, h: 600 });
  const [drag, setDrag] = useState<Drag | null>(null);
  const [altHeld, setAltHeld] = useState(false);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const measure = () => {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.height > 0) setSize({ w: r.width, h: r.height });
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const extentArea: Area = props.extent
    ? { x: 0, y: 0, w: props.extent[0], h: props.extent[1] }
    : AREA_FALLBACK;
  const viewport = withMargin(extentArea, siteViewMarginMm(extentArea));
  const geom = viewGeom(size.w, size.h, viewport);
  const cam = FRAME_CAMERA;
  const px = (axis: "x" | "y", mm: number) => canvasPx(axis, mm, viewport, geom, cam);
  const mm = (axis: "x" | "y", p: number) => frameMm(axis, p, viewport, geom, cam);
  const scale = pxPerMm("x", viewport, geom, cam);
  const rectPx = (r: Rect) => ({
    x: px("x", r.x),
    y: px("y", r.y),
    width: r.w * scale,
    height: r.h * scale,
  });

  const step = gridStepMm(scale);
  const sub = gridSubStepMm(scale);
  const ruler = rulerStepMm(step, scale);
  const extentForTicks = props.extent ? extentArea : null;
  const xs = axisTicks("x", viewport, geom, cam, step);
  const ys = axisTicks("y", viewport, geom, cam, step);
  const subXs = sub ? axisTicks("x", viewport, geom, cam, sub) : [];
  const subYs = sub ? axisTicks("y", viewport, geom, cam, sub) : [];
  const labelXs = ticksInSite(axisTicks("x", viewport, geom, cam, ruler), "x", extentForTicks);
  const labelYs = ticksInSite(axisTicks("y", viewport, geom, cam, ruler), "y", extentForTicks);

  const colourAreas: Area[] = props.areas.map((a) => ({ ...a, role: effectiveRole(a) }));
  const snapNow = (e: { altKey: boolean }) => (e.altKey ? 1 : props.snapMm);

  const toFrame = (e: React.PointerEvent) => {
    const r = wrapRef.current!.getBoundingClientRect();
    return { x: mm("x", e.clientX - r.left), y: mm("y", e.clientY - r.top) };
  };

  const begin = (e: React.PointerEvent, next: Drag) => {
    e.stopPropagation();
    wrapRef.current?.setPointerCapture?.(e.pointerId);
    setDrag(next);
  };

  const onBackgroundDown = (e: React.PointerEvent) => {
    if (e.button !== 0) return;
    if (props.tool === "area") {
      const p = toFrame(e);
      begin(e, { kind: "draw", from: p, to: p });
    } else {
      props.onSelect(null);
    }
  };

  const onAreaDown = (e: React.PointerEvent, index: number) => {
    if (e.button !== 0 || props.tool === "area") return;
    const a = props.areas[index];
    props.onSelect(index);
    begin(e, { kind: "move", index, start: { x: a.x, y: a.y, w: a.w, h: a.h }, from: toFrame(e) });
  };

  const onHandleDown = (e: React.PointerEvent, index: number, handle: Handle) => {
    if (e.button !== 0) return;
    const a = props.areas[index];
    begin(e, { kind: "resize", index, start: { x: a.x, y: a.y, w: a.w, h: a.h }, handle });
  };

  const onMove = (e: React.PointerEvent) => {
    setAltHeld(e.altKey);
    if (!drag) return;
    const p = toFrame(e);
    const s = snapNow(e);
    if (drag.kind === "move") {
      props.onChange(drag.index, moveRect(drag.start, p.x - drag.from.x, p.y - drag.from.y, s));
    } else if (drag.kind === "resize") {
      props.onChange(drag.index, resizeRect(drag.start, drag.handle, p, s));
    } else {
      setDrag({ ...drag, to: p });
    }
  };

  const onUp = (e: React.PointerEvent) => {
    if (drag?.kind === "draw") {
      const r = rectFromDrag(drag.from, toFrame(e), snapNow(e));
      if (r) props.onDraw(r);
    }
    setDrag(null);
  };

  // Largest first, so a small area inside a large one stays on top to grab.
  const order = props.areas
    .map((a, i) => i)
    .filter((i) => !props.hidden.has(props.areas[i].name) || i === props.selected)
    .sort((i, j) => props.areas[j].w * props.areas[j].h - props.areas[i].w * props.areas[i].h);
  const sel = props.selected !== null ? props.areas[props.selected] : null;
  const preview = drag?.kind === "draw" ? rectFromDrag(drag.from, drag.to, props.snapMm) : null;
  const extentPx = rectPx(extentArea);

  return (
    <div
      ref={wrapRef}
      data-testid="site-canvas"
      onPointerDown={onBackgroundDown}
      onPointerMove={onMove}
      onPointerUp={onUp}
      onPointerCancel={() => setDrag(null)}
      style={{
        position: "relative",
        flex: 1,
        minWidth: 0,
        minHeight: 0,
        overflow: "hidden",
        background: "var(--canvas)",
        cursor: props.tool === "area" ? "crosshair" : "default",
        touchAction: "none",
        userSelect: "none",
      }}
    >
      <svg width={size.w} height={size.h} style={{ display: "block" }}>
        <rect {...extentPx} fill="var(--surface)" />
        <g stroke="var(--grid-sub)" strokeWidth={1}>
          {subXs.map((t) => (
            <line key={`sx${t.mm}`} x1={t.px} x2={t.px} y1={0} y2={size.h} />
          ))}
          {subYs.map((t) => (
            <line key={`sy${t.mm}`} y1={t.px} y2={t.px} x1={0} x2={size.w} />
          ))}
        </g>
        <g stroke="var(--grid)" strokeWidth={1}>
          {xs.map((t) => (
            <line key={`x${t.mm}`} x1={t.px} x2={t.px} y1={0} y2={size.h} />
          ))}
          {ys.map((t) => (
            <line key={`y${t.mm}`} y1={t.px} y2={t.px} x1={0} x2={size.w} />
          ))}
        </g>
        <rect
          {...extentPx}
          fill="none"
          stroke="var(--muted)"
          strokeWidth={1.5}
          data-testid="site-extent"
        />
        <g fontFamily="var(--font-mono)" fontSize={10} fill="var(--muted)">
          {labelXs.map((t) => (
            <text key={`lx${t.mm}`} x={t.px} y={extentPx.y - 6} textAnchor="middle">
              {metreLabel(t.mm, ruler)}
            </text>
          ))}
          {labelYs.map((t) => (
            <text key={`ly${t.mm}`} x={extentPx.x - 6} y={t.px + 3} textAnchor="end">
              {metreLabel(t.mm, ruler)}
            </text>
          ))}
        </g>
        {order.map((i) => {
          const a = props.areas[i];
          const colour = areaColor(colourAreas[i], colourAreas);
          const role = effectiveRole(a);
          const composite = a.name.includes("+");
          const r = rectPx(a);
          return (
            <g key={`${i}-${a.was ?? ""}`}>
              <rect
                data-testid={`edit-area-${a.name}`}
                {...r}
                fill={colour}
                fillOpacity={composite ? 0.03 : AREA_TINT}
                stroke={colour}
                strokeWidth={i === props.selected ? 2.5 : role === "corner" ? 2 : 1.5}
                strokeDasharray={composite ? "7 5" : role === "corner" ? "3 3" : undefined}
                style={{ cursor: props.tool === "select" ? "move" : "crosshair" }}
                onPointerDown={(e) => onAreaDown(e, i)}
              >
                <title>{a.name}</title>
              </rect>
              {r.width > 40 && r.height > 18 && (
                <text
                  x={composite ? r.x + r.width - 6 : r.x + 6}
                  y={composite ? r.y + r.height - 6 : r.y + 14}
                  textAnchor={composite ? "end" : "start"}
                  fontSize={11}
                  fontFamily="var(--font-ui)"
                  fill={colour}
                  style={{ pointerEvents: "none" }}
                >
                  {a.name}
                </text>
              )}
            </g>
          );
        })}
        {sel && props.selected !== null && props.tool === "select" && (
          <g data-testid="selection">
            <text
              x={rectPx(sel).x + rectPx(sel).width / 2}
              y={rectPx(sel).y + rectPx(sel).height + 16}
              textAnchor="middle"
              fontSize={11}
              fontFamily="var(--font-mono)"
              fill="var(--text)"
              style={{ pointerEvents: "none" }}
            >
              {`${sel.w} x ${sel.h} mm at (${sel.x}, ${sel.y})`}
            </text>
            {HANDLES.map((h) => {
              const p = handlePoint(sel, h);
              return (
                <rect
                  key={h}
                  data-testid={`handle-${h}`}
                  x={px("x", p.x) - HANDLE_PX / 2}
                  y={px("y", p.y) - HANDLE_PX / 2}
                  width={HANDLE_PX}
                  height={HANDLE_PX}
                  fill="var(--surface)"
                  stroke="var(--text)"
                  strokeWidth={1.2}
                  style={{ cursor: CURSOR[h] }}
                  onPointerDown={(e) => onHandleDown(e, props.selected!, h)}
                />
              );
            })}
          </g>
        )}
        {preview && (
          <rect
            data-testid="draw-preview"
            {...rectPx(preview)}
            fill="var(--accent)"
            fillOpacity={0.08}
            stroke="var(--accent)"
            strokeDasharray="4 3"
          />
        )}
        <g data-testid="anchor">
          <circle cx={px("x", 0)} cy={px("y", 0)} r={5} fill="var(--accent)" />
          <text
            x={px("x", 0) - 10}
            y={px("y", 0) - 16}
            textAnchor="end"
            fontSize={10}
            fontFamily="var(--font-mono)"
            fill="var(--accent)"
          >
            anchor (0, 0)
          </text>
        </g>
      </svg>
      <div
        style={{
          position: "absolute",
          right: 10,
          bottom: 8,
          fontSize: 11,
          color: "var(--muted)",
          fontFamily: "var(--font-mono)",
          pointerEvents: "none",
        }}
      >
        {altHeld ? "free placement (Alt)" : `snap ${props.snapMm} mm, Alt for free`}
      </div>
    </div>
  );
}
