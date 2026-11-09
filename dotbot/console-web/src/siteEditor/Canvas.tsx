import React, { useEffect, useRef, useState } from "react";

import { areaColor } from "../areaColor";
import { convexHull } from "../calibrationSpan";
import { OBJECT_COLOUR, OBJECT_SIZE_MM, facing } from "../siteObjects";
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
import { BARRIER_MIN_POINTS, HANDLES, effectiveRole, finishPoints, movePoints, moveRect, rectFromDrag, resizeRect, snap } from "./edit";
import type { Handle, Rect } from "./edit";
import { applyMove, movedBox, movedCorners, snapAngle, turnAbout } from "./rigid";
import type { Point, Rigid2D } from "./rigid";
import type {
  BarrierKind,
  CalibrationBackdrop,
  CalibrationOverlay,
  CameraBackdrop,
  EditArea,
  EditBarrier,
  EditObject,
} from "./types";

// The site drawn to scale: the extent, the metric grid and its rulers, and
// every area in its role colour. Areas are moved, resized and drawn here; the
// numbers themselves live in the inspector.

export type Tool = "select" | "area" | "calibration" | "wall" | "obstacle" | "object";

/** A selected wall or obstacle. */
export interface BarrierRef {
  kind: BarrierKind;
  index: number;
}

const TOOL_KIND: Partial<Record<Tool, BarrierKind>> = { wall: "walls", obstacle: "obstacles" };

/** A calibration drawn over the site, and the move that places it. */
export interface Placement {
  overlay: CalibrationOverlay;
  move: Rigid2D;
}

// One colour per station, in station order
const STATION_COLOURS = ["var(--accent)", "var(--s-Running)", "var(--s-Programming)", "var(--s-Bootloader)"];
const ROTATE_HANDLE_PX = 28;

const HANDLE_PX = 9;
const AREA_TINT = 0.12;

const DRAG_THRESHOLD_PX = 3;

type Drag =
  | { kind: "move"; index: number; start: Rect; from: { x: number; y: number }; px: { x: number; y: number } }
  | { kind: "resize"; index: number; start: Rect; handle: Handle }
  | { kind: "draw"; from: { x: number; y: number }; to: { x: number; y: number } }
  | { kind: "place-move"; start: Rigid2D; from: { x: number; y: number } }
  | { kind: "barrier-move"; ref: BarrierRef; start: [number, number][]; from: { x: number; y: number } }
  | { kind: "barrier-vertex"; ref: BarrierRef; vertex: number }
  | { kind: "object-move"; index: number; start: { x: number; y: number }; from: { x: number; y: number } }
  | { kind: "place-turn"; start: Rigid2D; pivot: Point; angle: number };

export interface CanvasProps {
  extent: [number, number] | null;
  areas: EditArea[];
  hidden: Set<string>;
  selected: number | null;
  tool: Tool;
  snapMm: number;
  onSelect: (index: number | null) => void;
  /** `key` names the gesture, so one drag undoes as one step. */
  onChange: (index: number, rect: Rect, key: string) => void;
  onDraw: (rect: Rect) => void;
  placement?: Placement | null;
  onPlacement?: (move: Rigid2D) => void;
  walls?: EditBarrier[];
  obstacles?: EditBarrier[];
  selectedBarrier?: BarrierRef | null;
  onSelectBarrier?: (ref: BarrierRef | null) => void;
  /** `key` names the gesture, so one drag undoes as one step. */
  onBarrierChange?: (ref: BarrierRef, points: [number, number][], key: string) => void;
  onBarrierDraw?: (kind: BarrierKind, points: [number, number][]) => void;
  objects?: EditObject[];
  selectedObject?: number | null;
  onSelectObject?: (index: number | null) => void;
  onObjectChange?: (index: number, at: { x: number; y: number }, key: string) => void;
  onObjectPlace?: (at: { x: number; y: number }) => void;
  /** Read-only layers under the areas: only the ones switched on. */
  backdrops?: { calibrations: CalibrationBackdrop[]; cameras: CameraBackdrop[] };
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
  // A wall or obstacle being drawn, point by point, and where the pointer is
  const [draft, setDraft] = useState<{ kind: BarrierKind; points: [number, number][] } | null>(null);
  const [hover, setHover] = useState<[number, number] | null>(null);
  const draftKind = TOOL_KIND[props.tool] ?? null;

  useEffect(() => {
    if (!draftKind) setDraft(null);
  }, [draftKind]);

