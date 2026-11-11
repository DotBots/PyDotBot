import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { BotMarker, MARKER_SCALE_VAR } from "../BotMarker";
import { DEFAULT_BODY_COLOR_MODE } from "../bodyColor";
import { areaColor } from "../areaColor";
import { gridStepMm } from "../grid";
import { DEFAULT_ROBOT_DRAWING } from "../robotDrawing";
import { ringDash, spinRings } from "../shared/spinRings";
import { facing } from "../siteObjects";
import type { SpinCircle, UnifiedBot } from "../types";
import {
  clampCam,
  FRAME_CAMERA,
  scaleForFraction,
  steppedScale,
  viewCentre,
  viewGeom,
  wheelDeltaPx,
  wheelScale,
  zoomAbout,
  zoomFraction,
  ZOOM_MAX_FLOOR,
  ZOOM_MAX_PX_PER_MM,
  ZOOM_STEP,
  type Camera,
  type ViewGeom,
} from "../zoom";
import { movedHandover, handover as handoverOf } from "./coverage";
import { planViewport } from "./mapView";
import { Icon } from "./icons";
import type { EditKind, Tool } from "./keys";
import { freshKey, freshName, numberedName, type Doc, type DocObject, type ObjectKind, type Point } from "./model";
import {
  canvasToMm,
  coincident,
  handleAt,
  HANDLES,
  keysWithin,
  movedAll,
  pxPerMmAt,
  resized,
  snapPoint,
  snapTargets,
  spanned,
  toBox,
  type Handle,
} from "./plan";
import type { Rect } from "./types";

export interface PlanLayers {
  grid: boolean;
  robots: boolean;
  boxes: boolean;
  circles: boolean;
  stations: boolean;
}

export const DEFAULT_LAYERS: PlanLayers = { grid: true, robots: true, boxes: true, circles: true, stations: true };

/** A station's estimated place: over (x, y) on the floor, `height` mm up. */
export interface StationPose {
  index: number;
  x: number;
  y: number;
  height: number;
}

/** Two presses of the zoom further out than the whole viewport, so what
 * stands around the floor can be seen. */
export const PLAN_ZOOM_MIN = ZOOM_STEP ** -2;


/** The kind an entity key belongs to on the plan; robots belong to none. */
export function kindOfKey(key: string): EditKind {
  if (key.startsWith("area:")) return "areas";
  if (key.startsWith("wall:") || key.startsWith("obstacle:")) return "walls";
  if (key.startsWith("object:")) return "objects";
  if (key.startsWith("box:")) return "stations";
  if (key.startsWith("robot:")) return "view";
  return "frame";
}

const KIND_PREFIXES: Partial<Record<EditKind, string[]>> = {
  areas: ["area:"],
  walls: ["wall:", "obstacle:"],
  objects: ["object:"],
};

const OBJECT_TOOLS: Partial<Record<Tool, ObjectKind>> = {
  charger: "charger",
  dock: "dock",
  landmark: "landmark",
  camera: "camera",
};

const OBJECT_ICON: Record<ObjectKind, "charger" | "dock" | "landmark" | "camera"> = {
  charger: "charger",
  dock: "dock",
  landmark: "landmark",
  camera: "camera",
};

type Drag =
  | { type: "pan"; from: Point; cam: Camera; moved: boolean }
  | { type: "move"; keys: string[]; from: Point; moved: boolean }
  | { type: "resize"; key: string; handle: Handle }
  | { type: "box"; index: number; handle: Handle; rect: Rect }
  | { type: "handover"; axis: 0 | 1 }
  | { type: "area"; from: Point; to: Point }
  | { type: "marquee"; from: Point; to: Point; base: string[] }
  | { type: "measure"; from: Point; to: Point }
  | { type: "floor"; from: Point; turn: boolean };

/** What an overlay drawn on the plan needs: frame mm to the box's pixels. */
export interface PlanPaint {
  px: (p: Point) => Point;
  pxLen: (mm: number) => number;
  /** One screen pixel, in the box's own units at this zoom. */
  chrome: number;
  /** A label's size factor: `chrome` times the label scale. */
  label: number;
}

interface PlanCanvasProps {
  doc: Doc;
  kind: EditKind;
  tool: Tool;
  selected: string[];
  /** The area edge or corner arrows move, if one is picked. */
  edge: { key: string; handle: Handle } | null;
  /** False on a page that may not write: everything selects, nothing moves. */
  editable: boolean;
  boxes: { index: number; rect: Rect }[];
  circles: SpinCircle[];
  layers: PlanLayers;
  robots: UnifiedBot[];
  /** Labels on the plan scaled up, for a projector. */
  labelScale?: number;
  /** Drawn under the areas, e.g. who gives the fix, for the boxes as drawn now. */
  underlay?: (paint: PlanPaint, boxes: { index: number; rect: Rect }[]) => React.ReactNode;
  /** Drawn over everything, e.g. suggested spins. */
  overlay?: (paint: PlanPaint, boxes: { index: number; rect: Rect }[]) => React.ReactNode;
  /** A floating card the page shows over the plan, e.g. a legend. */
  children?: React.ReactNode;
  onSelect: (keys: string[]) => void;
  onEdge: (edge: { key: string; handle: Handle } | null) => void;
  /** A station box dragged to a new rectangle; absent where boxes are read only. */
  onBoxEdit?: (index: number, rect: Rect) => void;
  /** Both boxes at once, as a drag of their handover line leaves them. */
  onBoxesEdit?: (rects: Record<number, Rect>) => void;
  /** Where the stations stand, estimated; drawn in View and Stations. */
  stations?: StationPose[];
  onEdit: (doc: Doc) => void;
  onCursor?: (mm: Point | null) => void;
  /** What the last drag snapped to, for the status bar. */
  onSnap?: (to: string) => void;
  /** A click with the point inspector, or null when it leaves. */
  onProbe?: (mm: Point | null, at: Point | null) => void;
  /** A one-shot tool finished; back to Select. */
  onToolDone: () => void;
  /** A click on the floor with a tool that picks a point, e.g. the pivot. */
  onPoint?: (mm: Point) => void;
  /** With the capture tool, a drag on the floor moves the whole room: called
   * from the press to each pointer position, `turn` when Alt or Shift was held
   * at the press, `done` on release. */
  onFloorDrag?: (from: Point, to: Point, turn: boolean, done: boolean) => void;
  onShortcuts?: () => void;
  /** Bumped by the page to fit the floor again. */
  fitSignal?: number;
  /** False hides the zoom, fit, scale and shortcuts, as for a projector. */
  chrome?: boolean;
  /** A camera the page sets, e.g. to match the 3D view; a new `n` applies it. */
  camRequest?: { cam: Camera; n: number };
  /** The camera and canvas size, as they change. */
  onView?: (cam: Camera, size: { w: number; h: number }) => void;
}

