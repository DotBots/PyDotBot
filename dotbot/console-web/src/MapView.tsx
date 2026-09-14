import React, { useCallback, useMemo, useRef, useState } from "react";

import { CalibrationLayer } from "./CalibrationLayer";
import { areaToFraction, fractionToArea } from "./frame";
import {
  axisTicks,
  gridStepMm as pickGridStep,
  gridSubStepMm as pickSubStep,
  metreLabel,
  pxPerMm,
  rulerStepMm as pickRulerStep,
} from "./grid";
import { BotGlyph, botFootprintPx, glyphBoxPx, glyphLevel } from "./BotGlyph";
import { ResetBadge, batteryColor, batteryPct, stateColor } from "./viewChrome";

import { Area, CalibrationSession, LH2Position, Site, UnifiedBot } from "./types";
import { useSmoothPositions } from "./useSmoothPositions";
import {
  Camera,
  SITE_ZOOM,
  ViewGeom,
  ZOOM_MIN,
  clampCam,
  viewGeom,
  zoomMax,
  zoomNames,
} from "./zoom";

export type { Camera, ViewGeom } from "./zoom";
export { clampCam } from "./zoom";

// Layer set mirrors the v1 design (Battery Bars / Waypoints / HotSpots /
// DotBots); Trails is our addition on top.
export interface Layers {
  batteryBars: boolean;
  waypoints: boolean;
  hotSpots: boolean;
  dotBots: boolean;
  crashedOnly: boolean;
  trails: boolean;
}

interface MapViewProps {
  bots: UnifiedBot[];
  // The part of the frame the map draws: the whole site plus a margin.
  viewport: Area;
  // Every area of the site, drawn as an outline with its name.
  siteAreas: Area[];
  // The area names this browser hides, ticked under Layers > Areas.
  hiddenAreas: Set<string>;
  // The whole site, outlined so it reads as a box rather than only a label.
  siteExtent: Area | null;
  selection: Set<string>;
  layers: Layers;
  plannedMissions: { waypoints: LH2Position[]; led: string | null }[]; // local queues, not yet sent
  cam: Camera;
  setCam: React.Dispatch<React.SetStateAction<Camera>>;
  onGeom: (g: ViewGeom) => void;
  onSelect: (ids: string[], mode: "replace" | "toggle" | "add") => void;
  onAddWaypoint: (p: LH2Position) => void;
  // Calibration mode: the rectangle being calibrated, drawn over the map.
  // While it is open, clicking a robot chooses it as the capturer.
  session?: CalibrationSession | null;
  onPickCapturer?: (id: string) => void;
  // The named zooms: the site the menu lists, and what a pick applies to.
  site: Site | null;
  onZoom: (name: string) => void;
}

// How much canvas a ruler label needs beside it to be readable whole.
const RULER_CLEAR_PX = 40;
// The zoom controls sit in the bottom-left corner, where the ruler's own
// column runs, so it gives up that much of the canvas to them.
const RULER_CONTROLS_PX = 110;

const ledCss = (b: UnifiedBot) =>
  b.led ? `rgb(${b.led.red},${b.led.green},${b.led.blue})` : "var(--s-Inactive)";