  const finishDraft = () => {
    if (!draft) return;
    const points = finishPoints(draft.points);
    if (points.length >= BARRIER_MIN_POINTS[draft.kind]) props.onBarrierDraw?.(draft.kind, points);
    setDraft(null);
  };

  useEffect(() => {
    if (!draft) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Enter") finishDraft();
      else if (e.key === "Escape") setDraft(null);
      else return;
      e.stopPropagation();
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  });

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

  const gesture = useRef(0);
  const begin = (e: React.PointerEvent, next: Drag) => {
    gesture.current += 1;
    e.stopPropagation();
    wrapRef.current?.setPointerCapture?.(e.pointerId);
    setDrag(next);
  };

  const onBackgroundDown = (e: React.PointerEvent) => {
    if (e.button !== 0) return;
    if (draftKind) {
      const p = toFrame(e);
      const s = snapNow(e);
      const point: [number, number] = [snap(p.x, s), snap(p.y, s)];
      setDraft((d) => (d && d.kind === draftKind ? { ...d, points: [...d.points, point] } : { kind: draftKind, points: [point] }));
      return;
    }
    if (props.tool === "object") {
      const p = toFrame(e);
      const s = snapNow(e);
      props.onObjectPlace?.({ x: snap(p.x, s), y: snap(p.y, s) });
      return;
    }
    if (props.tool === "area") {
      const p = toFrame(e);
      begin(e, { kind: "draw", from: p, to: p });
    } else {
      props.onSelect(null);
      props.onSelectBarrier?.(null);
      props.onSelectObject?.(null);
    }
  };

  const onObjectDown = (e: React.PointerEvent, index: number) => {
    if (e.button !== 0 || props.tool !== "select") return;
    const o = props.objects?.[index];
    if (!o) return;
    props.onSelectObject?.(index);
    begin(e, { kind: "object-move", index, start: { x: o.x, y: o.y }, from: toFrame(e) });
  };

  const onBarrierDown = (e: React.PointerEvent, ref: BarrierRef) => {
    if (e.button !== 0 || props.tool !== "select") return;
    const b = (ref.kind === "walls" ? props.walls : props.obstacles)?.[ref.index];
    if (!b) return;
    props.onSelectBarrier?.(ref);
    begin(e, { kind: "barrier-move", ref, start: b.points, from: toFrame(e) });
  };

  const onVertexDown = (e: React.PointerEvent, ref: BarrierRef, vertex: number) => {
    if (e.button !== 0) return;
    begin(e, { kind: "barrier-vertex", ref, vertex });
  };

  const onAreaDown = (e: React.PointerEvent, index: number) => {
    if (e.button !== 0 || props.tool !== "select") return;
    const a = props.areas[index];
    props.onSelect(index);
    begin(e, {
      kind: "move",
      index,
      start: { x: a.x, y: a.y, w: a.w, h: a.h },
      from: toFrame(e),
      px: { x: e.clientX, y: e.clientY },
    });
  };

  const onHandleDown = (e: React.PointerEvent, index: number, handle: Handle) => {
    if (e.button !== 0) return;
    const a = props.areas[index];
    begin(e, { kind: "resize", index, start: { x: a.x, y: a.y, w: a.w, h: a.h }, handle });
  };

  const placement = props.placement ?? null;
  const fence = placement ? placement.overlay.fence : null;
  const placedBox = placement && fence ? movedBox(placement.move, fence) : null;
  const placeCentre: Point | null = placedBox
    ? [(placedBox[0] + placedBox[2]) / 2, (placedBox[1] + placedBox[3]) / 2]
    : null;
  const angleTo = (c: Point, p: { x: number; y: number }) =>
    (Math.atan2(p.y - c[1], p.x - c[0]) * 180) / Math.PI;

  const onPlacementDown = (e: React.PointerEvent) => {
    if (e.button !== 0 || props.tool !== "calibration" || !placement) return;
    begin(e, { kind: "place-move", start: placement.move, from: toFrame(e) });
  };

  const onTurnDown = (e: React.PointerEvent) => {
    if (e.button !== 0 || !placement || !placeCentre) return;
    begin(e, { kind: "place-turn", start: placement.move, pivot: placeCentre, angle: angleTo(placeCentre, toFrame(e)) });
  };

