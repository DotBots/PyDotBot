import React, { useCallback, useMemo, useRef, useState } from "react";

import { arenaToFraction, fractionToArena } from "./arenaFrame";
import { BOT_GLYPH_BOX, BOT_GLYPH_SPAN, BotGlyph } from "./BotGlyph";
import { ResetBadge, batteryColor, batteryPct, stateColor } from "./viewChrome";

import { LH2Position, MapSize, UnifiedBot } from "./types";
import { useSmoothPositions } from "./useSmoothPositions";

// Layer set mirrors the v1 design (Battery Bars / Waypoints / HotSpots /
// DotBots / Real-scale bots); Trails is our addition on top.
export interface Layers {
  batteryBars: boolean;
  waypoints: boolean;
  hotSpots: boolean;
  dotBots: boolean;
  trueScale: boolean;
  crashedOnly: boolean;
  trails: boolean;
}

export interface Camera {
  scale: number;
  tx: number;
  ty: number;
}

export interface ViewGeom {
  w: number;
  h: number;
  side: number;
}

// v1 clampPan: keep the arena reachable, never fling it off-screen.
export function clampCam(cam: Camera, geom: ViewGeom): Camera {
  const sw = geom.side * cam.scale;
  const padX = Math.max(0, (geom.w - geom.side) / 2);
  const padY = Math.max(0, (geom.h - geom.side) / 2);
  const mx = Math.max(0, (sw - geom.w) / 2) + padX;
  const my = Math.max(0, (sw - geom.h) / 2) + padY;
  return {
    ...cam,
    tx: Math.max(-mx, Math.min(mx, cam.tx)),
    ty: Math.max(-my, Math.min(my, cam.ty)),
  };
}

interface MapViewProps {
  bots: UnifiedBot[];
  mapSize: MapSize;
  selection: Set<string>;
  layers: Layers;
  plannedMissions: { waypoints: LH2Position[]; led: string | null }[]; // local queues, not yet sent
  cam: Camera;
  setCam: React.Dispatch<React.SetStateAction<Camera>>;
  onGeom: (g: ViewGeom) => void;
  onSelect: (ids: string[], mode: "replace" | "toggle" | "add") => void;
  onAddWaypoint: (p: LH2Position) => void;
}

const REAL_BOT_MM = 80; // approximate DotBot footprint for the Real-scale layer

const ledCss = (b: UnifiedBot) =>
  b.led ? `rgb(${b.led.red},${b.led.green},${b.led.blue})` : "var(--s-Inactive)";



