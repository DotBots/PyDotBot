import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { BotMarker, MARKER_SCALE_VAR } from "../BotMarker";
import { DEFAULT_BODY_COLOR_MODE } from "../bodyColor";
import { areaColor } from "../areaColor";
import { siteViewMarginMm, withMargin } from "../frame";
import { gridStepMm } from "../grid";
import { DEFAULT_ROBOT_DRAWING } from "../robotDrawing";
import type { Area, SpinCircle, UnifiedBot } from "../types";
import {
  clampCam,
  FRAME_CAMERA,
  steppedScale,
  viewCentre,
  viewGeom,
  wheelDeltaPx,
  wheelScale,
  zoomAbout,
  ZOOM_MAX_FLOOR,
  ZOOM_MAX_PX_PER_MM,
  type Camera,
  type ViewGeom,
} from "../zoom";
import type { EditKind, Tool } from "./keys";
import { freshKey, freshName, type Doc, type DocObject, type ObjectKind, type Point } from "./model";
import { canvasToMm, coincident, moved, pxPerMmAt, resized, snap, spanned, toBox, type Handle } from "./plan";
import type { Rect } from "./types";

export interface PlanLayers {
  grid: boolean;
  robots: boolean;
  boxes: boolean;
  circles: boolean;
}

export const DEFAULT_LAYERS: PlanLayers = { grid: true, robots: true, boxes: true, circles: true };

/** The kind an entity key belongs to on the plan. */
export function kindOfKey(key: string): EditKind {
  if (key.startsWith("area:")) return "areas";
  if (key.startsWith("wall:") || key.startsWith("obstacle:")) return "walls";
  if (key.startsWith("object:")) return "objects";
  if (key.startsWith("box:")) return "stations";
  return "frame";
}

const OBJECT_TOOLS: Partial<Record<Tool, ObjectKind>> = {
  charger: "charger",
  dock: "dock",
  landmark: "landmark",
  camera: "camera",
};

const OBJECT_GLYPH: Record<ObjectKind, string> = { charger: "⚡", dock: "D", landmark: "◆", camera: "◉" };

type Drag =
  | { type: "pan"; from: Point; cam: Camera; moved: boolean }
  | { type: "move"; key: string; from: Point; moved: boolean }
  | { type: "resize"; key: string; handle: Handle }
  | { type: "area"; from: Point; to: Point }
  | { type: "measure"; from: Point; to: Point };

interface PlanCanvasProps {
  doc: Doc;
  kind: EditKind;
  tool: Tool;
  selected: string | null;
  /** False on a page that may not write: everything selects, nothing moves. */
  editable: boolean;
  boxes: { index: number; rect: Rect }[];
  circles: SpinCircle[];
  layers: PlanLayers;
  robots: UnifiedBot[];
  /** Labels on the plan scaled up, for a projector. */
  labelScale?: number;
  onSelect: (key: string | null) => void;
  onEdit: (doc: Doc) => void;
  onCursor?: (mm: Point | null) => void;
  /** A one-shot tool finished; back to Select. */
  onToolDone: () => void;
}

const MIN_AREA_MM = 20;