  const onMove = (e: React.PointerEvent) => {
    setAltHeld(e.altKey);
    if (draft) {
      const p = toFrame(e);
      const s = snapNow(e);
      setHover([snap(p.x, s), snap(p.y, s)]);
    }
    if (!drag) return;
    const p = toFrame(e);
    const s = snapNow(e);
    if (drag.kind === "object-move") {
      props.onObjectChange?.(
        drag.index,
        { x: snap(drag.start.x + p.x - drag.from.x, s), y: snap(drag.start.y + p.y - drag.from.y, s) },
        `canvas-${gesture.current}`,
      );
    } else if (drag.kind === "barrier-move") {
      props.onBarrierChange?.(drag.ref, movePoints(drag.start, p.x - drag.from.x, p.y - drag.from.y, s), `canvas-${gesture.current}`);
    } else if (drag.kind === "barrier-vertex") {
      const b = (drag.ref.kind === "walls" ? props.walls : props.obstacles)?.[drag.ref.index];
      if (b) {
        const points = b.points.map((q, i): [number, number] => (i === drag.vertex ? [snap(p.x, s), snap(p.y, s)] : q));
        props.onBarrierChange?.(drag.ref, points, `canvas-${gesture.current}`);
      }
    } else if (drag.kind === "place-move") {
      const dx = snap(drag.start.dx_mm + p.x - drag.from.x, s);
      const dy = snap(drag.start.dy_mm + p.y - drag.from.y, s);
      props.onPlacement?.({ ...drag.start, dx_mm: dx, dy_mm: dy });
    } else if (drag.kind === "place-turn") {
      const total = snapAngle(drag.start.theta_deg + angleTo(drag.pivot, p) - drag.angle, e.altKey);
      const turned = turnAbout(drag.start, drag.pivot, total - drag.start.theta_deg);
      // The zero lands on the snap grid too, so the numbers stay round
      props.onPlacement?.({
        theta_deg: total,
        dx_mm: s > 1 ? snap(turned.dx_mm, s) : Math.round(turned.dx_mm * 10) / 10,
        dy_mm: s > 1 ? snap(turned.dy_mm, s) : Math.round(turned.dy_mm * 10) / 10,
      });
    } else if (drag.kind === "move") {
      // A click that selects is not a move, however the pointer jitters
      if (Math.hypot(e.clientX - drag.px.x, e.clientY - drag.px.y) < DRAG_THRESHOLD_PX) return;
      props.onChange(drag.index, moveRect(drag.start, p.x - drag.from.x, p.y - drag.from.y, s), `canvas-${gesture.current}`);
    } else if (drag.kind === "resize") {
      props.onChange(drag.index, resizeRect(drag.start, drag.handle, p, s), `canvas-${gesture.current}`);
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
      onDoubleClick={finishDraft}
      style={{
        position: "relative",
        flex: 1,
        minWidth: 0,
        minHeight: 0,
        overflow: "hidden",
        background: "var(--canvas)",
        cursor: props.tool === "area" || props.tool === "object" || draftKind ? "crosshair" : "default",
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
        {props.backdrops?.cameras.map((cam) =>
          cam.rect && cam.still ? (
            <image
              key={`cam-${cam.id8}`}
              data-testid={`backdrop-camera-${cam.id8}`}
              href={cam.still}
              {...rectPx({ x: cam.rect[0], y: cam.rect[1], w: cam.rect[2], h: cam.rect[3] })}
              preserveAspectRatio="none"
              opacity={0.7}
              style={{ pointerEvents: "none" }}
            />
          ) : null,
        )}
        {props.backdrops?.calibrations.map((cal) => {
          const outline = (pts: [number, number][]) =>
            convexHull(pts)
              .map(([x, y]) => `${px("x", x)},${px("y", y)}`)
              .join(" ");
          return (
            <g key={`cal-${cal.id8}`} data-testid={`backdrop-calibration-${cal.id8}`} style={{ pointerEvents: "none" }}>
              {cal.placements
                .filter((pts) => pts.length >= 3)
                .map((pts, k) => (
                  <polygon
                    key={k}
                    points={outline(pts)}
                    fill="var(--s-Programming)"
                    fillOpacity={0.06}
                    stroke="var(--s-Programming)"
                    strokeDasharray="2 3"
                  />
                ))}
              {cal.centres.length >= 3 && (
                <polygon points={outline(cal.centres)} fill="none" stroke="var(--s-Programming)" strokeDasharray="2 3" />
              )}
              {cal.centres.map(([x, y], k) => (
                <circle key={k} cx={px("x", x)} cy={px("y", y)} r={2.5} fill="var(--s-Programming)" />
              ))}
            </g>
          );
        })}
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
        {(["obstacles", "walls"] as BarrierKind[]).map((kind) =>
          ((kind === "walls" ? props.walls : props.obstacles) ?? []).map((b, i) => {
            const ref = { kind, index: i };
            const chosen = props.selectedBarrier?.kind === kind && props.selectedBarrier.index === i;
            const pts = b.points.map(([x, y]) => `${px("x", x)},${px("y", y)}`).join(" ");
            const common = {
              points: pts,
              stroke: chosen ? "var(--accent)" : "var(--text)",
              style: { cursor: props.tool === "select" ? "move" : undefined },
              onPointerDown: (e: React.PointerEvent) => onBarrierDown(e, ref),
            };
            return kind === "walls" ? (
              <polyline
                key={`w${i}`}
                data-testid={`edit-wall-${i}`}
                {...common}
                fill="none"
                strokeWidth={chosen ? 5 : 4}
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <title>{b.name || `wall ${i + 1}`}</title>
              </polyline>
            ) : (
              <polygon
                key={`o${i}`}
                data-testid={`edit-obstacle-${i}`}
                {...common}
                fill="var(--muted)"
                fillOpacity={0.35}
                strokeWidth={chosen ? 2.5 : 1.5}
              >
                <title>{b.name || `obstacle ${i + 1}`}</title>
              </polygon>
            );
          }),
        )}
        {props.selectedBarrier && props.tool === "select" &&
          ((props.selectedBarrier.kind === "walls" ? props.walls : props.obstacles) ?? [])[props.selectedBarrier.index]?.points.map(
            ([x, y], v) => (
              <rect
                key={`v${v}`}
                data-testid={`vertex-${v}`}
                x={px("x", x) - HANDLE_PX / 2}
                y={px("y", y) - HANDLE_PX / 2}
                width={HANDLE_PX}
                height={HANDLE_PX}
                fill="var(--surface)"
                stroke="var(--accent)"
                strokeWidth={1.2}
                style={{ cursor: "move" }}
                onPointerDown={(e) => onVertexDown(e, props.selectedBarrier!, v)}
              />
            ),
          )}
        {(props.objects ?? []).map((o, i) => {
          const r = Math.max(5, (OBJECT_SIZE_MM / 2) * scale);
          const [cx, cy] = [px("x", o.x), px("y", o.y)];
          const [dx, dy] = facing(o.heading_deg);
          const chosen = props.selectedObject === i;
          return (
            <g
              key={`obj-${i}`}
              data-testid={`edit-object-${o.name}`}
              style={{ cursor: props.tool === "select" ? "move" : undefined }}
              onPointerDown={(e) => onObjectDown(e, i)}
            >
              <rect
                x={cx - r}
                y={cy - r}
                width={2 * r}
                height={2 * r}
                rx={r / 3}
                fill={OBJECT_COLOUR[o.kind]}
                fillOpacity={0.25}
                stroke={chosen ? "var(--accent)" : OBJECT_COLOUR[o.kind]}
                strokeWidth={chosen ? 2.5 : 1.5}
              />
              <line x1={cx} y1={cy} x2={cx + dx * r} y2={cy + dy * r} stroke={OBJECT_COLOUR[o.kind]} strokeWidth={1.5} />
              <text
                x={cx + r + 4}
                y={cy + 4}
                fontSize={10}
                fontFamily="var(--font-mono)"
                fill={OBJECT_COLOUR[o.kind]}
                style={{ pointerEvents: "none" }}
              >
                {o.name}
              </text>
            </g>
          );
        })}
        {draft && (
          <g data-testid="barrier-draft" style={{ pointerEvents: "none" }}>
            <polyline
              points={[...draft.points, ...(hover ? [hover] : []), ...(draft.kind === "obstacles" && draft.points.length > 1 ? [draft.points[0]] : [])]
                .map(([x, y]) => `${px("x", x)},${px("y", y)}`)
                .join(" ")}
              fill="none"
              stroke="var(--accent)"
              strokeWidth={2}
              strokeDasharray="5 4"
            />
            {draft.points.map(([x, y], k) => (
              <circle key={k} cx={px("x", x)} cy={px("y", y)} r={3} fill="var(--accent)" />
            ))}
          </g>
        )}
        {placement && fence && placedBox && placeCentre && (
          <g data-testid="placement">
            {placement.overlay.stations.map((st, k) => {
              const colour = STATION_COLOURS[k % STATION_COLOURS.length];
              const corners = movedCorners(placement.move, st.rect)
                .map(([x, y]) => `${px("x", x)},${px("y", y)}`)
                .join(" ");
              return (
                <g key={st.index} data-testid={`placement-station-${st.index}`}>
                  <polygon points={corners} fill="none" stroke={colour} strokeWidth={1.5} strokeDasharray="6 4" />
                  {placement.overlay.stations.length > 1 && (
                    <text
                      x={px("x", movedBox(placement.move, st.rect)[0]) + 4}
                      y={px("y", movedBox(placement.move, st.rect)[3]) - 4 - 12 * k}
                      fontSize={10}
                      fontFamily="var(--font-mono)"
                      fill={colour}
                      style={{ pointerEvents: "none" }}
                    >
                      {`station ${st.index} (channel ${st.channel})`}
                    </text>
                  )}
                  {st.circles.map((c) => {
                    const [x, y] = applyMove(placement.move, [c.x, c.y]);
                    return (
                      <g key={c.name} data-testid={`placement-circle-${st.index}-${c.name}`}>
                        <circle
                          cx={px("x", x)}
                          cy={px("y", y)}
                          r={Math.max(2, c.radius_mm * scale)}
                          fill="none"
                          stroke={colour}
                          strokeWidth={1}
                        />
                        <circle cx={px("x", x)} cy={px("y", y)} r={2.5} fill={colour} />
                      </g>
                    );
                  })}
                </g>
              );
            })}
            {placement.overlay.links.map((link) => {
              const a = placement.overlay.stations.find((st) => st.index === link.a);
              const b = placement.overlay.stations.find((st) => st.index === link.b);
              if (!a || !b) return null;
              const centre = (rect: number[]) =>
                applyMove(placement.move, [(rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2]);
              const [ax, ay] = centre(a.rect);
              const [bx, by] = centre(b.rect);
              return (
                <line
                  key={`${link.a}-${link.b}`}
                  data-testid={`placement-link-${link.a}-${link.b}`}
                  x1={px("x", ax)}
                  y1={px("y", ay)}
                  x2={px("x", bx)}
                  y2={px("y", by)}
                  stroke={link.weak ? "var(--s-Stopping)" : "var(--muted)"}
                  strokeOpacity={0.5}
                  strokeDasharray={link.weak ? "2 3" : undefined}
                >
                  <title>{`${link.shared} shared circle${link.shared === 1 ? "" : "s"}${link.weak ? ", weak" : ""}`}</title>
                </line>
              );
            })}
            <polygon
              data-testid="placement-body"
              points={movedCorners(placement.move, fence)
                .map(([x, y]) => `${px("x", x)},${px("y", y)}`)
                .join(" ")}
              fill="var(--accent)"
              fillOpacity={props.tool === "calibration" ? 0.06 : 0}
              stroke="none"
              style={{
                cursor: props.tool === "calibration" ? "move" : "default",
                pointerEvents: props.tool === "calibration" ? "all" : "none",
              }}
              onPointerDown={onPlacementDown}
            />
            <text
              x={px("x", placedBox[0])}
              y={px("y", placedBox[3]) + 14}
              fontSize={11}
              fontFamily="var(--font-mono)"
              fill="var(--accent)"
              style={{ pointerEvents: "none" }}
            >
              {`${placement.overlay.id8} ${placement.move.theta_deg} deg`}
            </text>
            {props.tool === "calibration" && (
              <g>
                <line
                  x1={px("x", placeCentre[0])}
                  y1={px("y", placedBox[1])}
                  x2={px("x", placeCentre[0])}
                  y2={px("y", placedBox[1]) - ROTATE_HANDLE_PX}
                  stroke="var(--accent)"
                  strokeWidth={1}
                />
                <circle
                  data-testid="placement-turn"
                  cx={px("x", placeCentre[0])}
                  cy={px("y", placedBox[1]) - ROTATE_HANDLE_PX}
                  r={7}
                  fill="var(--surface)"
                  stroke="var(--accent)"
                  strokeWidth={1.5}
                  style={{ cursor: "grab" }}
                  onPointerDown={onTurnDown}
                >
                  <title>turn: 90 degree steps, Alt for free</title>
                </circle>
              </g>
            )}
          </g>
        )}
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
        {draftKind
          ? `click to add points, double-click or Enter to finish, Esc to cancel; snap ${props.snapMm} mm, Alt for free`
          : altHeld
          ? "free placement (Alt)"
          : props.tool === "calibration"
            ? `snap ${props.snapMm} mm and 90 deg, Alt for free; scale is locked`
            : `snap ${props.snapMm} mm, Alt for free`}
      </div>
    </div>
  );
}