export const MapView: React.FC<MapViewProps> = (props) => {
  const wrapRef = useRef<HTMLDivElement>(null);
  const { cam, setCam } = props;
  const [marquee, setMarquee] = useState<{ x0: number; y0: number; x1: number; y1: number } | null>(null);
  const [hoverId, setHoverId] = useState<string | null>(null);
  const panRef = useRef<{ x0: number; y0: number; tx0: number; ty0: number; moved: boolean } | null>(null);
  const marqueeRef = useRef<{ additive: boolean } | null>(null);
  const geomRef = useRef<ViewGeom>({ w: 1000, h: 600, side: 600 });

  const mapDiagonal = Math.hypot(props.mapSize.width, props.mapSize.height);
  const smoothPositions = useSmoothPositions(props.bots, mapDiagonal);

  const [side, setSide] = useState(600);
  const onGeomRef = useRef(props.onGeom);
  onGeomRef.current = props.onGeom;
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
      const s = Math.max(200, Math.min(r.width, r.height) - 48);
      setSide(s);
      geomRef.current = { w: r.width, h: r.height, side: s };
      onGeomRef.current(geomRef.current);
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const pctPos = (p: LH2Position) => {
    const { fx, fy } = arenaToFraction(p, props.mapSize);
    return { left: fx * 100, top: fy * 100 };
  };

  const pxToMm = (clientX: number, clientY: number): LH2Position | null => {
    const el = wrapRef.current;
    if (!el) return null;
    const r = el.getBoundingClientRect();
    const cx = r.left + r.width / 2;
    const cy = r.top + r.height / 2;
    const ux = (clientX - cx - cam.tx) / cam.scale + r.width / 2;
    const uy = (clientY - cy - cam.ty) / cam.scale + r.height / 2;
    const ax = ux - (r.width - side) / 2;
    const ay = uy - (r.height - side) / 2;
    const { x, y } = fractionToArena(ax / side, ay / side, props.mapSize);
    if (x < 0 || y < 0 || x > props.mapSize.width || y > props.mapSize.height) return null;
    return { x: Math.round(x), y: Math.round(y) };
  };

  // v1 canvas semantics: alt-click = waypoint, shift-drag = marquee,
  // plain drag = pan, plain click (no movement) = clear selection.
  const onCanvasDown = (e: React.PointerEvent) => {
    if (e.button !== 0) return;
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

  const gridStep = side / 10;
  const gridBg = useMemo(
    () =>
      `repeating-linear-gradient(0deg, var(--grid) 0 1px, transparent 1px ${gridStep}px),` +
      `repeating-linear-gradient(90deg, var(--grid) 0 1px, transparent 1px ${gridStep}px)`,
    [gridStep],
  );

  // Real-scale layer: glyphs scale to the actual DotBot footprint.
  const gscale = props.layers.trueScale
    ? Math.max(0.2, (side * (REAL_BOT_MM / props.mapSize.width)) / BOT_GLYPH_SPAN)
    : 1;

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
        style={{
          position: "absolute",
          inset: 0,
          transform: `translate(${cam.tx}px, ${cam.ty}px) scale(${cam.scale})`,
          transformOrigin: "50% 50%",
        }}
      >
        {/* arena */}
        <div
          style={{
            position: "absolute",
            left: "50%",
            top: "50%",
            width: side,
            height: side,
            transform: "translate(-50%, -50%)",
            background: gridBg,
            border: "1px solid var(--grid)",
            borderRadius: 6,
          }}
        >
          {/* subtle center accents (v1) */}
          <div style={{ position: "absolute", left: "50%", top: 0, bottom: 0, width: 1, background: "rgba(228,3,46,.16)", pointerEvents: "none" }} />
          <div style={{ position: "absolute", top: "50%", left: 0, right: 0, height: 1, background: "var(--hairline)", pointerEvents: "none" }} />

          {/* trails (our extra layer) */}
          {props.layers.trails && (
            <svg width={side} height={side} style={{ position: "absolute", inset: 0, pointerEvents: "none" }}>
              {props.bots
                .filter((b) => b.trail.length > 1)
                .map((b) => (
                  <polyline
                    key={b.id}
                    points={b.trail
                      .map((p) => {
                        const { fx, fy } = arenaToFraction(p, props.mapSize);
                        return `${fx * side},${fy * side}`;
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
              const s = (isSel ? 10 : 8) * gscale;
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
                      transform: "translate(-50%, -50%) rotate(45deg)",
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
                    width: 10 * gscale,
                    height: 10 * gscale,
                    transform: "translate(-50%, -50%) rotate(45deg)",
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
                      if (e.shiftKey || e.metaKey || e.ctrlKey) {
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
                      transform: `translate(-50%, -50%) scale(${gscale})`,
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
                          width: 44,
                          height: 44,
                          margin: "-22px 0 0 -22px",
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
                          top: -24,
                          transform: "translateX(-50%)",
                          width: 28,
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
                      <BotGlyph color={stc} heading={b.heading} size={BOT_GLYPH_BOX} />
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
                          width: 10,
                          height: 10,
                          margin: "-5px 0 0 -5px",
                          borderRadius: "50%",
                          background: led,
                          border: "1.5px solid rgba(255,255,255,.95)",
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
                          top: 21,
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
          { label: "+", fn: () => setCam((c) => clampCam({ ...c, scale: Math.min(4, c.scale * 1.25) }, geomRef.current)) },
          { label: "−", fn: () => setCam((c) => clampCam({ ...c, scale: Math.max(0.5, c.scale / 1.25) }, geomRef.current)) },
          { label: "◎", fn: () => setCam({ scale: 1, tx: 0, ty: 0 }) },
        ].map((z, i) => (
          <div
            key={i}
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
            }}
          >
            {z.label}
          </div>
        ))}
      </div>

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