const MIN_AREA_MM = 20;

/** "Floor, field and S0 coverage are the same rectangle". */
export function sameRectangle(labels: string[]): string {
  const said = labels.length > 1 ? `${labels.slice(0, -1).join(", ")} and ${labels[labels.length - 1]}` : labels[0];
  return `${said.charAt(0).toUpperCase()}${said.slice(1)} are the same rectangle`;
}
const SNAP_REACH_PX = 8;

/** The scale bar's length: the longest round length under `maxPx` on screen. */
export function scaleBar(perMm: number, maxPx = 130): { mm: number; px: number } {
  const ladder = [10, 20, 50, 100, 200, 250, 500, 1000, 2000, 5000];
  let mm = ladder[0];
  for (const c of ladder) if (c * perMm <= maxPx) mm = c;
  return { mm, px: mm * perMm };
}

export const PlanCanvas: React.FC<PlanCanvasProps> = (props) => {
  const { doc, kind, tool, selected, editable } = props;
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState<{ w: number; h: number }>({ w: 800, h: 600 });
  const [cam, setCam] = useState<Camera>(props.camRequest?.cam ?? FRAME_CAMERA);
  useEffect(() => {
    if (props.camRequest) setCam(props.camRequest.cam);
  }, [props.camRequest?.n]);
  const onViewRef = useRef(props.onView);
  onViewRef.current = props.onView;
  const [drag, setDrag] = useState<Drag | null>(null);
  // A drag's edit, drawn live and committed as one step on release
  const [preview, setPreview] = useState<Doc | null>(null);
  const [poly, setPoly] = useState<Point[]>([]);
  const [hover, setHover] = useState<Point | null>(null);
  const [boxPreview, setBoxPreview] = useState<{ index: number; rect: Rect } | null>(null);
  const [pairPreview, setPairPreview] = useState<Record<number, Rect> | null>(null);
  const [, setHoverBot] = useState<string | null>(null);

  const extent: [number, number] = doc.extent_mm ?? [2000, 2000];
  // The floor, and any station standing near it
  const framed = props.layers.stations ? (props.stations ?? []) : [];
  const nearKey = framed.map((s) => `${Math.round(s.x)},${Math.round(s.y)}`).join(";");
  const viewport = useMemo(() => planViewport(extent, framed), [extent[0], extent[1], nearKey]);
  const geom: ViewGeom = useMemo(() => viewGeom(size.w, size.h, viewport), [size, viewport]);
  const maxScale = Math.max(ZOOM_MAX_FLOOR, viewport.w > 0 ? ZOOM_MAX_PX_PER_MM / (geom.boxW / viewport.w) : 1);
  const perMm = pxPerMmAt(cam, viewport, geom);
  const chrome = 1 / cam.scale;
  const label = (props.labelScale ?? 1) * chrome;
  const shown = preview ?? doc;
  const sel = (key: string) => selected.includes(key);

  useEffect(() => {
    if (props.fitSignal) setCam(FRAME_CAMERA);
  }, [props.fitSignal]);
  useEffect(() => {
    onViewRef.current?.(cam, size);
  }, [cam, size]);

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
  const rawMm = (e: { clientX: number; clientY: number }): Point => canvasToMm(local(e), cam, viewport, geom);
  const reach = perMm > 0 ? SNAP_REACH_PX / perMm : 0;
  const snapped = (e: { clientX: number; clientY: number; altKey?: boolean }, skip: string[] = []) => {
    const s = snapPoint(rawMm(e), snapTargets(doc, skip), reach, !e.altKey);
    return s;
  };
  const mmAt = (e: { clientX: number; clientY: number; altKey?: boolean }, skip: string[] = []): Point => snapped(e, skip).point;
  const px = (p: Point) => toBox(p, viewport, geom);
  const pxLen = (mm: number) => (mm / viewport.w) * geom.boxW;
  const paint: PlanPaint = { px, pxLen, chrome, label };

  // Ctrl or Cmd with the wheel zooms about the pointer; the wheel alone pans
  const wheelRef = useRef<(e: WheelEvent) => void>(() => {});
  wheelRef.current = (e: WheelEvent) => {
    e.preventDefault();
    if (e.ctrlKey || e.metaKey) {
      const at = local(e);
      setCam((c) => zoomAbout(c, wheelScale(c.scale, wheelDeltaPx(e), maxScale, PLAN_ZOOM_MIN), { x: at[0], y: at[1] }, geom));
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
    // A double click, or a click then Enter, places its last point twice
    const points = poly.filter((p, i) => i === 0 || p[0] !== poly[i - 1][0] || p[1] !== poly[i - 1][1]);
    if (points.length >= need) {
      const k = tool === "obstacle" ? "obstacle" : "wall";
      const key = freshKey(doc, k);
      const entry = { key, name: null, points, comment: null, was: null };
      props.onEdit(k === "wall" ? { ...doc, walls: [...doc.walls, entry] } : { ...doc, obstacles: [...doc.obstacles, entry] });
      props.onSelect([key]);
    }
    setPoly([]);
  }, [poly, tool, doc, props]);

  // Enter ends a wall or obstacle; Esc drops a drawing and never commits it
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
    const name = numberedName(k, doc.objects.map((o) => o.name));
    const obj: DocObject = { key, name, kind: k, x: at[0], y: at[1], heading_deg: 0, comment: null, was: null };
    props.onEdit({ ...doc, objects: [...doc.objects, obj] });
    props.onSelect([key]);
    props.onToolDone();
  };

  const capture = (e: React.PointerEvent) => {
    try {
      wrapRef.current?.setPointerCapture?.(e.pointerId);
    } catch {
      // a synthetic pointer has nothing to capture
    }
  };

  const onFloorDown = (e: React.PointerEvent) => {
    if (e.button !== 0) return;
    capture(e);
    const at = mmAt(e);
    if (editable && tool === "area") return setDrag({ type: "area", from: at, to: at });
    if (tool === "measure") return setDrag({ type: "measure", from: at, to: at });
    if (tool === "probe") return props.onProbe?.(rawMm(e), local(e));
    if (tool === "turn") return props.onPoint?.(at);
    if (tool === "capture" && props.onFloorDrag) return setDrag({ type: "floor", from: rawMm(e), turn: e.altKey || e.shiftKey });
    if (editable && (tool === "wall" || tool === "obstacle")) return setPoly((p) => [...p, at]);
    const objectKind = OBJECT_TOOLS[tool];
    if (editable && objectKind) return placeObject(at, objectKind);
    if (e.shiftKey && tool === "select") {
      const p = rawMm(e);
      return setDrag({ type: "marquee", from: p, to: p, base: selected });
    }
    setDrag({ type: "pan", from: local(e), cam, moved: false });
  };

  const onEntityDown = (e: React.PointerEvent, key: string) => {
    if (e.button !== 0 || tool !== "select") return;
    e.stopPropagation();
    capture(e);
    // Shift-drag over a thing of another kind still selects a rectangle
    if (e.shiftKey && kind !== "view" && kindOfKey(key) !== kind) {
      const p = rawMm(e);
      setDrag({ type: "marquee", from: p, to: p, base: selected });
      return;
    }
    props.onEdge(null);
    if (e.shiftKey) {
      props.onSelect(sel(key) ? selected.filter((k) => k !== key) : [...selected.filter((k) => kindOfKey(k) === kindOfKey(key)), key]);
      return;
    }
    const keys = sel(key) ? selected : [key];
    if (!sel(key)) props.onSelect([key]);
    const own = kindOfKey(key) === kind;
    const movable = keys.filter((k) => !k.startsWith("box:") && !k.startsWith("robot:"));
    if (editable && own && movable.length) setDrag({ type: "move", keys: movable, from: mmAt(e, movable), moved: false });
  };

  const onHandleDown = (e: React.PointerEvent, key: string, handle: Handle) => {
    if (e.button !== 0) return;
    e.stopPropagation();
    capture(e);
    props.onEdge({ key, handle });
    setDrag({ type: "resize", key, handle });
  };

  const onMove = (e: React.PointerEvent) => {
    const at = mmAt(e);
    setHover(at);
    props.onCursor?.(at);
    if (tool === "probe" && !drag) props.onProbe?.(rawMm(e), local(e));
    if (!drag) return;
    if (drag.type === "box") {
      const s = snapped(e);
      props.onSnap?.(s.to);
      const r = resized({ x: drag.rect[0], y: drag.rect[1], w: drag.rect[2] - drag.rect[0], h: drag.rect[3] - drag.rect[1] }, drag.handle, s.point);
      setBoxPreview({ index: drag.index, rect: [r.x, r.y, r.x + r.w, r.y + r.h] });
      return;
    }
    if (drag.type === "floor") {
      props.onFloorDrag?.(drag.from, rawMm(e), drag.turn, false);
      return;
    }
    if (drag.type === "handover") {
      const s = snapped(e);
      setPairPreview(movedHandover(props.boxes, Math.round(s.point[drag.axis])));
      return;
    }
    if (drag.type === "pan") {
      const p = local(e);
      const dx = p[0] - drag.from[0];
      const dy = p[1] - drag.from[1];
      if (Math.hypot(dx, dy) > 3 || drag.moved) {
        setDrag({ ...drag, moved: true });
        setCam(clampCam({ ...drag.cam, tx: drag.cam.tx + dx, ty: drag.cam.ty + dy }, geom));
      }
    } else if (drag.type === "move") {
      const s = snapped(e, drag.keys);
      const dx = s.point[0] - drag.from[0];
      const dy = s.point[1] - drag.from[1];
      if (dx || dy || drag.moved) {
        setDrag({ ...drag, moved: true });
        setPreview(movedAll(doc, drag.keys, dx, dy));
        props.onSnap?.(s.to);
      }
    } else if (drag.type === "resize") {
      const s = snapped(e, [drag.key]);
      props.onSnap?.(s.to);
      setPreview({ ...doc, areas: doc.areas.map((a) => (a.key === drag.key ? resized(a, drag.handle, s.point) : a)) });
    } else if (drag.type === "marquee") {
      setDrag({ ...drag, to: rawMm(e) });
    } else {
      const s = snapped(e);
      props.onSnap?.(s.to);
      setDrag({ ...drag, to: s.point });
    }
  };

  const onUp = (e?: React.PointerEvent) => {
    if (drag?.type === "floor" && e) props.onFloorDrag?.(drag.from, rawMm(e), drag.turn, true);
    if (drag?.type === "box" && boxPreview) props.onBoxEdit?.(boxPreview.index, boxPreview.rect);
    setBoxPreview(null);
    if (drag?.type === "handover" && pairPreview) props.onBoxesEdit?.(pairPreview);
    setPairPreview(null);
    if (drag?.type === "pan" && !drag.moved && tool === "select") {
      props.onSelect([]);
      props.onEdge(null);
    }
    if (drag?.type === "area") {
      const r = spanned(drag.from, drag.to);
      if (r.w >= MIN_AREA_MM && r.h >= MIN_AREA_MM) {
        const key = freshKey(doc, "area");
        const name = freshName("area", doc.areas.map((a) => a.name));
        props.onEdit({ ...doc, areas: [...doc.areas, { key, name, ...r, role: null, comment: null, was: null }] });
        props.onSelect([key]);
        props.onToolDone();
      }
    }
    if (drag?.type === "marquee") {
      const r = spanned(drag.from, drag.to);
      const prefixes = KIND_PREFIXES[kind] ?? ["area:", "wall:", "obstacle:", "object:"];
      const inside = keysWithin(doc, [r.x, r.y, r.x + r.w, r.y + r.h], prefixes);
      props.onSelect([...new Set([...drag.base, ...inside])]);
    }
    if (preview) props.onEdit(preview);
    setPreview(null);
    setDrag(null);
  };

  const zoomTo = (scale: number) => setCam((c) => zoomAbout(c, scale, viewCentre(geom), geom));
  const zoomBy = (presses: number) => zoomTo(steppedScale(cam.scale, presses, maxScale, PLAN_ZOOM_MIN));

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
  // Ruler labels every half metre (or metre on a large floor), outside the floor
  const rulerStep = extent[0] > 3000 || extent[1] > 3000 ? 1000 : 500;
  const ruler: React.ReactNode[] = [];
  const rl = (mm: number) => (mm === 0 ? "0 m" : `${mm / 1000}${mm % 1000 === 0 ? " m" : ""}`);
  for (let x = 0; x <= extent[0]; x += rulerStep) {
    const [rx] = px([x, 0]);
    ruler.push(
      <text key={`rx${x}`} className="tl" x={rx + (x === 0 ? 10 : 3) * chrome} y={fy - 7 * chrome} fontSize={9.5 * label}>
        {rl(x)}
      </text>,
    );
  }
  for (let y = rulerStep; y <= extent[1]; y += rulerStep) {
    const [, ry] = px([0, y]);
    ruler.push(
      <text key={`ry${y}`} className="tl" x={fx - 8 * chrome} y={ry + 3 * chrome} fontSize={9.5 * label} textAnchor="end">
        {rl(y)}
      </text>,
    );
  }

  const interactive = tool === "select";
  const outlines = coincident([
    { label: "floor", rect: [0, 0, extent[0], extent[1]] },
    ...shown.areas.map((a) => ({ label: a.name, rect: [a.x, a.y, a.x + a.w, a.y + a.h] as [number, number, number, number] })),
    ...(props.layers.boxes ? props.boxes.map((b) => ({ label: `S${b.index} coverage`, rect: b.rect })) : []),
  ]);

  const areaNodes = shown.areas.map((a) => {
    const [x, y] = px([a.x, a.y]);
    const colour = areaColor({ x: a.x, y: a.y, w: a.w, h: a.h, name: a.name, role: a.role ?? undefined }, shown.areas.map((b) => ({ ...b, role: b.role ?? undefined })));
    const on = sel(a.key);
    const dim = kind !== "view" && kind !== "areas" && !on;
    return (
      <g key={a.key} data-testid={`area-${a.name}`} opacity={dim ? 0.55 : 1}>
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
        <text className="halo" x={x + 8 * chrome} y={y + 14 * label} fontSize={11 * label} fill={colour} strokeWidth={3 * chrome} style={{ pointerEvents: "none" }}>
          {a.name}
          {a.role && a.role !== a.name ? ` · ${a.role}` : ""}
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
      strokeLinecap: "round" as const,
      strokeLinejoin: "round" as const,
      fill: closed ? "color-mix(in srgb, var(--text) 18%, transparent)" : "none",
      style: { cursor: interactive ? "pointer" : undefined, pointerEvents: (interactive ? "all" : "none") as React.CSSProperties["pointerEvents"] },
      onPointerDown: (e: React.PointerEvent) => onEntityDown(e, b.key),
    };
    return closed ? <polygon key={b.key} data-testid={b.key} {...common} /> : <polyline key={b.key} data-testid={b.key} {...common} />;
  };

  const objectNodes = shown.objects.map((o) => {
    const [x, y] = px([o.x, o.y]);
    const s = 22 * chrome;
    const [hx, hy] = facing(o.heading_deg ?? 0);
    const on = sel(o.key);
    return (
      <g
        key={o.key}
        data-testid={`object-${o.name}`}
        style={{ cursor: interactive ? "pointer" : undefined, pointerEvents: interactive ? "all" : "none" }}
        onPointerDown={(e) => onEntityDown(e, o.key)}
      >
        <line x1={x} y1={y} x2={x + hx * s} y2={y + hy * s} stroke={on ? "var(--accent)" : "var(--muted)"} strokeWidth={1.5 * chrome} />
        <rect
          x={x - s / 2}
          y={y - s / 2}
          width={s}
          height={s}
          rx={5 * chrome}
          fill="var(--elevated)"
          stroke={on ? "var(--accent)" : "var(--muted)"}
          strokeWidth={(on ? 2 : 1) * chrome}
        />
        <g transform={`translate(${x - 7 * chrome} ${y - 7 * chrome}) scale(${(14 * chrome) / 24})`} color="var(--text)" style={{ pointerEvents: "none" }}>
          <Icon name={OBJECT_ICON[o.kind]} size={24} className="" />
        </g>
        <text className="tl halo" x={x} y={y + s / 2 + 12 * label} fontSize={10 * label} textAnchor="middle" fill="var(--muted)" strokeWidth={3 * chrome} style={{ pointerEvents: "none" }}>
          {o.name}
        </text>
      </g>
    );
  });

  const shownBoxes = pairPreview
    ? props.boxes.map((b) => (pairPreview[b.index] ? { index: b.index, rect: pairPreview[b.index] } : b))
    : boxPreview
      ? props.boxes.map((b) => (b.index === boxPreview.index ? boxPreview : b))
      : props.boxes;
  // The handover line takes a drag in the Stations kind, when it runs straight across an axis
  const line = kind === "stations" && props.onBoxesEdit && tool === "select" && shownBoxes.length === 2 ? handoverOf(shownBoxes[0].rect, shownBoxes[1].rect) : null;
  const lineAxis = line ? (line.from[0] === line.to[0] ? 0 : line.from[1] === line.to[1] ? 1 : null) : null;
  const handoverGrip =
    line && lineAxis !== null ? (
      <line
        data-testid="handover-grip"
        x1={px(line.from)[0]}
        y1={px(line.from)[1]}
        x2={px(line.to)[0]}
        y2={px(line.to)[1]}
        stroke="transparent"
        strokeWidth={14 * chrome}
        style={{ cursor: lineAxis === 0 ? "ew-resize" : "ns-resize", pointerEvents: "stroke" }}
        onPointerDown={(e) => {
          if (e.button !== 0) return;
          e.stopPropagation();
          capture(e);
          setDrag({ type: "handover", axis: lineAxis });
        }}
      >
        <title>Drag to move the handover; both coverages follow, their overlap kept</title>
      </line>
    ) : null;
  const boxNodes = props.layers.boxes
    ? shownBoxes.map((b, i) => {
        const inset = (i + 1) * 3 * chrome;
        const [x0, y0] = px([b.rect[0], b.rect[1]]);
        const [x1, y1] = px([b.rect[2], b.rect[3]]);
        const on = sel(`box:${b.index}`);
        const hue = `var(--st-${b.index % 2})`;
        const strong = kind === "stations" || on;
        return (
          <g key={`box-${b.index}`} data-testid={`box-${b.index}`} opacity={strong ? 1 : 0.6}>
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
            {kind === "stations" &&
              (b.index % 2 === 0 ? (
                <text className="halo" x={x0 + inset + 5 * chrome} y={y1 - inset - 6 * chrome} fontSize={11 * label} fill={hue} fontWeight={600} strokeWidth={3 * chrome}>
                  S{b.index} box
                </text>
              ) : (
                <text className="halo" x={x1 - inset - 5 * chrome} y={y0 + inset + 14 * label} fontSize={11 * label} fill={hue} fontWeight={600} textAnchor="end" strokeWidth={3 * chrome}>
                  S{b.index} box
                </text>
              ))}
          </g>
        );
      })
    : null;

  const circleNodes = props.layers.circles
    ? spinRings(props.circles).map((c, i) => {
        const [x, y] = px([c.x, c.y]);
        const r = pxLen(c.radius_mm);
        return (
          <g key={`c${i}`} data-testid="spin-ring" style={{ pointerEvents: "none" }} opacity={kind === "stations" || kind === "view" ? 1 : 0.5}>
            {c.stations.map((st, k) => {
              const dash = ringDash(k, c.stations.length, 2 * Math.PI * r);
              return (
                <circle
                  key={st}
                  cx={x}
                  cy={y}
                  r={r}
                  fill="none"
                  stroke={`var(--st-${st % 2})`}
                  strokeOpacity={0.85}
                  strokeWidth={chrome}
                  strokeDasharray={dash.dasharray}
                  strokeDashoffset={dash.offset}
                />
              );
            })}
            <circle cx={x} cy={y} r={1.5 * chrome} fill="var(--muted)" />
          </g>
        );
      })
    : null;

  const selectedBox = kind === "stations" && props.onBoxEdit && tool === "select" && selected.length === 1 ? shownBoxes.find((b) => `box:${b.index}` === selected[0]) : undefined;
  const boxHandles = selectedBox
    ? HANDLES.map((h) => {
        const rr = { x: selectedBox.rect[0], y: selectedBox.rect[1], w: selectedBox.rect[2] - selectedBox.rect[0], h: selectedBox.rect[3] - selectedBox.rect[1] };
        const [hx, hy] = px(handleAt(rr, h));
        const s = 10 * chrome;
        const picked = props.edge?.key === `box:${selectedBox.index}` && props.edge.handle === h;
        const cursor = h === "n" || h === "s" ? "ns-resize" : h === "e" || h === "w" ? "ew-resize" : h === "nw" || h === "se" ? "nwse-resize" : "nesw-resize";
        return (
          <rect
            key={`bh-${h}`}
            data-testid={`box-handle-${h}`}
            x={hx - s / 2}
            y={hy - s / 2}
            width={s}
            height={s}
            rx={2 * chrome}
            fill={picked ? `var(--st-${selectedBox.index % 2})` : "var(--surface)"}
            stroke={`var(--st-${selectedBox.index % 2})`}
            strokeWidth={1.5 * chrome}
            style={{ cursor }}
            onPointerDown={(e) => {
              if (e.button !== 0) return;
              e.stopPropagation();
              capture(e);
              props.onEdge({ key: `box:${selectedBox.index}`, handle: h });
              setDrag({ type: "box", index: selectedBox.index, handle: h, rect: selectedBox.rect });
            }}
          >
            <title>Drag to move this edge of S{selectedBox.index}'s box; click, then the arrow keys nudge it</title>
          </rect>
        );
      })
    : null;
  const selectedAreas = kind === "areas" && editable && tool === "select" ? shown.areas.filter((a) => sel(a.key)) : [];
  const handles =
    selectedAreas.length === 1
      ? HANDLES.map((h) => {
          const a = selectedAreas[0];
          const [hx, hy] = px(handleAt(a, h));
          const s = 9 * chrome;
          const picked = props.edge?.key === a.key && props.edge.handle === h;
          const cursor = h === "n" || h === "s" ? "ns-resize" : h === "e" || h === "w" ? "ew-resize" : h === "nw" || h === "se" ? "nwse-resize" : "nesw-resize";
          return (
            <rect
              key={h}
              data-testid={`handle-${h}`}
              x={hx - s / 2}
              y={hy - s / 2}
              width={s}
              height={s}
              rx={1.5 * chrome}
              fill={picked ? "var(--accent)" : "var(--surface)"}
              stroke="var(--accent)"
              strokeWidth={1.5 * chrome}
              style={{ cursor }}
              onPointerDown={(e) => onHandleDown(e, a.key, h)}
            >
              <title>Drag to resize; click, then use the arrow keys to nudge this edge</title>
            </rect>
          );
        })
      : null;
  const boxPill = boxPreview
    ? (() => {
        const [x, y] = px([(boxPreview.rect[0] + boxPreview.rect[2]) / 2, boxPreview.rect[3]]);
        const t = `S${boxPreview.index} x ${boxPreview.rect[0]}-${boxPreview.rect[2]} · y ${boxPreview.rect[1]}-${boxPreview.rect[3]}`;
        return (
          <g style={{ pointerEvents: "none" }}>
            <rect x={x - 90 * chrome} y={y + 7 * chrome} width={180 * chrome} height={17 * chrome} rx={4 * chrome} fill={`var(--st-${boxPreview.index % 2})`} />
            <text x={x} y={y + 19.5 * chrome} fontSize={10.5 * chrome} textAnchor="middle" fill="#fff" fontFamily="var(--font-mono)" fontWeight={600}>
              {t}
            </text>
          </g>
        );
      })()
    : null;
  const sizePill =
    selectedAreas.length === 1 && (drag?.type === "resize" || drag?.type === "move")
      ? (() => {
          const a = selectedAreas[0];
          const [x, y] = px([a.x + a.w / 2, a.y + a.h]);
          const t = `${Math.round(a.w)} × ${Math.round(a.h)}`;
          return (
            <g style={{ pointerEvents: "none" }}>
              <rect x={x - 34 * chrome} y={y + 7 * chrome} width={68 * chrome} height={17 * chrome} rx={4 * chrome} fill="var(--accent)" />
              <text x={x} y={y + 19.5 * chrome} fontSize={10.5 * chrome} textAnchor="middle" fill="#fff" fontFamily="var(--font-mono)" fontWeight={600}>
                {t}
              </text>
            </g>
          );
        })()
      : null;

  const drawing = (() => {
    if (drag?.type === "area") {
      const r = spanned(drag.from, drag.to);
      const [x, y] = px([r.x, r.y]);
      return (
        <g>
          <rect x={x} y={y} width={pxLen(r.w)} height={pxLen(r.h)} fill="color-mix(in srgb, var(--accent) 10%, transparent)" stroke="var(--accent)" strokeWidth={1.5 * chrome} />
          <text className="halo" x={x + pxLen(r.w) / 2} y={y - 6 * chrome} fontSize={11 * label} textAnchor="middle" fill="var(--text)" fontFamily="var(--font-mono)" strokeWidth={3 * chrome}>
            {r.w} × {r.h} mm
          </text>
        </g>
      );
    }
    if (drag?.type === "marquee") {
      const r = spanned(drag.from, drag.to);
      const [x, y] = px([r.x, r.y]);
      return (
        <rect
          data-testid="marquee"
          x={x}
          y={y}
          width={pxLen(r.w)}
          height={pxLen(r.h)}
          fill="color-mix(in srgb, var(--accent) 7%, transparent)"
          stroke="var(--accent)"
          strokeDasharray={`${4 * chrome} ${3 * chrome}`}
          strokeWidth={chrome}
        />
      );
    }
    if (drag?.type === "measure") {
      const [x0, y0] = px(drag.from);
      const [x1, y1] = px(drag.to);
      const d = Math.hypot(drag.to[0] - drag.from[0], drag.to[1] - drag.from[1]);
      return (
        <g data-testid="measure">
          <line x1={x0} y1={y0} x2={x1} y2={y1} stroke="var(--text)" strokeWidth={1.5 * chrome} strokeDasharray={`${4 * chrome} ${3 * chrome}`} />
          <text className="halo" x={(x0 + x1) / 2 + 6 * chrome} y={(y0 + y1) / 2 - 6 * chrome} fontSize={12 * label} fill="var(--text)" fontFamily="var(--font-mono)" strokeWidth={3 * chrome}>
            {Math.round(d)} mm · Δx {Math.round(drag.to[0] - drag.from[0])} · Δy {Math.round(drag.to[1] - drag.from[1])}
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

  // Zero: a ringed point, and its axes in the Frame kind
  const [zx, zy] = px([0, 0]);
  const axis = 80 * chrome;
  const frameNodes = (
    <g data-testid={kind === "frame" ? "zero" : undefined} style={{ pointerEvents: "none" }}>
      <circle cx={zx} cy={zy} r={6 * chrome} fill="var(--canvas)" stroke="var(--text)" strokeWidth={1.4 * chrome} />
      <circle cx={zx} cy={zy} r={2 * chrome} fill="var(--text)" />
      {kind === "frame" && (
        <>
          <line x1={zx + 6 * chrome} y1={zy} x2={zx + axis} y2={zy} stroke="var(--text)" strokeWidth={1.5 * chrome} />
          <path d={`M${zx + axis},${zy} l${-7 * chrome},${-4 * chrome} v${8 * chrome}z`} fill="var(--text)" />
          <line x1={zx} y1={zy + 6 * chrome} x2={zx} y2={zy + axis} stroke="var(--text)" strokeWidth={1.5 * chrome} />
          <path d={`M${zx},${zy + axis} l${-4 * chrome},${-7 * chrome} h${8 * chrome}z`} fill="var(--text)" />
          <text className="halo" x={zx + axis + 5 * chrome} y={zy + 4 * chrome} fontSize={11 * label} fill="var(--text)" strokeWidth={3 * chrome}>
            x
          </text>
          <text className="halo" x={zx + 6 * chrome} y={zy + axis + 4 * chrome} fontSize={11 * label} fill="var(--text)" strokeWidth={3 * chrome}>
            y
          </text>
          <text className="tl halo" x={zx + 10 * chrome} y={zy - 9 * chrome} fontSize={10 * label} strokeWidth={3 * chrome}>
            origin (0, 0)
          </text>
        </>
      )}
    </g>
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
  const onRobotDown = useCallback(
    (e: React.PointerEvent, id: string) => {
      if (e.button !== 0) return;
      e.stopPropagation();
      props.onSelect([`robot:${id}`]);
    },
    [props.onSelect],
  );
  const selectedRobot = selected.find((k) => k.startsWith("robot:"))?.slice(6);

  const cursor =
    tool === "select" ? (drag?.type === "pan" && drag.moved ? "grabbing" : "default") : tool === "measure" || tool === "probe" ? "crosshair" : "copy";
  const bar = scaleBar(perMm);
  const frac = zoomFraction(cam.scale, maxScale, PLAN_ZOOM_MIN);

  // Where the stations stand: a marker on the floor, or an arrow at the
  // canvas edge pointing at one out of view
  const poses = props.layers.stations && (kind === "view" || kind === "stations") ? (props.stations ?? []) : [];
  const onScreen = (p: Point): Point => {
    const [bx, by] = px(p);
    return [size.w / 2 + cam.tx + cam.scale * (bx - geom.boxW / 2), size.h / 2 + cam.ty + cam.scale * (by - geom.boxH / 2)];
  };

  const poseNodes = poses.map((s) => {
    const [x, y] = px([s.x, s.y]);
    const hue = `var(--st-${s.index % 2})`;
    const r = 8 * chrome;
    const tip = `S${s.index} stands about (${Math.round(s.x)}, ${Math.round(s.y)}) mm, ${(s.height / 1000).toFixed(1)} m up: estimated, not to tape`;
    return (
      <g key={`pose-${s.index}`} data-testid={`station-pos-${s.index}`} style={{ pointerEvents: "visiblePainted" }}>
        <title>{tip}</title>
        <circle cx={x} cy={y} r={r} fill={`color-mix(in srgb, ${hue} 28%, transparent)`} stroke={hue} strokeWidth={1.8 * chrome} />
        <line x1={x - r * 1.6} y1={y} x2={x + r * 1.6} y2={y} stroke={hue} strokeWidth={1.3 * chrome} />
        <line x1={x} y1={y - r * 1.6} x2={x} y2={y + r * 1.6} stroke={hue} strokeWidth={1.3 * chrome} />
        <text className="halo" x={x + r + 6 * chrome} y={y - 2 * chrome} fontSize={11.5 * label} fill={hue} fontWeight={700} strokeWidth={3 * chrome}>
          S{s.index} ≈ {(s.height / 1000).toFixed(1)} m up
        </text>
        <text className="tl halo" x={x + r + 6 * chrome} y={y + 11 * label} fontSize={9.5 * label} fontFamily="var(--font-mono)" strokeWidth={3 * chrome}>
          ({Math.round(s.x)}, {Math.round(s.y)}) mm
        </text>
      </g>
    );
  });
  const poseArrows = poses.flatMap((s) => {
    const [sx, sy] = onScreen([s.x, s.y]);
    if (sx >= 0 && sy >= 0 && sx <= size.w && sy <= size.h) return [];
    // Clear of the floating bars along the top and bottom
    const ax = Math.max(40, Math.min(size.w - 140, sx));
    const ay = Math.max(70, Math.min(size.h - 130, sy));
    const deg = (Math.atan2(sy - ay, sx - ax) * 180) / Math.PI;
    const right = ax > size.w / 2;
    return [
      <div
        key={`arrow-${s.index}`}
        className="pose-arrow"
        data-testid={`station-arrow-${s.index}`}
        title={`S${s.index} stands about (${Math.round(s.x)}, ${Math.round(s.y)}) mm, out of view: estimated, not to tape`}
        style={{ left: ax, top: ay, color: `var(--st-${s.index % 2})` }}
      >
        <span className="tip" style={{ transform: `translate(-50%, -50%) rotate(${deg}deg)` }}>
          ➜
        </span>
        <span className={`lb${right ? " r" : ""}`}>
          S{s.index} ≈ {(s.height / 1000).toFixed(1)} m up
        </span>
      </div>,
    ];
  });

  return (
    <div style={{ position: "relative", flex: 1, minWidth: 0, minHeight: 0, display: "flex" }}>
      <div
        ref={wrapRef}
        data-testid="plan"
        onPointerDown={onFloorDown}
        onPointerMove={onMove}
        onPointerUp={onUp}
        onPointerLeave={() => {
          props.onCursor?.(null);
          setHover(null);
          if (tool === "probe") props.onProbe?.(null, null);
        }}
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
          boxShadow: kind !== "view" ? "inset 0 0 0 1px color-mix(in srgb, var(--text) 10%, transparent)" : undefined,
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
                d={`M${-geom.boxW * 4},${-geom.boxH * 4}H${geom.boxW * 5}V${geom.boxH * 5}H${-geom.boxW * 4}Z M${fx},${fy}V${fy + fh}H${fx + fw}V${fy}Z`}
                fill="var(--outside)"
                fillRule="evenodd"
                style={{ pointerEvents: "none" }}
              />
              {gridLines}
              {ruler}
              {props.underlay?.(paint, shownBoxes)}
              <rect data-testid="floor" x={fx} y={fy} width={fw} height={fh} fill="none" stroke="var(--muted)" strokeWidth={chrome} strokeDasharray={doc.extent_mm ? undefined : `${3 * chrome} ${5 * chrome}`} style={{ pointerEvents: "none" }} />
              <text className="tl halo" x={fx + fw / 2} y={fy + fh + 16 * label} fontSize={10 * label} textAnchor="middle" strokeWidth={3 * chrome}>
                {doc.extent_mm ? `floor ${extent[0]} × ${extent[1]} mm` : "floor not measured yet: a placeholder"}
              </text>
              {circleNodes}
              {boxNodes}
              {areaNodes}
              {shown.walls.map((w) => barrier(w, false))}
              {shown.obstacles.map((o) => barrier(o, true))}
              {objectNodes}
              {frameNodes}
              {poseNodes}
              {props.overlay?.(paint, shownBoxes)}
              {handoverGrip}
              {handles}
              {boxHandles}
              {boxPill}
              {sizePill}
              {drawing}
            </svg>
            <div style={{ position: "absolute", inset: 0, pointerEvents: "none" }} data-testid="robots">
              {robots.map((b) => (
                <div key={b.id} style={{ pointerEvents: tool === "select" ? "auto" : "none" }}>
                  <BotMarker
                    bot={b}
                    selected={b.id === selectedRobot}
                    hovered={false}
                    solid={1}
                    perMm={perMm}
                    drawing={DEFAULT_ROBOT_DRAWING}
                    botCount={robots.length}
                    batteryBars={false}
                    colorMode={DEFAULT_BODY_COLOR_MODE}
                    attach={attach}
                    onPointerDown={onRobotDown}
                    onHover={setHoverBot}
                  />
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
      {poseArrows}
      {props.children}
      {props.chrome !== false && outlines.length > 0 && (
        <div className="float chipc" data-testid="coincident-chip" title="These rectangles are the same, so they are drawn as one outline">
          <Icon name="rect" size={13} />
          {sameRectangle(outlines[0])}
        </div>
      )}
      {props.chrome !== false && (
      <>
      <div className="float zoom" onPointerDown={(e) => e.stopPropagation()}>
        <button type="button" className="zb" title="Zoom out" aria-label="Zoom out" onClick={() => zoomBy(-1)}>
          −
        </button>
        <div
          className="track"
          role="slider"
          aria-label="Zoom"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(frac * 100)}
          tabIndex={0}
          style={{ cursor: "pointer" }}
          onPointerDown={(e) => {
            const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
            zoomTo(scaleForFraction((e.clientX - r.left) / r.width, maxScale, PLAN_ZOOM_MIN));
          }}
          onKeyDown={(e) => {
            if (e.key === "ArrowRight" || e.key === "ArrowUp") zoomBy(1);
            else if (e.key === "ArrowLeft" || e.key === "ArrowDown") zoomBy(-1);
            else return;
            e.preventDefault();
            e.stopPropagation();
          }}
        >
          <i style={{ width: `${frac * 100}%` }} />
          <b style={{ left: `${frac * 100}%` }} />
        </div>
        <button type="button" className="zb" title="Zoom in" aria-label="Zoom in" onClick={() => zoomBy(1)}>
          +
        </button>
      </div>
      <button type="button" className="float fitbtn" title="Fit the floor" aria-label="Fit the floor" onClick={() => setCam(FRAME_CAMERA)}>
        <Icon name="fit" size={17} />
      </button>
      <div className="scale" data-testid="scale-bar" aria-hidden>
        <i style={{ width: bar.px }} />
        {bar.mm >= 1000 ? `${bar.mm / 1000} m` : `${bar.mm} mm`}
      </div>
      {props.onShortcuts && (
        <button type="button" className="float shortbtn" onClick={props.onShortcuts} title="Every key of this page (?)">
          <span className="k2">?</span> shortcuts
        </button>
      )}
      </>
      )}
    </div>
  );
};