export const MapView: React.FC<MapViewProps> = (props) => {
  const wrapRef = useRef<HTMLDivElement>(null);
  const { cam, setCam } = props;
  const [marquee, setMarquee] = useState<{ x0: number; y0: number; x1: number; y1: number } | null>(null);
  const [hoverId, setHoverId] = useState<string | null>(null);
  const [zoomOpen, setZoomOpen] = useState(false);
  const panRef = useRef<{ x0: number; y0: number; tx0: number; ty0: number; moved: boolean } | null>(null);
  const marqueeRef = useRef<{ additive: boolean } | null>(null);
  const geomRef = useRef<ViewGeom>(viewGeom(1000, 600, props.viewport));

  const mapDiagonal = Math.hypot(props.viewport.w, props.viewport.h);
  const smoothPositions = useSmoothPositions(props.bots, mapDiagonal);

  const [box, setBox] = useState(() => viewGeom(1000, 600, props.viewport));
  const onGeomRef = useRef(props.onGeom);
  onGeomRef.current = props.onGeom;
  const viewportRef = useRef(props.viewport);
  viewportRef.current = props.viewport;
  // Track the canvas size live (rail open/close, window resize): the arena
  // keeps its margins instead of overflowing when the canvas shrinks.
  const measure = useCallback((el: HTMLDivElement | null) => {
    (wrapRef as React.MutableRefObject<HTMLDivElement | null>).current = el;
  }, []);
  React.useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const update = () => {
      const r = el.getBoundingClientRect();
      const g = viewGeom(r.width, r.height, viewportRef.current);
      setBox(g);
      geomRef.current = g;
      onGeomRef.current(g);
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
    // The viewport's extent decides the box's aspect, so a site that arrives
    // after the first measure has to re-run it.
  }, [props.viewport.w, props.viewport.h]);
  const boxW = box.boxW;
  const boxH = box.boxH;

  const pctPos = (p: LH2Position) => {
    const { fx, fy } = areaToFraction(p, props.viewport);
    return { left: fx * 100, top: fy * 100 };
  };

  // One area as a percentage box of the viewport, so it lands in the same
  // coordinate space as the bots.
  const pctArea = (a: Area) => {
    const tl = areaToFraction({ x: a.x, y: a.y }, props.viewport);
    const br = areaToFraction({ x: a.x + a.w, y: a.y + a.h }, props.viewport);
    return {
      left: `${tl.fx * 100}%`,
      top: `${tl.fy * 100}%`,
      width: `${(br.fx - tl.fx) * 100}%`,
      height: `${(br.fy - tl.fy) * 100}%`,
    };
  };

  // The same box in the drawn box's own pixels, for the SVG outlines.
  const rectPx = (a: Area) => {
    const tl = areaToFraction({ x: a.x, y: a.y }, props.viewport);
    const br = areaToFraction({ x: a.x + a.w, y: a.y + a.h }, props.viewport);
    return {
      x: tl.fx * boxW,
      y: tl.fy * boxH,
      width: (br.fx - tl.fx) * boxW,
      height: (br.fy - tl.fy) * boxH,
    };
  };

  const drawnAreas = props.siteAreas.filter(
    (a) => !props.hiddenAreas.has(a.name ?? ""),
  );
  // Areas that share a top-left corner would print their names on top of one
  // another, so each one after the first drops a line.
  const stackedAt = (index: number) =>
    drawnAreas.filter(
      (o, j) =>
        j < index &&
        o.x === drawnAreas[index].x &&
        o.y === drawnAreas[index].y,
    ).length;

  const pxToMm = (clientX: number, clientY: number): LH2Position | null => {
    const el = wrapRef.current;
    if (!el) return null;
    const r = el.getBoundingClientRect();
    const cx = r.left + r.width / 2;
    const cy = r.top + r.height / 2;
    const ux = (clientX - cx - cam.tx) / cam.scale + r.width / 2;
    const uy = (clientY - cy - cam.ty) / cam.scale + r.height / 2;
    const ax = ux - (r.width - boxW) / 2;
    const ay = uy - (r.height - boxH) / 2;
    const { x, y } = fractionToArea(ax / boxW, ay / boxH, props.viewport);
    const { x: x0, y: y0, w, h } = props.viewport;
    if (x < x0 || y < y0 || x > x0 + w || y > y0 + h) return null;
    return { x: Math.round(x), y: Math.round(y) };
  };

  // v1 canvas semantics: alt-click = waypoint, shift-drag = marquee,
  // plain drag = pan, plain click (no movement) = clear selection.
  const onCanvasDown = (e: React.PointerEvent) => {
    if (e.button !== 0) return;
    setZoomOpen(false);
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    if (e.altKey) {
      const p = pxToMm(e.clientX, e.clientY);
      if (p) props.onAddWaypoint(p);
      return;
    }
    if (e.shiftKey) {
      marqueeRef.current = { additive: true };
      setMarquee({ x0: e.clientX, y0: e.clientY, x1: e.clientX, y1: e.clientY });
      return;
    }
    panRef.current = { x0: e.clientX, y0: e.clientY, tx0: cam.tx, ty0: cam.ty, moved: false };
  };

  const onCanvasMove = (e: React.PointerEvent) => {
    if (panRef.current) {
      const p = panRef.current;
      const dx = e.clientX - p.x0;
      const dy = e.clientY - p.y0;
      if (Math.abs(dx) + Math.abs(dy) > 3) p.moved = true;
      setCam((c) => clampCam({ ...c, tx: p.tx0 + dx, ty: p.ty0 + dy }, geomRef.current));
      return;
    }
    if (marqueeRef.current) setMarquee((m) => (m ? { ...m, x1: e.clientX, y1: e.clientY } : m));
  };

  const onCanvasUp = () => {
    if (panRef.current) {
      const moved = panRef.current.moved;
      panRef.current = null;
      if (!moved) props.onSelect([], "replace"); // plain click on empty canvas clears
      return;
    }
    if (!marqueeRef.current || !marquee) {
      marqueeRef.current = null;
      setMarquee(null);
      return;
    }
    const x0 = Math.min(marquee.x0, marquee.x1);
    const x1 = Math.max(marquee.x0, marquee.x1);
    const y0 = Math.min(marquee.y0, marquee.y1);
    const y1 = Math.max(marquee.y0, marquee.y1);
    if (x1 - x0 >= 5 || y1 - y0 >= 5) {
      const hits = props.bots
        .filter((b) => {
          if (!b.position) return false;
          const el = document.getElementById(`bot-${b.id}`);
          if (!el) return false;
          const r = el.getBoundingClientRect();
          const cx = r.left + r.width / 2;
          const cy = r.top + r.height / 2;
          return cx >= x0 && cx <= x1 && cy >= y0 && cy <= y1;
        })
        .map((b) => b.id);
      props.onSelect(hits, "add");
    }
    marqueeRef.current = null;
    setMarquee(null);
  };

  // The camera scales the whole layer, so a name or a badge would grow with
  // the zoom. Chrome is not an object on the floor: it keeps its size.
  const chrome = 1 / cam.scale;

  // The metric grid, in the scaled layer's own units. Both axes span a
  // millimetre in the same pixels, so one step serves them both; a line is one
  // screen pixel wide whatever the camera does.
  const geomNow = geomRef.current;
  const perMm = pxPerMm("x", props.viewport, geomNow, cam);
  const gridStepMm = useMemo(() => pickGridStep(perMm), [perMm]);
  const subStepMm = useMemo(() => pickSubStep(perMm), [perMm]);
  // The grid lies on the site, so a site with no measured extent falls back to
  // the whole drawn frame rather than losing its grid.
  const gridBox = props.siteExtent ?? props.viewport;
  const gridBg = useMemo(() => {
    // The tiles are phased so a line falls on the frame's zero, not on the
    // box's own corner: the steps mean metres from the site's anchor.
    const zeroX = ((0 - gridBox.x) / props.viewport.w) * boxW;
    const zeroY = ((0 - gridBox.y) / props.viewport.h) * boxH;
    const lines = (stepMm: number, color: string) => ({
      image:
        `linear-gradient(90deg, ${color} 0 ${chrome}px, transparent ${chrome}px 100%),` +
        `linear-gradient(180deg, ${color} 0 ${chrome}px, transparent ${chrome}px 100%)`,
      size:
        `${(stepMm / props.viewport.w) * boxW}px 100%,` +
        `100% ${(stepMm / props.viewport.h) * boxH}px`,
      position: `${zeroX}px 0, 0 ${zeroY}px`,
    });
    // The metre lines are listed first, so they paint over the sub-grid where
    // the two coincide and keep their own weight.
    const layers = [lines(gridStepMm, "var(--grid)")];
    if (subStepMm) layers.push(lines(subStepMm, "var(--grid-sub)"));
    return {
      backgroundImage: layers.map((l) => l.image).join(","),
      backgroundSize: layers.map((l) => l.size).join(","),
      backgroundPosition: layers.map((l) => l.position).join(","),
    } as const;
  }, [
    gridStepMm,
    subStepMm,
    props.viewport,
    gridBox.x,
    gridBox.y,
    boxW,
    boxH,
    chrome,
  ]);

  // The ruler names the lines the grid draws: the same step, or a multiple of
  // it where the labels would not fit, so a number always sits on a line. A
  // label too close to an edge is dropped rather than printed half off the
  // canvas or over the other axis.
  const rulerStep = pickRulerStep(gridStepMm, perMm);
  const readable = (ticks: ReturnType<typeof axisTicks>, last: number) =>
    ticks.filter((t) => t.px > RULER_CLEAR_PX && t.px < last);
  const rulerX = readable(
    axisTicks("x", props.viewport, geomNow, cam, rulerStep),
    geomNow.w - RULER_CLEAR_PX,
  );
  const rulerY = readable(
    axisTicks("y", props.viewport, geomNow, cam, rulerStep),
    geomNow.h - RULER_CONTROLS_PX,
  );

  // The robot is an object on the floor, so it is drawn at the floor's own
  // scale: zooming in tells the truth about how much room it takes. Zooming
  // out floors it at a size that can still be seen and clicked.
  const footprintPx = botFootprintPx(perMm);
  const glyphPx = glyphBoxPx(footprintPx);
  // How much of the robot is worth drawing at that size, with the fleet's own
  // size as the tie-breaker.
  const level = glyphLevel(footprintPx, props.bots.length);
  // What sits around the robot - selection, badges, labels - is chrome, and
  // keeps its size on screen whatever the camera does.
  const selectionPx = Math.max(34, footprintPx + 12);
  // What sits on top of the robot shrinks with it, to a floor, so a bot the
  // size of a dot is not buried under its own indicators.
  const drivePx = Math.max(3, Math.min(10, footprintPx * 0.32));
  const batteryPx = Math.max(14, Math.min(28, footprintPx));

  return (
    <div
      ref={measure}
      onPointerDown={onCanvasDown}
      onPointerMove={onCanvasMove}
      onPointerUp={onCanvasUp}
      style={{
        position: "relative",
        flex: 1,
        overflow: "hidden",
        background: "var(--canvas)",
        cursor: panRef.current ? "grabbing" : "default",
        touchAction: "none",
        // Drag surface: a pan or marquee would otherwise smear a text
        // selection across the UI and race the browser's native drag.
        userSelect: "none",
      }}
    >
      {/* camera layer */}
      <div
        data-testid="camera-layer"
        style={{
          position: "absolute",
          inset: 0,
          transform: `translate(${cam.tx}px, ${cam.ty}px) scale(${cam.scale})`,
          transformOrigin: "50% 50%",
        }}
      >
        {/* the drawn frame: the site plus its margin, which draws nothing */}
        <div
          style={{
            position: "absolute",
            left: "50%",
            top: "50%",
            width: boxW,
            height: boxH,
            transform: "translate(-50%, -50%)",
          }}
        >
          {/* the site, which the grid lies on */}
          <div
            data-testid="map-grid"
            style={{
              position: "absolute",
              ...pctArea(gridBox),
              ...gridBg,
              pointerEvents: "none",
            }}
          />

          {/* The outlines: the site as the one outer silhouette, then one
              dashed rectangle per area. Strokes rather than borders, because
              a CSS border under a pixel wide is rounded back up to one and
              then multiplied by the camera; a stroke keeps the width it is
              given, so counter-scaling it holds the hairline at any zoom. */}
          <svg
            width={boxW}
            height={boxH}
            style={{ position: "absolute", inset: 0, pointerEvents: "none" }}
          >
            <rect
              {...rectPx(gridBox)}
              fill="none"
              stroke="var(--muted)"
              strokeWidth={chrome}
            />
            {drawnAreas.map((a) => (
              <rect
                key={`outline-${a.name}`}
                {...rectPx(a)}
                fill="none"
                stroke="var(--muted)"
                strokeWidth={chrome}
                strokeDasharray={`${5 * chrome} ${4 * chrome}`}
                opacity={0.75}
              />
            ))}
          </svg>

          {/* the area names, ticked under Layers > Areas with their outlines */}
          {drawnAreas.map((a, i) => (
              <div
                key={`area-${a.name}`}
                style={{
                  position: "absolute",
                  ...pctArea(a),
                  pointerEvents: "none",
                }}
              >
                {a.name && (
                  <span
                    role="button"
                    title={`Zoom to ${a.name}`}
                    onPointerDown={(e) => {
                      e.stopPropagation();
                      props.onZoom(a.name ?? "");
                    }}
                    style={{
                      position: "absolute",
                      // Offsets are in the scaled layer's units, so they are
                      // divided back out to stay constant on screen.
                      left: 4 * chrome,
                      top: (2 + stackedAt(i) * 12) * chrome,
                      fontSize: 10,
                      opacity: 0.7,
                      whiteSpace: "nowrap",
                      cursor: "pointer",
                      pointerEvents: "auto",
                      transform: `scale(${chrome})`,
                      transformOrigin: "left top",
                    }}
                  >
                    {a.name}
                  </span>
                )}
              </div>
            ))}
          {props.session && (
            <CalibrationLayer
              session={props.session}
              viewport={props.viewport}
              chrome={chrome}
            />
          )}

          {/* trails (our extra layer) */}
          {props.layers.trails && (
            <svg width={boxW} height={boxH} style={{ position: "absolute", inset: 0, pointerEvents: "none" }}>
              {props.bots
                .filter((b) => b.trail.length > 1)
                .map((b) => (
                  <polyline
                    key={b.id}
                    points={b.trail
                      .map((p) => {
                        const { fx, fy } = areaToFraction(p, props.viewport);
                        return `${fx * boxW},${fy * boxH}`;
                      })
                      .join(" ")}
                    fill="none"
                    stroke={ledCss(b)}
                    strokeWidth={1}
                    opacity={0.35}
                  />
                ))}
            </svg>
          )}

          {/* waypoints: per-bot LED-colored diamonds (v1: no connector lines) */}
          {props.layers.waypoints &&
            props.bots.flatMap((b) => {
              if (b.waypoints.length === 0) return [];
              const isSel = props.selection.has(b.id);
              const led = ledCss(b);
              const s = isSel ? 10 : 8;
              return b.waypoints.map((w, i) => {
                const q = pctPos(w);
                return (
                  <div
                    key={`${b.id}-wp-${i}`}
                    style={{
                      position: "absolute",
                      left: `${q.left}%`,
                      top: `${q.top}%`,
                      width: s,
                      height: s,
                      transform: `translate(-50%, -50%) rotate(45deg) scale(${chrome})`,
                      background: isSel ? led : "transparent",
                      border: `1.5px solid ${led}`,
                      opacity: isSel ? 1 : 0.35,
                      boxShadow: isSel ? `0 0 7px ${led}` : "none",
                      pointerEvents: "none",
                    }}
                  />
                );
              });
            })}

          {/* planned (queued, not sent) waypoints */}
          {props.layers.waypoints &&
            props.plannedMissions.flatMap((m, mi) =>
              m.waypoints.map((p, i) => {
              const q = pctPos(p);
              const led = m.led ?? "var(--accent)";
              return (
                <div
                  key={`pend-${mi}-${i}`}
                  style={{
                    position: "absolute",
                    left: `${q.left}%`,
                    top: `${q.top}%`,
                    width: 10,
                    height: 10,
                    transform: `translate(-50%, -50%) rotate(45deg) scale(${chrome})`,
                    background: "transparent",
                    border: `1.5px dashed ${led}`,
                    boxShadow: `0 0 7px ${led}`,
                    pointerEvents: "none",
                  }}
                  title={`waypoint ${i + 1}`}
                />
              );
              }),
            )}

          {/* bots (v1 glyph: state-colored body, LED pip, drive dot, chip label) */}
          {props.layers.dotBots &&
            props.bots
              .filter((b) => b.position)
              .map((b) => {
                const q = pctPos(smoothPositions.get(b.id) ?? b.position!);
                const selected = props.selection.has(b.id);
                const hovered = hoverId === b.id;
                const led = ledCss(b);
                const stc = stateColor(b.state);
                const pct = batteryPct(b);
                const blink = b.state === "Programming" || b.state === "Resetting";
                return (
                  <div
                    key={b.id}
                    id={`bot-${b.id}`}
                    onPointerDown={(e) => {
                      e.stopPropagation();
                      if (e.altKey) {
                        const p = pxToMm(e.clientX, e.clientY);
                        if (p) props.onAddWaypoint(p);
                        return;
                      }
                      if (props.session && props.onPickCapturer) {
                        props.onPickCapturer(b.id);
                        props.onSelect([b.id], "replace");
                      } else if (e.shiftKey || e.metaKey || e.ctrlKey) {
                        props.onSelect([b.id], "toggle");
                      } else if (props.selection.has(b.id) && props.selection.size === 1) {
                        props.onSelect([], "replace"); // click the sole selected bot again = deselect
                      } else {
                        props.onSelect([b.id], "replace");
                      }
                    }}
                    onPointerEnter={() => setHoverId(b.id)}
                    onPointerLeave={() => setHoverId((h) => (h === b.id ? null : h))}
                    style={{
                      position: "absolute",
                      left: `${q.left}%`,
                      top: `${q.top}%`,
                      transform: `translate(-50%, -50%) scale(${chrome})`,
                      cursor: "pointer",
                      zIndex: selected ? 6 : 2,
                      width: 0,
                      height: 0,
                    }}
                  >
                    {/* last-reset warning, centred over the glyph body */}
                    <div
                      style={{
                        position: "absolute",
                        left: "50%",
                        top: "50%",
                        transform: "translate(-50%, -50%)",
                        zIndex: 3,
                      }}
                    >
                      <ResetBadge bot={b} size={13} />
                    </div>
                    {/* selection rectangle */}
                    {selected && (
                      <div
                        style={{
                          position: "absolute",
                          left: "50%",
                          top: "50%",
                          width: selectionPx,
                          height: selectionPx,
                          margin: `${-selectionPx / 2}px 0 0 ${-selectionPx / 2}px`,
                          border: "1.5px solid var(--accent)",
                          borderRadius: 3,
                          boxShadow: "0 0 0 3px rgba(228,3,46,.14)",
                        }}
                      />
                    )}
                    {/* battery bar */}
                    {props.layers.batteryBars && (
                      <div
                        style={{
                          position: "absolute",
                          left: "50%",
                          top: -footprintPx / 2 - 11,
                          transform: "translateX(-50%)",
                          width: batteryPx,
                          height: 3,
                          background: "rgba(255,255,255,.2)",
                          borderRadius: 2,
                        }}
                      >
                        <div style={{ height: "100%", width: `${pct}%`, background: batteryColor(b), borderRadius: 2 }} />
                      </div>
                    )}
                    {/* body and heading are one glyph: it rotates as a piece */}
                    <div
                      style={{
                        position: "absolute",
                        left: "50%",
                        top: "50%",
                        transform: "translate(-50%, -50%)",
                        animation: blink ? "dbBlink 1.1s ease-in-out infinite" : undefined,
                      }}
                    >
                      <BotGlyph
                        color={stc}
                        heading={b.heading}
                        size={glyphPx}
                        level={level}
                      />
                    </div>
                    {/* drive dot: white ring at center = drivable; its FILL is
                        the LED color (experiment: merges the v1 LED pip into the
                        drive indicator - see design-feedback) */}
                    {b.drivable && (
                      <div
                        style={{
                          position: "absolute",
                          left: "50%",
                          top: "50%",
                          width: drivePx,
                          height: drivePx,
                          margin: `${-drivePx / 2}px 0 0 ${-drivePx / 2}px`,
                          borderRadius: "50%",
                          background: led,
                          border: `${Math.max(1, drivePx / 7)}px solid rgba(255,255,255,.95)`,
                          boxShadow: `0 0 3px rgba(0,0,0,.5), 0 0 5px ${led}`,
                          zIndex: 7,
                        }}
                      />
                    )}
                    {/* chip label: selected or hovered only */}
                    {(selected || hovered) && (
                      <div
                        style={{
                          position: "absolute",
                          left: "50%",
                          top: (selected ? selectionPx : footprintPx) / 2 + 3,
                          transform: "translateX(-50%)",
                          font: "600 9px/1 var(--font-mono)",
                          letterSpacing: ".5px",
                          color: "var(--text)",
                          background: "var(--elevated)",
                          padding: "2px 5px",
                          borderRadius: 3,
                          whiteSpace: "nowrap",
                          boxShadow: "0 1px 3px rgba(0,0,0,.4)",
                          pointerEvents: "none",
                        }}
                      >
                        {b.id.slice(-4).toUpperCase()}
                      </div>
                    )}
                  </div>
                );
              })}
        </div>
      </div>

      {/* the ruler: which metre of the frame each edge of the canvas is on.
          Canvas chrome like the zoom buttons, so it keeps its size and stays
          on screen whatever the camera does. */}
      <div
        aria-label="Metre ruler"
        style={{
          position: "absolute",
          inset: 0,
          pointerEvents: "none",
          zIndex: 8,
          font: "10px/1 var(--font-mono)",
          color: "var(--muted)",
        }}
      >
        {rulerX.map((t) => (
          <span
            key={`rx-${t.mm}`}
            style={{ position: "absolute", left: t.px + 3, top: 4, whiteSpace: "nowrap" }}
          >
            {metreLabel(t.mm, rulerStep)}
          </span>
        ))}
        {rulerY.map((t) => (
          <span
            key={`ry-${t.mm}`}
            style={{ position: "absolute", left: 4, top: t.px + 3, whiteSpace: "nowrap" }}
          >
            {metreLabel(t.mm, rulerStep)}
          </span>
        ))}
      </div>

      {/* marquee */}
      {marquee && (
        <div
          style={{
            position: "fixed",
            left: Math.min(marquee.x0, marquee.x1),
            top: Math.min(marquee.y0, marquee.y1),
            width: Math.abs(marquee.x1 - marquee.x0),
            height: Math.abs(marquee.y1 - marquee.y0),
            border: "1px dashed var(--accent)",
            background: "rgba(228,3,46,.06)",
            pointerEvents: "none",
            zIndex: 20,
          }}
        />
      )}

      {/* zoom controls */}
      <div
        style={{
          position: "absolute",
          left: 14,
          bottom: 14,
          display: "flex",
          flexDirection: "column",
          background: "var(--surface)",
          border: "1px solid var(--hairline)",
          borderRadius: 8,
          overflow: "hidden",
          boxShadow: "0 4px 16px rgba(0,0,0,.3)",
          zIndex: 10,
        }}
        onPointerDown={(e) => e.stopPropagation()}
      >
        {[
          { label: "+", title: "Zoom in", fn: () => setCam((c) => clampCam({ ...c, scale: Math.min(zoomMax(props.site, props.viewport, geomRef.current), c.scale * 1.25) }, geomRef.current)) },
          { label: "−", title: "Zoom out", fn: () => setCam((c) => clampCam({ ...c, scale: Math.max(ZOOM_MIN, c.scale / 1.25) }, geomRef.current)) },
          { label: "◎", title: "Zoom to", fn: () => setZoomOpen((open) => !open) },
        ].map((z, i) => (
          <div
            key={i}
            title={z.title}
            onClick={z.fn}
            style={{
              width: 30,
              height: 30,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              cursor: "pointer",
              fontSize: 15,
              borderBottom: i < 2 ? "1px solid var(--hairline)" : "none",
              color: "var(--text)",
              background: i === 2 && zoomOpen ? "var(--elevated)" : "transparent",
            }}
          >
            {z.label}
          </div>
        ))}
      </div>

      {/* the named zooms: the whole site, then one per area */}
      {zoomOpen && (
        <div
          role="menu"
          aria-label="Zoom to"
          onPointerDown={(e) => e.stopPropagation()}
          style={{
            position: "absolute",
            left: 50,
            bottom: 14,
            minWidth: 128,
            background: "var(--surface)",
            border: "1px solid var(--hairline)",
            borderRadius: 8,
            overflow: "hidden",
            boxShadow: "0 4px 16px rgba(0,0,0,.3)",
            zIndex: 14,
          }}
        >
          {zoomNames(props.site).map((name) => (
            <div
              key={name}
              role="menuitem"
              onClick={() => {
                props.onZoom(name);
                setZoomOpen(false);
              }}
              style={{
                padding: "7px 12px",
                fontSize: 12,
                cursor: "pointer",
                whiteSpace: "nowrap",
                textTransform: name === SITE_ZOOM ? "capitalize" : "none",
                color: "var(--text)",
              }}
            >
              {name}
            </div>
          ))}
        </div>
      )}

      {/* hint */}
      <div
        style={{
          position: "absolute",
          right: 14,
          bottom: 14,
          fontSize: 11,
          color: "var(--muted)",
          background: "var(--surface)",
          border: "1px solid var(--hairline)",
          borderRadius: 6,
          padding: "5px 9px",
          pointerEvents: "none",
        }}
      >
        drag = pan &middot; shift-drag = select &middot; &#8997; alt-click = waypoint
      </div>
    </div>
  );
};
