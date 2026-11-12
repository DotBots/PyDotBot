import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { areaColor } from "../areaColor";
import { heldCalibrationId } from "../botFacts";
import type { UnifiedBot } from "../types";
import { fogImage, handover, overlapBand, switchLabel, type Boxes, type Coverage, type Geometry } from "./coverage";
import type { Doc, Point } from "./model";
import { contextBounds, contextStep, FLOOR_FILL, floorStep, lens, stationLabel, roomFit, roomProject, TOP_DOWN, turn, zoomAt, type Insets, type RoomCam, type Size, type Zoom } from "./mapView";
import type { CoverageMode } from "./StationsPanel";
import { fixImageCached } from "./StationsLayer";
import { ORIGIN_HINT } from "./keys";

// The room as a twin: the floor with its areas and origin on a grid, each
// station on a pole at its estimated height with rays to the corners of its
// own coverage, coverage tinted on the floor with the handover line, the
// robots live. An orthographic projection, so a millimetre on the floor is
// the same length everywhere along its axis and the floor maps affinely;
// dragging orbits it. The page holds the camera and the zoom.

export const EL_MIN = 10;
export const EL_MAX = 85;

export const PRESETS: { key: string; label: string; cam: RoomCam }[] = [
  { key: "top", label: "Top", cam: TOP_DOWN },
  { key: "front", label: "Front", cam: { az: 0, el: EL_MIN } },
  { key: "side", label: "Side", cam: { az: -90, el: EL_MIN } },
  { key: "34", label: "3/4", cam: { az: 45, el: 35 } },
];
export const HOME: RoomCam = PRESETS[3].cam;
export const clampEl = (el: number) => Math.max(EL_MIN, Math.min(EL_MAX, el));

/** The preset `cam` is at, if any. */
export const presetOf = (cam: RoomCam) => PRESETS.find((p) => Math.abs(turn(cam.az, p.cam.az)) < 0.5 && Math.abs(p.cam.el - cam.el) < 0.5)?.key ?? null;

/** A label wanting a place: its anchor, its size, and how to draw it at a top-left corner. */
export interface Want {
  key: string;
  at: Point;
  w: number;
  h: number;
  /** Lower is placed first. */
  prio: number;
  /** Placed even when every spot overlaps something. */
  must: boolean;
  /** Distance from the anchor, px. */
  gap: number;
}

type Box4 = [number, number, number, number];

const hits = (a: Box4, b: Box4) => a[0] < b[2] && b[0] < a[2] && a[1] < b[3] && b[1] < a[3];

/** Each label at the first of eight spots around its anchor, near first then
 * farther out, that overlaps no label placed before it and no obstacle, inside
 * `bounds`; a label that finds none is left out, or, if it must show, put
 * where it covers the fewest things. */
export function placeLabels(wants: Want[], obstacles: Box4[], bounds: Box4): Map<string, Point> {
  const out = new Map<string, Point>();
  const taken: Box4[] = [];
  for (const l of [...wants].sort((a, b) => a.prio - b.prio)) {
    const [x, y] = l.at;
    // A label for something out of view would point at nothing
    const far = l.must ? 40 : 0;
    if (x < bounds[0] - far || y < bounds[1] - far || x > bounds[2] + far || y > bounds[3] + far) continue;
    const spots: Point[] = [l.gap, l.gap + 14, l.gap + 30]
      .flatMap((g) => [
        [x + g, y - l.h / 2],
        [x - g - l.w, y - l.h / 2],
        [x + g, y - g - l.h],
        [x - g - l.w, y - g - l.h],
        [x + g, y + g],
        [x - g - l.w, y + g],
        [x - l.w / 2, y - g - l.h],
        [x - l.w / 2, y + g],
      ])
      .map(([sx, sy]) => [Math.max(bounds[0], Math.min(bounds[2] - l.w, sx)), Math.max(bounds[1], Math.min(bounds[3] - l.h, sy))] as Point);
    const box = (p: Point): Box4 => [p[0] - 1, p[1] - 1, p[0] + l.w + 1, p[1] + l.h + 1];
    const covers = (p: Point) => taken.filter((t) => hits(box(p), t)).length + obstacles.filter((o) => hits(box(p), o)).length;
    const free = spots.find((p) => covers(p) === 0);
    const at = free ?? (l.must ? spots.reduce((a, b) => (covers(b) < covers(a) ? b : a)) : null);
    if (!at) continue;
    out.set(l.key, at);
    taken.push(box(at));
  }
  return out;
}

let measurer: CanvasRenderingContext2D | null | undefined;
const fonts = new Map<string, string>();
/** The width of `text` at `size` px in the page's own font, measured once a
 * canvas can; a fair estimate where none can. */