export const PlanCanvas: React.FC<PlanCanvasProps> = (props) => {
  const { doc, kind, tool, selected, editable } = props;
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState<{ w: number; h: number }>({ w: 800, h: 600 });
  const [cam, setCam] = useState<Camera>(FRAME_CAMERA);
  const [drag, setDrag] = useState<Drag | null>(null);
  // A drag's edit, drawn live and committed as one step on release
  const [preview, setPreview] = useState<Doc | null>(null);
  const [poly, setPoly] = useState<Point[]>([]);
  const [hover, setHover] = useState<Point | null>(null);
  const [, setHoverBot] = useState<string | null>(null);

  const extent: [number, number] = doc.extent_mm ?? [2000, 2000];
  const floor: Area = { x: 0, y: 0, w: extent[0], h: extent[1] };
  const viewport = useMemo(() => withMargin(floor, siteViewMarginMm(floor)), [extent[0], extent[1]]);
  const geom: ViewGeom = useMemo(() => viewGeom(size.w, size.h, viewport), [size, viewport]);
  const maxScale = Math.max(ZOOM_MAX_FLOOR, viewport.w > 0 ? ZOOM_MAX_PX_PER_MM / (geom.boxW / viewport.w) : 1);
  const perMm = pxPerMmAt(cam, viewport, geom);
  const chrome = 1 / cam.scale;
  const label = (props.labelScale ?? 1) * chrome;
  const shown = preview ?? doc;

  useLayoutEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const measure = () => setSize({ w: el.clientWidth || 800, h: el.clientHeight || 600 });
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const local = (e: { clientX: number; clientY: number }): Point => {
    const r = wrapRef.current?.getBoundingClientRect();
    return [e.clientX - (r?.left ?? 0), e.clientY - (r?.top ?? 0)];
  };
  const mmAt = (e: { clientX: number; clientY: number; altKey?: boolean }): Point => {
    const [x, y] = canvasToMm(local(e), cam, viewport, geom);
    const on = !e.altKey;
    return [snap(x, on), snap(y, on)];
  };
  const px = (p: Point) => toBox(p, viewport, geom);
  const pxLen = (mm: number) => (mm / viewport.w) * geom.boxW;

  // Ctrl or Cmd with the wheel zooms about the pointer; the wheel alone pans
  const wheelRef = useRef<(e: WheelEvent) => void>(() => {});
  wheelRef.current = (e: WheelEvent) => {
    e.preventDefault();
    if (e.ctrlKey || e.metaKey) {
      const at = local(e);
      setCam((c) => zoomAbout(c, wheelScale(c.scale, wheelDeltaPx(e), maxScale), { x: at[0], y: at[1] }, geom));
    } else {
      setCam((c) => clampCam({ ...c, tx: c.tx - e.deltaX, ty: c.ty - e.deltaY }, geom));
    }
  };
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const on = (e: WheelEvent) => wheelRef.current(e);
    el.addEventListener("wheel", on, { passive: false });
    return () => el.removeEventListener("wheel", on);
  }, []);

  const finishPoly = useCallback(() => {
    const need = tool === "obstacle" ? 3 : 2;
    if (poly.length >= need) {
      const k = tool === "obstacle" ? "obstacle" : "wall";
      const key = freshKey(doc, k);
      const entry = { key, name: null, points: poly, comment: null, was: null };
      props.onEdit(k === "wall" ? { ...doc, walls: [...doc.walls, entry] } : { ...doc, obstacles: [...doc.obstacles, entry] });
      props.onSelect(key);
    }
    setPoly([]);
  }, [poly, tool, doc, props]);

  // Enter ends a wall or obstacle; Esc drops it and never commits it
  useEffect(() => {
    if (poly.length === 0 && !drag) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Enter" && poly.length) finishPoly();
      else if (e.key === "Escape") {
        setPoly([]);
        setDrag(null);
        setPreview(null);
      } else return;
      e.preventDefault();
      e.stopImmediatePropagation();
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [poly, drag, finishPoly]);

  const placeObject = (at: Point, k: ObjectKind) => {
    const key = freshKey(doc, "object");
    const name = freshName(`${k}-1`, doc.objects.map((o) => o.name));
    const obj: DocObject = { key, name, kind: k, x: at[0], y: at[1], heading_deg: 0, comment: null, was: null };
    props.onEdit({ ...doc, objects: [...doc.objects, obj] });
    props.onSelect(key);
    props.onToolDone();
  };

  const onFloorDown = (e: React.PointerEvent) => {
    if (e.button !== 0) return;
    wrapRef.current?.setPointerCapture?.(e.pointerId);
    const at = mmAt(e);
    if (editable && tool === "area") return setDrag({ type: "area", from: at, to: at });
    if (tool === "measure") return setDrag({ type: "measure", from: at, to: at });
    if (editable && (tool === "wall" || tool === "obstacle")) return setPoly((p) => [...p, at]);
    const objectKind = OBJECT_TOOLS[tool];
    if (editable && objectKind) return placeObject(at, objectKind);
    setDrag({ type: "pan", from: local(e), cam, moved: false });
  };

  const onEntityDown = (e: React.PointerEvent, key: string) => {
    if (e.button !== 0 || tool !== "select") return;
    e.stopPropagation();
    wrapRef.current?.setPointerCapture?.(e.pointerId);
    props.onSelect(key);
    const own = kindOfKey(key) === kind;
    if (editable && own && !key.startsWith("box:")) setDrag({ type: "move", key, from: mmAt(e), moved: false });
  };

  const onHandleDown = (e: React.PointerEvent, key: string, handle: Handle) => {
    if (e.button !== 0) return;
    e.stopPropagation();
    wrapRef.current?.setPointerCapture?.(e.pointerId);
    setDrag({ type: "resize", key, handle });
  };

  const onMove = (e: React.PointerEvent) => {
    const at = mmAt(e);
    setHover(at);
    props.onCursor?.(at);
    if (!drag) return;
    if (drag.type === "pan") {
      const p = local(e);
      const dx = p[0] - drag.from[0];
      const dy = p[1] - drag.from[1];
      if (Math.hypot(dx, dy) > 3 || drag.moved) {
        setDrag({ ...drag, moved: true });
        setCam(clampCam({ ...drag.cam, tx: drag.cam.tx + dx, ty: drag.cam.ty + dy }, geom));
      }
    } else if (drag.type === "move") {
      const dx = at[0] - drag.from[0];
      const dy = at[1] - drag.from[1];
      if (dx || dy || drag.moved) {
        setDrag({ ...drag, moved: true });
        setPreview(moved(doc, drag.key, dx, dy));
      }
    } else if (drag.type === "resize") {
      setPreview({ ...doc, areas: doc.areas.map((a) => (a.key === drag.key ? resized(a, drag.handle, at) : a)) });
    } else {
      setDrag({ ...drag, to: at });
    }
  };

  const onUp = () => {
    if (drag?.type === "pan" && !drag.moved && tool === "select") props.onSelect(null);
    if (drag?.type === "area") {
      const r = spanned(drag.from, drag.to);
      if (r.w >= MIN_AREA_MM && r.h >= MIN_AREA_MM) {
        const key = freshKey(doc, "area");
        const name = freshName("area", doc.areas.map((a) => a.name));
        props.onEdit({ ...doc, areas: [...doc.areas, { key, name, ...r, role: null, comment: null, was: null }] });
        props.onSelect(key);
        props.onToolDone();
      }
    }
    if (preview) props.onEdit(preview);
    setPreview(null);
    setDrag(null);
  };

  const zoomBy = (presses: number) =>
    setCam((c) => zoomAbout(c, steppedScale(c.scale, presses, maxScale), viewCentre(geom), geom));

  // --- drawing ---------------------------------------------------------

  const [fx, fy] = px([0, 0]);
  const [fw, fh] = [pxLen(extent[0]), pxLen(extent[1])];
  const gridMm = perMm * 100 >= 14 ? 100 : gridStepMm(perMm);
  const gridLines: React.ReactNode[] = [];
  if (props.layers.grid && gridMm > 0) {
    for (let x = gridMm; x < extent[0]; x += gridMm) {
      const [gx] = px([x, 0]);
      gridLines.push(<line key={`gx${x}`} x1={gx} y1={fy} x2={gx} y2={fy + fh} stroke="var(--grid)" strokeWidth={chrome} />);
    }
    for (let y = gridMm; y < extent[1]; y += gridMm) {
      const [, gy] = px([0, y]);
      gridLines.push(<line key={`gy${y}`} x1={fx} y1={gy} x2={fx + fw} y2={gy} stroke="var(--grid)" strokeWidth={chrome} />);
    }
  }

  const sel = (key: string) => key === selected;
  const interactive = tool === "select";
  const outlines = coincident([
    { label: "floor", rect: [0, 0, extent[0], extent[1]] },
    ...shown.areas.map((a) => ({ label: a.name, rect: [a.x, a.y, a.x + a.w, a.y + a.h] as [number, number, number, number] })),
    ...(props.layers.boxes ? props.boxes.map((b) => ({ label: `S${b.index} box`, rect: b.rect })) : []),
  ]);

  const areaNodes = shown.areas.map((a) => {
    const [x, y] = px([a.x, a.y]);
    const colour = areaColor({ x: a.x, y: a.y, w: a.w, h: a.h, name: a.name, role: a.role ?? undefined }, shown.areas.map((b) => ({ ...b, role: b.role ?? undefined })));
    const on = sel(a.key);
    return (
      <g key={a.key} data-testid={`area-${a.name}`}>
        <rect
          x={x}
          y={y}
          width={pxLen(a.w)}
          height={pxLen(a.h)}
          fill={on ? `color-mix(in srgb, ${colour} 18%, transparent)` : "transparent"}
          stroke={colour}
          strokeWidth={(on ? 2 : 1.25) * chrome}
          strokeDasharray={`${6 * chrome} ${4 * chrome}`}
          style={{ cursor: interactive ? (kind === "areas" ? "move" : "pointer") : undefined, pointerEvents: interactive ? "all" : "none" }}
          onPointerDown={(e) => onEntityDown(e, a.key)}
        />
        <text x={x + 10 * chrome} y={y + 15 * label} fontSize={11 * label} fill={colour} style={{ pointerEvents: "none" }}>
          {a.name}
          {a.role ? ` · ${a.role}` : ""}
        </text>
      </g>
    );
  });

  const barrier = (b: { key: string; points: Point[] }, closed: boolean) => {
    const pts = b.points.map((p) => px(p).join(",")).join(" ");
    const on = sel(b.key);
    const common = {
      points: pts,
      stroke: on ? "var(--accent)" : "var(--text)",
      strokeWidth: (on ? 3.5 : 2.5) * chrome,
      fill: closed ? "color-mix(in srgb, var(--text) 18%, transparent)" : "none",
      style: { cursor: interactive ? "pointer" : undefined, pointerEvents: (interactive ? "all" : "none") as React.CSSProperties["pointerEvents"] },
      onPointerDown: (e: React.PointerEvent) => onEntityDown(e, b.key),
    };
    return closed ? <polygon key={b.key} data-testid={b.key} {...common} /> : <polyline key={b.key} data-testid={b.key} {...common} />;
  };

  const objectNodes = shown.objects.map((o) => {
    const [x, y] = px([o.x, o.y]);
    const s = 16 * chrome;
    const rad = ((o.heading_deg ?? 0) * Math.PI) / 180;
    const on = sel(o.key);
    return (
      <g
        key={o.key}
        data-testid={`object-${o.name}`}
        style={{ cursor: interactive ? "pointer" : undefined, pointerEvents: interactive ? "all" : "none" }}
        onPointerDown={(e) => onEntityDown(e, o.key)}
      >
        <rect x={x - s / 2} y={y - s / 2} width={s} height={s} rx={3 * chrome} fill="var(--elevated)" stroke={on ? "var(--accent)" : "var(--muted)"} strokeWidth={(on ? 2 : 1) * chrome} />
        <line x1={x} y1={y} x2={x + Math.sin(rad) * s} y2={y + Math.cos(rad) * s} stroke="var(--muted)" strokeWidth={1.5 * chrome} />
        <text x={x} y={y + 4 * chrome} fontSize={10 * chrome} textAnchor="middle" fill="var(--text)" style={{ pointerEvents: "none" }}>
          {OBJECT_GLYPH[o.kind]}
        </text>
        <text x={x + s * 0.7} y={y - s * 0.6} fontSize={10 * label} fill="var(--muted)" style={{ pointerEvents: "none" }}>
          {o.name}
        </text>
      </g>
    );
  });

  const boxNodes = props.layers.boxes
    ? props.boxes.map((b, i) => {
        const inset = (i + 1) * 3 * chrome;
        const [x0, y0] = px([b.rect[0], b.rect[1]]);
        const [x1, y1] = px([b.rect[2], b.rect[3]]);
        const on = sel(`box:${b.index}`);
        const hue = `var(--st-${b.index % 2})`;
        return (
          <g key={`box-${b.index}`} data-testid={`box-${b.index}`}>
            <rect
              x={x0 + inset}
              y={y0 + inset}
              width={Math.max(x1 - x0 - 2 * inset, 0)}
              height={Math.max(y1 - y0 - 2 * inset, 0)}
              fill={on ? `color-mix(in srgb, ${hue} 14%, transparent)` : "none"}
              stroke={hue}
              strokeWidth={(on ? 2.5 : 1.5) * chrome}
              strokeDasharray={b.index >= 2 ? `${5 * chrome} ${3 * chrome}` : undefined}
              style={{ pointerEvents: kind === "stations" && interactive ? "stroke" : "none", cursor: "pointer" }}
              onPointerDown={(e) => onEntityDown(e, `box:${b.index}`)}
            />
            {kind === "stations" && (
              <text x={x0 + inset + 4 * chrome} y={y1 - inset - 5 * chrome} fontSize={11 * label} fill={hue}>
                S{b.index}
              </text>
            )}
          </g>
        );
      })
    : null;

  const circleNodes = props.layers.circles
    ? props.circles.map((c, i) => {
        const [x, y] = px([c.x, c.y]);
        const r = pxLen(c.radius_mm);
        const hue = `var(--st-${c.station % 2})`;
        return (
          <g key={`c${i}`} style={{ pointerEvents: "none" }}>
            <circle cx={x} cy={y} r={r} fill="none" stroke={hue} strokeOpacity={0.75} strokeWidth={chrome} />
            <circle cx={x} cy={y} r={1.5 * chrome} fill={hue} />
          </g>
        );
      })
    : null;

  const selectedArea = kind === "areas" && editable ? shown.areas.find((a) => a.key === selected) : undefined;
  const handles =
    selectedArea && tool === "select"
      ? (["nw", "ne", "sw", "se"] as Handle[]).map((h) => {
          const x = h.endsWith("w") ? selectedArea.x : selectedArea.x + selectedArea.w;
          const y = h.startsWith("n") ? selectedArea.y : selectedArea.y + selectedArea.h;
          const [hx, hy] = px([x, y]);
          const s = 9 * chrome;
          return (
            <rect
              key={h}
              data-testid={`handle-${h}`}
              x={hx - s / 2}
              y={hy - s / 2}
              width={s}
              height={s}
              fill="var(--surface)"
              stroke="var(--accent)"
              strokeWidth={1.5 * chrome}
              style={{ cursor: h === "nw" || h === "se" ? "nwse-resize" : "nesw-resize" }}
              onPointerDown={(e) => onHandleDown(e, selectedArea.key, h)}
            />
          );
        })
      : null;

  const draft = (() => {
    if (drag?.type === "area") {
      const r = spanned(drag.from, drag.to);
      const [x, y] = px([r.x, r.y]);
      return (
        <g>
          <rect x={x} y={y} width={pxLen(r.w)} height={pxLen(r.h)} fill="color-mix(in srgb, var(--accent) 10%, transparent)" stroke="var(--accent)" strokeWidth={1.5 * chrome} />
          <text x={x + pxLen(r.w) / 2} y={y - 6 * chrome} fontSize={11 * label} textAnchor="middle" fill="var(--text)">
            {r.w} × {r.h} mm
          </text>
        </g>
      );
    }
    if (drag?.type === "measure") {
      const [x0, y0] = px(drag.from);
      const [x1, y1] = px(drag.to);
      const d = Math.hypot(drag.to[0] - drag.from[0], drag.to[1] - drag.from[1]);
      return (
        <g data-testid="measure">
          <line x1={x0} y1={y0} x2={x1} y2={y1} stroke="var(--text)" strokeWidth={1.5 * chrome} strokeDasharray={`${4 * chrome} ${3 * chrome}`} />
          <text x={(x0 + x1) / 2 + 6 * chrome} y={(y0 + y1) / 2 - 6 * chrome} fontSize={12 * label} fill="var(--text)">
            {Math.round(d)} mm
          </text>
        </g>
      );
    }
    if (poly.length) {
      const pts = [...poly, ...(hover ? [hover] : [])].map((p) => px(p).join(",")).join(" ");
      return <polyline points={pts} fill="none" stroke="var(--accent)" strokeWidth={2 * chrome} strokeDasharray={`${5 * chrome} ${3 * chrome}`} />;
    }
    return null;
  })();

  // Zero and the axes, in the Frame kind
  const [zx, zy] = px([0, 0]);
  const axis = 80 * chrome;
  const frameNodes =
    kind === "frame" ? (
      <g data-testid="zero" style={{ pointerEvents: "none" }}>
        <circle cx={zx} cy={zy} r={7 * chrome} fill="none" stroke="var(--text)" strokeWidth={1.5 * chrome} />
        <line x1={zx} y1={zy} x2={zx + axis} y2={zy} stroke="var(--text)" strokeWidth={1.5 * chrome} />
        <line x1={zx} y1={zy} x2={zx} y2={zy + axis} stroke="var(--text)" strokeWidth={1.5 * chrome} />
        <text x={zx + axis + 4 * chrome} y={zy + 4 * chrome} fontSize={11 * label} fill="var(--text)">x</text>
        <text x={zx - 3 * chrome} y={zy + axis + 12 * chrome} fontSize={11 * label} fill="var(--text)">y</text>
      </g>
    ) : (
      <circle cx={zx} cy={zy} r={4 * chrome} fill="none" stroke="var(--muted)" strokeWidth={chrome} style={{ pointerEvents: "none" }} />
    );

  // Robots, positioned as the console's animator places them
  const markers = useRef(new Map<string, HTMLElement>());
  const attach = useCallback((id: string, el: HTMLElement | null) => {
    if (el) markers.current.set(id, el);
    else markers.current.delete(id);
  }, []);
  const robots = props.layers.robots ? props.robots.filter((b) => b.position) : [];
  useLayoutEffect(() => {
    for (const b of robots) {
      const el = markers.current.get(b.id);
      if (!el || !b.position) continue;
      const [x, y] = toBox([b.position.x, b.position.y], viewport, geom);
      el.style.translate = `${x}px ${y}px`;
    }
  });

  const cursor =
    tool === "select" ? (drag?.type === "pan" && drag.moved ? "grabbing" : "default") : tool === "measure" ? "crosshair" : "copy";

  return (
    <div
      ref={wrapRef}
      data-testid="plan"
      onPointerDown={onFloorDown}
      onPointerMove={onMove}
      onPointerUp={onUp}
      onPointerLeave={() => props.onCursor?.(null)}
      onDoubleClick={() => poly.length && finishPoly()}
      style={{
        position: "relative",
        flex: 1,
        minWidth: 0,
        minHeight: 0,
        overflow: "hidden",
        background: "var(--canvas)",
        cursor,
        touchAction: "none",
        userSelect: "none",
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: 0,
          transform: `translate(${cam.tx}px, ${cam.ty}px) scale(${cam.scale})`,
          transformOrigin: "50% 50%",
          [MARKER_SCALE_VAR as string]: chrome,
        }}
      >
        <div style={{ position: "absolute", left: "50%", top: "50%", width: geom.boxW, height: geom.boxH, transform: "translate(-50%, -50%)" }}>
          <svg width={geom.boxW} height={geom.boxH} style={{ position: "absolute", inset: 0, overflow: "visible" }}>
            <path
              d={`M0,0H${geom.boxW}V${geom.boxH}H0Z M${fx},${fy}V${fy + fh}H${fx + fw}V${fy}Z`}
              fill="var(--outside)"
              fillRule="evenodd"
              style={{ pointerEvents: "none" }}
            />
            <rect x={fx} y={fy} width={fw} height={fh} fill="var(--surface)" style={{ pointerEvents: "none" }} />
            {gridLines}
            <rect data-testid="floor" x={fx} y={fy} width={fw} height={fh} fill="none" stroke="var(--muted)" strokeWidth={chrome} style={{ pointerEvents: "none" }} />
            {circleNodes}
            {boxNodes}
            {areaNodes}
            {shown.walls.map((w) => barrier(w, false))}
            {shown.obstacles.map((o) => barrier(o, true))}
            {objectNodes}
            {frameNodes}
            {handles}
            {draft}
          </svg>
          <div style={{ position: "absolute", inset: 0, pointerEvents: "none" }} data-testid="robots">
            {robots.map((b) => (
              <BotMarker
                key={b.id}
                bot={b}
                selected={false}
                hovered={false}
                solid={1}
                perMm={perMm}
                drawing={DEFAULT_ROBOT_DRAWING}
                botCount={robots.length}
                batteryBars={false}
                colorMode={DEFAULT_BODY_COLOR_MODE}
                attach={attach}
                onPointerDown={() => {}}
                onHover={setHoverBot}
              />
            ))}
          </div>
        </div>
      </div>
      {outlines.length > 0 && (
        <div
          data-testid="coincident-chip"
          title="These are drawn once: their rectangles are the same"
          style={{
            position: "absolute",
            left: 12,
            bottom: 12,
            maxWidth: "calc(100% - 140px)",
            fontSize: 11,
            padding: "4px 9px",
            borderRadius: 7,
            border: "1px solid var(--hairline)",
            background: "var(--surface)",
            color: "var(--muted)",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          One rectangle: {outlines[0].join(" = ")}
        </div>
      )}
      <div style={{ position: "absolute", right: 12, bottom: 12, display: "flex", gap: 4 }} onPointerDown={(e) => e.stopPropagation()}>
        {[
          ["−", () => zoomBy(-1), "Zoom out"],
          ["+", () => zoomBy(1), "Zoom in"],
          ["◎", () => setCam(FRAME_CAMERA), "Fit the floor"],
        ].map(([text, act, title]) => (
          <button
            key={title as string}
            type="button"
            title={title as string}
            aria-label={title as string}
            onClick={act as () => void}
            style={{
              width: 28,
              height: 28,
              borderRadius: 7,
              border: "1px solid var(--hairline)",
              background: "var(--surface)",
              color: "var(--text)",
              cursor: "pointer",
            }}
          >
            {text as string}
          </button>
        ))}
      </div>
    </div>
  );
};