function textW(text: string, size: number, mono = false, bold = false): number {
  if (measurer === undefined) {
    try {
      measurer = typeof document !== "undefined" && !/jsdom/.test(navigator.userAgent) ? document.createElement("canvas").getContext("2d") : null;
    } catch {
      measurer = null;
    }
  }
  if (!measurer) return text.length * size * (mono ? 0.61 : 0.56);
  const v = mono ? "--font-mono" : "--font-ui";
  if (!fonts.has(v)) fonts.set(v, getComputedStyle(document.documentElement).getPropertyValue(v).trim() || (mono ? "monospace" : "sans-serif"));
  measurer.font = `${bold ? 700 : 400} ${size}px ${fonts.get(v)}`;
  return measurer.measureText(text).width;
}

const poly = (ps: Point[]) => ps.map((p) => p.map((v) => Math.round(v * 10) / 10).join(",")).join(" ");

export const RoomView: React.FC<{
  doc: Doc;
  extent: [number, number];
  geometry: Geometry | null;
  boxes: Boxes;
  coverage: Coverage | null;
  mode: CoverageMode;
  bots: UnifiedBot[];
  /** The calibration drawn, by name, and the id robots would report for it. */
  shownName: string | null;
  shownId: string | null;
  stationFit?: Record<number, number>;
  /** The coverage in a few words, said against what is in use. */
  coverageNote: string;
  light: boolean;
  /** Large: for a projector, labels bigger. */
  large?: boolean;
  /** Canvas kept clear for bars floating over it. */
  insets: Insets;
  cam: RoomCam;
  zoom: Zoom;
  /** A drag orbited the view. */
  onCam: (cam: RoomCam) => void;
  onZoom: (zoom: Zoom | ((z: Zoom) => Zoom)) => void;
  /** A pointer went down on the view: any camera move under way stops. */
  onGrab?: () => void;
  /** Double-click: back to the 3/4 view. */
  onHome: () => void;
  /** The canvas's size, px, as it changes. */
  onSize?: (size: Size) => void;
  selectedStation?: number | null;
  onSelectStation?: (index: number | null) => void;
  selectedRobot?: string | null;
  onSelectRobot?: (id: string | null) => void;
  /** The selection: an entity's key, or a whole kind as a Checks row picks it. */
  selected?: string[];
  /** The origin clicked, on a page that can move it. */
  onOrigin?: () => void;
}> = (props) => {
  const { doc, extent, geometry, boxes, coverage, mode, bots, shownName, shownId, stationFit, coverageNote, light, large, insets, cam, zoom, onCam, onZoom, selectedStation, onSelectStation } = props;
  const topInset = insets.top;
  const holder = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState({ w: 900, h: 600 });
  const onSizeRef = useRef(props.onSize);
  onSizeRef.current = props.onSize;
  useLayoutEffect(() => {
    const el = holder.current;
    if (!el) return;
    const measure = () => {
      const next = { w: el.clientWidth || 900, h: el.clientHeight || 600 };
      setSize(next);
      onSizeRef.current?.(next);
    };
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const [ownPick, setOwnPick] = useState<number | null>(null);
  const picked = onSelectStation ? (selectedStation ?? null) : ownPick;
  const pick = onSelectStation ?? setOwnPick;

  // Pointers down: one orbits (or pans, with Shift or the right button), two pinch
  const pointers = useRef(new Map<number, Point>());
  const drag = useRef<{ x: number; y: number; cam: RoomCam; zoom: Zoom; pan: boolean } | null>(null);
  const pinch = useRef<{ dist: number; mid: Point; zoom: Zoom } | null>(null);
  const sizeRef = useRef(size);
  sizeRef.current = size;
  const onZoomRef = useRef(onZoom);
  onZoomRef.current = onZoom;
  // The wheel, and a trackpad's pinch (a wheel with Ctrl), zoom toward the pointer
  useEffect(() => {
    const el = holder.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const r = el.getBoundingClientRect();
      const factor = Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0015));
      onZoomRef.current((z) => zoomAt(z, factor, [e.clientX - r.left, e.clientY - r.top], sizeRef.current));
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);
  const [w, h] = extent;
  const W = size.w;
  const H = size.h;
  const f = large ? Math.max(1.3, Math.min(1.9, W / 1000)) : 1;
  const stations = Object.entries(geometry?.stations ?? {}).map(([s, p]) => ({ index: Number(s), ...p }));
  const rectOf = (i: number) => boxes.find((b) => b.index === i)?.rect ?? null;

  // The projection fitted to the floor and the stations, with a small margin
  const { P, depth } = useMemo(() => {
    const fit = roomFit(cam, extent, stations.map((st) => [st.x_mm, st.y_mm, st.height_mm]), size, insets, large);
    const L = lens(cam);
    const P = (x: number, y: number, z = 0): Point => roomProject(cam, fit, zoom, size, x, y, z);
    // Near things full, the farthest a little fainter
    const depth = (x: number, y: number, z = 0) => 1 - 0.45 * Math.max(0, Math.min(1, (L(x, y, z)[2] - fit.dMin) / fit.dSpan));
    return { P, depth };
  }, [cam, zoom, w, h, JSON.stringify(geometry), W, H, insets.top, insets.bottom, large]);

  const floor = [P(0, 0), P(w, 0), P(w, h), P(0, h)];
  const two = boxes.length === 2 ? boxes : null;
  const shared = !!two && two[0].rect.join() === two[1].rect.join();
  const line = two && !shared ? handover(two[0].rect, two[1].rect) : null;
  const fog = mode === "error" && coverage?.fog ? coverage.fog : null;
  const fogUrl = useMemo(() => (fog && coverage ? fogImage(fog, coverage.limit_mm, light) : null), [fog, coverage?.limit_mm, light]);
  const fix = mode === "fix" ? fixImageCached(boxes, extent) : null;
  // The floor plane is affine under the projection: an image laid on it is one matrix
  const onFloor = (origin: Point) => {
    const o = P(origin[0], origin[1]);
    const ex = P(origin[0] + 1, origin[1]);
    const ey = P(origin[0], origin[1] + 1);
    return `matrix(${ex[0] - o[0]} ${ex[1] - o[1]} ${ey[0] - o[0]} ${ey[1] - o[1]} ${o[0]} ${o[1]})`;
  };
  const apart = Object.entries(geometry?.apart_mm ?? {})[0];
  const sel = (k: string) => (props.selected ?? []).includes(k);
  const have = (b: UnifiedBot) => !!shownId && heldCalibrationId(b).toLowerCase() === shownId.toLowerCase();
  const located = bots.filter((b) => b.position);

  // --- the grid: a faint context beyond the floor, a finer one on it ------------
  const step = contextStep(extent);
  const [gx0, gy0, gx1, gy1] = contextBounds(extent, stations.map((s) => [s.x_mm, s.y_mm] as Point), step);
  const gridLines: React.ReactNode[] = [];
  for (let x = gx0; x <= gx1; x += step) {
    const a = P(x, gy0);
    const b = P(x, gy1);
    gridLines.push(<line key={`gx${x}`} x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} strokeOpacity={(x % 1000 === 0 ? 0.26 : 0.16) * depth(x, (gy0 + gy1) / 2)} />);
  }
  for (let y = gy0; y <= gy1; y += step) {
    const a = P(gx0, y);
    const b = P(gx1, y);
    gridLines.push(<line key={`gy${y}`} x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} strokeOpacity={(y % 1000 === 0 ? 0.26 : 0.16) * depth((gx0 + gx1) / 2, y)} />);
  }
  const o0 = P(0, 0);
  const o1 = P(1000, 0);
  const fine = floorStep(Math.hypot(o1[0] - o0[0], o1[1] - o0[1]) / 1000, extent);
  const floorLines: React.ReactNode[] = [];
  for (let x = fine; x < w; x += fine) floorLines.push(<line key={`fx${x}`} x1={P(x, 0)[0]} y1={P(x, 0)[1]} x2={P(x, h)[0]} y2={P(x, h)[1]} />);
  for (let y = fine; y < h; y += fine) floorLines.push(<line key={`fy${y}`} x1={P(0, y)[0]} y1={P(0, y)[1]} x2={P(w, y)[0]} y2={P(w, y)[1]} />);

  // --- labels, placed so none covers another or a robot ---------------------
  const wants: (Want & { draw: (x: number, y: number) => React.ReactNode })[] = [];
  const obstacles: Box4[] = [];
  const text = (key: string, at: Point, s: string, size: number, prio: number, opts: { must?: boolean; mono?: boolean; bold?: boolean; fill?: string; opacity?: number; gap?: number } = {}) => {
    const tw = textW(s, size, opts.mono, opts.bold);
    wants.push({
      key,
      at,
      w: tw,
      h: size * 1.25,
      prio,
      must: !!opts.must,
      gap: opts.gap ?? 6,
      draw: (x, y) => (
        <text
          key={key}
          x={x}
          y={y + size * 0.95}
          fontSize={size}
          fontWeight={opts.bold ? 700 : undefined}
          fontFamily={opts.mono ? "var(--font-mono)" : undefined}
          fill={opts.fill}
          opacity={opts.opacity}
          className="halo"
          data-testid={`room-label-${key}`}
        >
          {s}
        </text>
      ),
    });
  };

  // Metre ticks along the two floor edges nearest the viewer
  const tick = Math.max(w, h) >= 2500 ? 1000 : 500;
  const L0 = lens(cam);
  const nearY = L0(w / 2, 0)[2] < L0(w / 2, h)[2] ? 0 : h;
  const nearX = L0(0, h / 2)[2] < L0(w, h / 2)[2] ? 0 : w;
  const mid = P(w / 2, h / 2);
  const outward = (p: Point, by: number): Point => {
    const d = Math.hypot(p[0] - mid[0], p[1] - mid[1]) || 1;
    return [p[0] + ((p[0] - mid[0]) / d) * by, p[1] + ((p[1] - mid[1]) / d) * by];
  };
  const metre = (mm: number) => (mm === 0 ? "0" : mm % 1000 === 0 ? `${mm / 1000} m` : `${mm / 1000}`);
  const ticks: React.ReactNode[] = [];
  for (let x = 0; x <= w; x += tick) {
    const p = P(x, nearY);
    const q = outward(p, 7 * f);
    ticks.push(<line key={`tx${x}`} x1={p[0]} y1={p[1]} x2={q[0]} y2={q[1]} />);
    text(`tick-x-${x}`, outward(p, 14 * f), metre(x), 10 * f, 7, { fill: "var(--muted)", gap: 2 });
  }
  for (let y = tick; y <= h; y += tick) {
    const p = P(nearX, y);
    const q = outward(p, 7 * f);
    ticks.push(<line key={`ty${y}`} x1={p[0]} y1={p[1]} x2={q[0]} y2={q[1]} />);
    text(`tick-y-${y}`, outward(p, 14 * f), metre(y), 10 * f, 7, { fill: "var(--muted)", gap: 2 });
  }

  const o = P(0, 0);
  obstacles.push([o[0] - 7, o[1] - 7, o[0] + 7, o[1] + 7]);
  text("origin", o, "origin", 11 * f, 3, { must: true, bold: true, gap: 9 });

  doc.areas.forEach((a) => {
    const col = areaColor({ ...a, role: a.role ?? undefined }, doc.areas.map((x) => ({ ...x, role: x.role ?? undefined })));
    text(`area-${a.key}`, P(a.x + a.w / 2, a.y + a.h), a.name, 10.5 * f, 4, { fill: col, gap: 4 });
  });

  if (sel("anchor")) doc.anchor_spots.forEach((sp, i) => text(`spot-${i}`, P(sp.at[0], sp.at[1]), `spot ${i + 1} · ${sp.error_mm.toFixed(1)} mm`, 10 * f, 3, { must: true, fill: "var(--accent)", gap: 8 }));

  if (mode === "fix" && line) {
    // The label stays off its own line
    for (let k = 0; k <= 16; k++) {
      const q = P(line.from[0] + ((line.to[0] - line.from[0]) * k) / 16, line.from[1] + ((line.to[1] - line.from[1]) * k) / 16);
      obstacles.push([q[0] - 3, q[1] - 3, q[0] + 3, q[1] + 3]);
    }
    const at = P((line.from[0] + line.to[0]) / 2, (line.from[1] + line.to[1]) / 2);
    text("handover", at, switchLabel(line), 11 * f, 2, { must: true, bold: true, mono: true, gap: 8 });
    const band = two ? overlapBand(two[0].rect, two[1].rect) : null;
    if (band) text("band", P((band[0] + band[2]) / 2, band[1] + (band[3] - band[1]) * 0.2), "both allowed", 10.5 * f, 2, { must: true, gap: 4 });
  }

  const robotR = 4.5 * f;
  located.forEach((b) => {
    const p = P(b.position!.x, b.position!.y);
    obstacles.push([p[0] - robotR - 1, p[1] - robotR - 1, p[0] + robotR + 1, p[1] + robotR + 1]);
    if (located.length <= 50) text(`robot-${b.id}`, p, b.id.slice(-4).toUpperCase(), 9.5 * f, 5, { mono: true, bold: large, fill: large ? "var(--text)" : "var(--muted)", gap: robotR + 2 });
  });

  const cards: (Want & { draw: (x: number, y: number) => React.ReactNode })[] = [];
  stations.forEach((st) => {
    const top = P(st.x_mm, st.y_mm, st.height_mm);
    obstacles.push([top[0] - 8, top[1] - 8, top[0] + 8, top[1] + 8]);
    const hue = `var(--st-${st.index % 2})`;
    const fit = stationFit?.[st.index];
    const s = stationLabel(st.index, st.height_mm, fit);
    const size = 11.5 * f;
    const cw = textW(s, size, false, true) + 14 * f;
    const ch = size * 1.9;
    cards.push({
      key: `station-${st.index}`,
      at: top,
      w: cw,
      h: ch,
      prio: 1,
      must: true,
      gap: 12,
      draw: (x, y) => (
        <g key={`card-${st.index}`} data-testid={`room-card-${st.index}`}>
          <title>
            S{st.index} stands about ({Math.round(st.x_mm)}, {Math.round(st.y_mm)}) mm, {(st.height_mm / 1000).toFixed(1)} m up: estimated, not to tape
          </title>
          <rect x={x} y={y} width={cw} height={ch} rx={6} fill="var(--surface)" stroke={hue} strokeWidth={1.4} />
          <text x={x + 7 * f} y={y + ch / 2 + size * 0.36} fontSize={size} fontWeight={600}>
            <tspan fill={hue} fontWeight={700}>
              S{st.index}
            </tspan>
            {s.slice(`S${st.index}`.length)}
          </text>
        </g>
      ),
    });
    // Height ticks on the pole, labelled at each whole metre
    for (let z = 500; z < st.height_mm; z += 500) {
      if (z % 1000 === 0) text(`pole-${st.index}-${z}`, P(st.x_mm, st.y_mm, z), `${z / 1000} m`, 9 * f, 8, { fill: hue, gap: 7 });
    }
  });
  if (apart && stations.length === 2) {
    const a = P(stations[0].x_mm, stations[0].y_mm, stations[0].height_mm);
    const b = P(stations[1].x_mm, stations[1].y_mm, stations[1].height_mm);
    text("apart", [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2], `${(apart[1] / 1000).toFixed(1)} m apart`, 10 * f, 6, { fill: "var(--muted)", gap: 4 });
  }
  const all = [...cards, ...wants];
  const places = placeLabels(all, obstacles, [4, topInset + 4, W - 4, H - insets.bottom - 4]);

  const local = (e: React.PointerEvent<SVGSVGElement>): Point => {
    const r = e.currentTarget.getBoundingClientRect();
    return [e.clientX - r.left, e.clientY - r.top];
  };
  const twoFingers = () => {
    const [a, b] = [...pointers.current.values()];
    return { dist: Math.hypot(a[0] - b[0], a[1] - b[1]) || 1, mid: [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2] as Point };
  };
  const onDown = (e: React.PointerEvent<SVGSVGElement>) => {
    props.onGrab?.();
    pointers.current.set(e.pointerId, local(e));
    try {
      (e.currentTarget as SVGSVGElement).setPointerCapture(e.pointerId);
    } catch {
      // a synthetic pointer has nothing to capture
    }
    if (pointers.current.size === 2) {
      drag.current = null;
      pinch.current = { ...twoFingers(), zoom };
      return;
    }
    drag.current = { x: e.clientX, y: e.clientY, cam, zoom, pan: e.shiftKey || e.button === 2 };
  };
  const onMove = (e: React.PointerEvent<SVGSVGElement>) => {
    if (pointers.current.has(e.pointerId)) pointers.current.set(e.pointerId, local(e));
    if (pinch.current && pointers.current.size === 2) {
      const now = twoFingers();
      const start = pinch.current;
      const z = zoomAt(start.zoom, now.dist / start.dist, start.mid, size);
      onZoom({ ...z, tx: z.tx + now.mid[0] - start.mid[0], ty: z.ty + now.mid[1] - start.mid[1] });
      return;
    }
    if (!drag.current) return;
    const d = drag.current;
    const dx = e.clientX - d.x;
    const dy = e.clientY - d.y;
    if (d.pan) onZoom({ ...d.zoom, tx: d.zoom.tx + dx, ty: d.zoom.ty + dy });
    else if (Math.hypot(dx, dy) > 2) onCam({ az: d.cam.az - dx * 0.35, el: clampEl(d.cam.el + dy * 0.3) });
  };
  const onUp = (e: React.PointerEvent<SVGSVGElement>) => {
    pointers.current.delete(e.pointerId);
    if (pointers.current.size < 2) pinch.current = null;
    drag.current = null;
  };

  return (
    <div className={`room${large ? " large" : ""}`} data-testid="room-view">
      <div ref={holder} className="room-canvas">
        <svg
          width={W}
          height={H}
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          aria-label={`The site: extent ${w} by ${h} mm, ${stations.length} station${stations.length === 1 ? "" : "s"}, ${bots.length} robot${bots.length === 1 ? "" : "s"}`}
          onPointerDown={onDown}
          onPointerMove={onMove}
          onPointerUp={onUp}
          onPointerCancel={onUp}
          onDoubleClick={props.onHome}
          onContextMenu={(e) => e.preventDefault()}
          style={{ cursor: drag.current ? "grabbing" : "grab", touchAction: "none" }}
        >
          <defs>
            <pattern id="room-hatch" patternUnits="userSpaceOnUse" width="7" height="7" patternTransform="rotate(45)">
              <line x1="0" y1="0" x2="0" y2="7" stroke="var(--muted)" strokeWidth="1.2" opacity="0.55" />
            </pattern>
          </defs>
          <g data-testid="room-grid" stroke="var(--muted)" strokeWidth={1}>
            {gridLines}
          </g>
          {/* the floor */}
          <polygon
            data-testid="room-floor"
            data-selected={sel("floor") || undefined}
            points={poly(floor)}
            fill={FLOOR_FILL}
            stroke={sel("floor") ? "var(--accent)" : "var(--muted)"}
            strokeWidth={sel("floor") ? 2.6 : 1.4}
          />
          <g data-testid="room-floor-grid" stroke="var(--grid)" strokeWidth={1}>
            {floorLines}
          </g>
          <g stroke="var(--muted)" strokeWidth={1.2}>
            {ticks}
          </g>
          {/* coverage, tinted as the plan tints it */}
          {fix && <image href={fix.url} x={0} y={0} width={fix.w} height={fix.h} preserveAspectRatio="none" transform={onFloor([0, 0])} style={{ imageRendering: "pixelated" }} data-testid="room-fix" />}
          {mode === "fix" &&
            boxes.map((b) => (
              <polygon
                key={`c-${b.index}`}
                points={poly([P(b.rect[0], b.rect[1]), P(b.rect[2], b.rect[1]), P(b.rect[2], b.rect[3]), P(b.rect[0], b.rect[3])])}
                fill={fix ? "none" : `var(--st-${b.index % 2})`}
                fillOpacity={shared ? 0.14 : 0.22}
                stroke={`var(--st-${b.index % 2})`}
                strokeOpacity={0.75}
                strokeWidth={1.3}
                data-testid={`room-cover-${b.index}`}
              />
            ))}
          {fogUrl && fog && <image href={fogUrl} x={0} y={0} width={fog.cols * fog.cell_mm} height={fog.rows * fog.cell_mm} preserveAspectRatio="none" transform={onFloor(fog.origin)} style={{ imageRendering: "pixelated" }} opacity={0.85} />}
          {/* areas */}
          {doc.areas.map((a) => {
            const col = areaColor({ ...a, role: a.role ?? undefined }, doc.areas.map((x) => ({ ...x, role: x.role ?? undefined })));
            const ps = [P(a.x, a.y), P(a.x + a.w, a.y), P(a.x + a.w, a.y + a.h), P(a.x, a.y + a.h)];
            const on = sel(a.key) || sel("areas");
            return <polygon key={a.key} data-testid={`room-area-${a.name}`} points={poly(ps)} fill={on ? `color-mix(in srgb, ${col} 18%, transparent)` : "none"} stroke={col} strokeWidth={on ? 2.2 : 1.3} strokeDasharray="5 3" />;
          })}
          {/* walls, obstacles and objects, flat on the floor */}
          {doc.walls.map((b) => {
            const on = sel(b.key) || sel("walls");
            return <polyline key={b.key} data-testid="room-wall" points={poly(b.points.map((q) => P(q[0], q[1])))} fill="none" stroke={on ? "var(--accent)" : "var(--text)"} strokeWidth={on ? 3.2 : 2.2} strokeLinecap="round" strokeLinejoin="round" />;
          })}
          {doc.obstacles.map((b) => {
            const on = sel(b.key) || sel("walls");
            return <polygon key={b.key} data-testid="room-obstacle" points={poly(b.points.map((q) => P(q[0], q[1])))} fill="color-mix(in srgb, var(--text) 18%, transparent)" stroke={on ? "var(--accent)" : "var(--text)"} strokeWidth={on ? 3 : 2} strokeLinejoin="round" />;
          })}
          {doc.objects.map((o) => {
            const on = sel(o.key) || sel("objects");
            const ps = [P(o.x - 60, o.y - 60), P(o.x + 60, o.y - 60), P(o.x + 60, o.y + 60), P(o.x - 60, o.y + 60)];
            return <polygon key={o.key} data-testid="room-object" points={poly(ps)} fill="var(--elevated)" stroke={on ? "var(--accent)" : "var(--muted)"} strokeWidth={on ? 2.2 : 1.2} />;
          })}
          {(sel("anchor") ? doc.anchor_spots : []).map((sp, i) => {
            const c = P(sp.at[0], sp.at[1]);
            const ring = Array.from({ length: 16 }, (_, k) => P(sp.at[0] + 45 * Math.cos((k / 16) * 2 * Math.PI), sp.at[1] + 45 * Math.sin((k / 16) * 2 * Math.PI)));
            return (
              <g key={`spot-${i}`} data-testid="room-anchor-spot">
                <polygon points={poly(ring)} fill="none" stroke="var(--accent)" strokeWidth={2} />
                <circle cx={c[0]} cy={c[1]} r={2} fill="var(--accent)" />
              </g>
            );
          })}
          {/* handover */}
          {mode === "fix" && line && (
            <line data-testid="room-handover" x1={P(...line.from)[0]} y1={P(...line.from)[1]} x2={P(...line.to)[0]} y2={P(...line.to)[1]} stroke="var(--text)" strokeWidth={2} strokeDasharray="7 4" />
          )}
          {/* origin and axes */}
          {(() => {
            const ax = P(Math.min(250, w / 3), 0);
            const ay = P(0, Math.min(250, h / 3));
            return (
              <g>
                <line x1={o[0]} y1={o[1]} x2={ax[0]} y2={ax[1]} stroke="var(--text)" strokeWidth={1.8} />
                <line x1={o[0]} y1={o[1]} x2={ay[0]} y2={ay[1]} stroke="var(--text)" strokeWidth={1.8} />
                <text x={ax[0] + 4} y={ax[1] + 4} fontSize={10 * f} className="halo">
                  x
                </text>
                <text x={ay[0] - 10} y={ay[1] + 4} fontSize={10 * f} className="halo">
                  y
                </text>
                <circle cx={o[0]} cy={o[1]} r={5} fill="var(--canvas)" stroke="var(--text)" strokeWidth={1.6} />
              </g>
            );
          })()}
          {/* each station: its footprint, its rays to its own coverage, its pole */}
          {stations.map((st) => {
            const hue = `var(--st-${st.index % 2})`;
            const top = P(st.x_mm, st.y_mm, st.height_mm);
            const foot = P(st.x_mm, st.y_mm, 0);
            const r = rectOf(st.index);
            const corners: Point[] = r ? [P(r[0], r[1]), P(r[2], r[1]), P(r[2], r[3]), P(r[0], r[3])] : [];
            const raw: [number, number][] = r ? [[r[0], r[1]], [r[2], r[1]], [r[2], r[3]], [r[0], r[3]]] : [];
            const on = picked === st.index || sel("stations");
            const ring = Array.from({ length: 24 }, (_, k) => P(st.x_mm + 70 * Math.cos((k / 24) * 2 * Math.PI), st.y_mm + 70 * Math.sin((k / 24) * 2 * Math.PI)));
            const fade = depth(st.x_mm, st.y_mm, st.height_mm / 2);
            return (
              <g key={`s-${st.index}`} data-testid={`room-rays-${st.index}`}>
                <polygon points={poly(ring)} fill={`color-mix(in srgb, ${hue} 20%, transparent)`} stroke={hue} strokeWidth={1.3} opacity={fade} />
                <line x1={P(st.x_mm - 110, st.y_mm)[0]} y1={P(st.x_mm - 110, st.y_mm)[1]} x2={P(st.x_mm + 110, st.y_mm)[0]} y2={P(st.x_mm + 110, st.y_mm)[1]} stroke={hue} strokeWidth={1} opacity={fade} />
                <line x1={P(st.x_mm, st.y_mm - 110)[0]} y1={P(st.x_mm, st.y_mm - 110)[1]} x2={P(st.x_mm, st.y_mm + 110)[0]} y2={P(st.x_mm, st.y_mm + 110)[1]} stroke={hue} strokeWidth={1} opacity={fade} />
                {corners.map((c, i) => (
                  <line key={i} data-testid={`room-ray-${st.index}`} x1={top[0]} y1={top[1]} x2={c[0]} y2={c[1]} stroke={hue} strokeWidth={on ? 1.6 : 1.1} strokeOpacity={(on ? 0.85 : 0.5) * depth(...raw[i])} />
                ))}
                <line x1={foot[0]} y1={foot[1]} x2={top[0]} y2={top[1]} stroke={hue} strokeDasharray="4 3" strokeWidth={1.6} opacity={fade} />
                {Array.from({ length: Math.floor((st.height_mm - 1) / 500) }, (_, k) => {
                  const z = (k + 1) * 500;
                  const p = P(st.x_mm, st.y_mm, z);
                  const half = (z % 1000 === 0 ? 6 : 3.5) * f;
                  return <line key={z} x1={p[0] - half} y1={p[1]} x2={p[0] + half} y2={p[1]} stroke={hue} strokeWidth={1.3} opacity={fade} />;
                })}
              </g>
            );
          })}
          {apart && stations.length === 2 && (
            <line
              x1={P(stations[0].x_mm, stations[0].y_mm, stations[0].height_mm)[0]}
              y1={P(stations[0].x_mm, stations[0].y_mm, stations[0].height_mm)[1]}
              x2={P(stations[1].x_mm, stations[1].y_mm, stations[1].height_mm)[0]}
              y2={P(stations[1].x_mm, stations[1].y_mm, stations[1].height_mm)[1]}
              stroke="var(--muted)"
              strokeDasharray="2 5"
            />
          )}
          {/* robots */}
          {located.map((b) => {
            const p = P(b.position!.x, b.position!.y);
            const has = have(b);
            const on = props.selectedRobot === b.id || sel("robots");
            return (
              <circle
                key={b.id}
                data-testid="room-robot"
                cx={p[0]}
                cy={p[1]}
                r={on ? robotR + 2 : robotR}
                fill={has ? "var(--text)" : "var(--canvas)"}
                stroke={on ? "var(--accent)" : "var(--text)"}
                strokeWidth={on ? 2.5 : 1.5}
                onPointerDown={(e) => e.stopPropagation()}
                onClick={(e) => (e.stopPropagation(), props.onSelectRobot?.(on ? null : b.id))}
                style={{ cursor: props.onSelectRobot ? "pointer" : undefined }}
              >
                <title>…{b.id.slice(-6).toUpperCase()}</title>
              </circle>
            );
          })}
          {/* the stations themselves: a dot at the top of each pole */}
          {stations.map((st) => {
            const top = P(st.x_mm, st.y_mm, st.height_mm);
            const on = picked === st.index || sel("stations");
            return (
              <g key={st.index} data-testid={`room-station-${st.index}`} onPointerDown={(e) => e.stopPropagation()} onClick={(e) => (e.stopPropagation(), pick(on ? null : st.index))} style={{ cursor: "pointer" }}>
                <circle cx={top[0]} cy={top[1]} r={(on ? 8 : 6.5) * Math.min(f, 1.4)} fill={`var(--st-${st.index % 2})`} stroke={on ? "var(--text)" : "var(--canvas)"} strokeWidth={1.5} />
                <title>
                  S{st.index} stands about ({Math.round(st.x_mm)}, {Math.round(st.y_mm)}) mm, {(st.height_mm / 1000).toFixed(1)} m up: estimated, not to tape
                </title>
              </g>
            );
          })}
          {/* the origin's hit area, over the rays and the floor */}
          {props.onOrigin && (
            <circle
              data-testid="room-origin"
              cx={o[0]}
              cy={o[1]}
              r={10}
              fill="transparent"
              style={{ cursor: "pointer", pointerEvents: "all" }}
              onPointerDown={(e) => e.stopPropagation()}
              onClick={(e) => (e.stopPropagation(), props.onOrigin?.())}
            >
              <title>{ORIGIN_HINT}</title>
            </circle>
          )}
          {/* labels last, over everything */}
          {all.map((l) => {
            const at = places.get(l.key);
            return at ? l.draw(at[0], at[1]) : null;
          })}
        </svg>
      </div>
      <div className="float room-legend" data-testid="room-legend">
        {mode === "fix" ? (
          <>
            {boxes.map((b) => (
              <span key={b.index} className="row">
                <span className="lsw" style={{ background: `color-mix(in srgb, var(--st-${b.index % 2}) 45%, transparent)` }} />S{b.index} covers
              </span>
            ))}
            <span className="row" data-testid="room-coverage-note">
              {coverageNote}
            </span>
          </>
        ) : (
          <span className="row">accuracy: darker is worse, amber passes the {coverage?.limit_mm ?? 2} mm limit</span>
        )}
        <span className="row muted">
          {shownName ? `${shownName} · ` : ""}
          extent {(w / 1000).toFixed(2)} × {(h / 1000).toFixed(2)} m · {stations.length ? "stations estimated, about ±10 cm" : "no station geometry for this calibration"}
        </span>
      </div>
    </div>
  );
};

/** The view presets and, in 3D, the zoom: one group over the map, in both
 * the 3D view and the top-down edit. */
export const MapPresets: React.FC<{
  /** The camera, or null while editing top-down. */
  cam: RoomCam | null;
  onPreset: (cam: RoomCam) => void;
  zoom?: { fit: boolean; onIn: () => void; onOut: () => void; onFit: () => void };
  /** On a second row, under the kinds bar, when the two do not fit side by side. */
  below?: boolean;
}> = ({ cam, onPreset, zoom, below }) => {
  const on = cam ? presetOf(cam) : "top";
  return (
    <div className={`float mapbar${below ? " below" : ""}`} data-testid="map-presets">
      <span className="seg presets" role="group" aria-label="View from">
        {PRESETS.map((p) => (
          <button
            key={p.key}
            type="button"
            className={on === p.key ? "on" : undefined}
            aria-pressed={on === p.key}
            onClick={() => onPreset(p.cam)}
            title={`${p.label === "3/4" ? "The corner view, three quarters up (or double-click the map)" : `From the ${p.label.toLowerCase()}`}; drag to orbit, Shift-drag or right-drag to pan, wheel or pinch to zoom`}
          >
            {p.label}
          </button>
        ))}
      </span>
      {zoom && (
        <span className="seg presets" role="group" aria-label="Zoom">
          <button type="button" onClick={zoom.onOut} aria-label="Zoom out" title="Zoom out (or the wheel)">
            −
          </button>
          <button type="button" onClick={zoom.onIn} aria-label="Zoom in" title="Zoom in (or the wheel)">
            +
          </button>
          <button type="button" className={zoom.fit ? "on" : undefined} onClick={zoom.onFit} title="Fit the extent and the stations" data-testid="room-fit">
            Fit
          </button>
        </span>
      )}
    </div>
  );
};
