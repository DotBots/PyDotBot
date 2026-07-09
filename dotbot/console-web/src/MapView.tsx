import React, { useCallback, useMemo, useRef, useState } from "react";

import { LH2Position, MapSize, UnifiedBot } from "./types";

export interface Layers {
  batteryBars: boolean;
  waypoints: boolean;
  trails: boolean;
  labels: boolean;
}

interface MapViewProps {
  bots: UnifiedBot[];
  mapSize: MapSize;
  selection: Set<string>;
  layers: Layers;
  pendingWaypoints: LH2Position[]; // local queue, not yet sent
  onSelect: (ids: string[], additive: boolean) => void;
  onAddWaypoint: (p: LH2Position) => void;
}

const BOT_R = 11; // px radius of the bot circle at zoom 1

interface Camera {
  scale: number;
  tx: number;
  ty: number;
}

export const MapView: React.FC<MapViewProps> = (props) => {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [cam, setCam] = useState<Camera>({ scale: 1, tx: 0, ty: 0 });
  const [marquee, setMarquee] = useState<{
    x0: number;
    y0: number;
    x1: number;
    y1: number;
  } | null>(null);
  const dragRef = useRef<{ additive: boolean } | null>(null);

  // The arena is drawn as a square of `side` px centered in the wrapper.
  const [side, setSide] = useState(600);
  const measure = useCallback((el: HTMLDivElement | null) => {
    (wrapRef as React.MutableRefObject<HTMLDivElement | null>).current = el;
    if (el) {
      const r = el.getBoundingClientRect();
      setSide(Math.max(200, Math.min(r.width, r.height) - 48));
    }
  }, []);

  const mmToPx = (p: LH2Position) => ({
    left: (p.x / props.mapSize.width) * side,
    top: (p.y / props.mapSize.height) * side,
  });

  const pxToMm = (clientX: number, clientY: number): LH2Position | null => {
    const el = wrapRef.current;
    if (!el) return null;
    const r = el.getBoundingClientRect();
    // Undo camera transform (transform origin is the wrapper center).
    const cx = r.left + r.width / 2;
    const cy = r.top + r.height / 2;
    const ux = (clientX - cx - cam.tx) / cam.scale + r.width / 2;
    const uy = (clientY - cy - cam.ty) / cam.scale + r.height / 2;
    // Arena square is centered in the wrapper.
    const ax = ux - (r.width - side) / 2;
    const ay = uy - (r.height - side) / 2;
    const x = (ax / side) * props.mapSize.width;
    const y = (ay / side) * props.mapSize.height;
    if (x < 0 || y < 0 || x > props.mapSize.width || y > props.mapSize.height)
      return null;
    return { x: Math.round(x), y: Math.round(y) };
  };

  const onCanvasDown = (e: React.PointerEvent) => {
    if (e.button !== 0) return;
    if (e.altKey) {
      const p = pxToMm(e.clientX, e.clientY);
      if (p) props.onAddWaypoint(p);
      return;
    }
    // Start a marquee from empty canvas.
    dragRef.current = { additive: e.shiftKey };
    setMarquee({ x0: e.clientX, y0: e.clientY, x1: e.clientX, y1: e.clientY });
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  };

  const onCanvasMove = (e: React.PointerEvent) => {
    if (!dragRef.current) return;
    setMarquee((m) => (m ? { ...m, x1: e.clientX, y1: e.clientY } : m));
  };

  const onCanvasUp = () => {
    if (!dragRef.current || !marquee) {
      dragRef.current = null;
      setMarquee(null);
      return;
    }
    const { additive } = dragRef.current;
    const x0 = Math.min(marquee.x0, marquee.x1);
    const x1 = Math.max(marquee.x0, marquee.x1);
    const y0 = Math.min(marquee.y0, marquee.y1);
    const y1 = Math.max(marquee.y0, marquee.y1);
    const isClick = x1 - x0 < 5 && y1 - y0 < 5;
    if (isClick) {
      props.onSelect([], additive); // click on empty canvas clears
    } else {
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
      props.onSelect(hits, additive);
    }
    dragRef.current = null;
    setMarquee(null);
  };

  const gridStep = side / 10;
  const gridBg = useMemo(
    () =>
      `repeating-linear-gradient(0deg, var(--grid) 0 1px, transparent 1px ${gridStep}px),` +
      `repeating-linear-gradient(90deg, var(--grid) 0 1px, transparent 1px ${gridStep}px)`,
    [gridStep],
  );

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
        cursor: "crosshair",
        touchAction: "none",
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
          {/* trails */}
          {props.layers.trails && (
            <svg
              width={side}
              height={side}
              style={{ position: "absolute", inset: 0, pointerEvents: "none" }}
            >
              {props.bots
                .filter((b) => b.trail.length > 1)
                .map((b) => (
                  <polyline
                    key={b.id}
                    points={b.trail
                      .map((p) => {
                        const q = mmToPx(p);
                        return `${q.left},${q.top}`;
                      })
                      .join(" ")}
                    fill="none"
                    stroke={
                      b.led
                        ? `rgb(${b.led.red},${b.led.green},${b.led.blue})`
                        : "var(--muted)"
                    }
                    strokeWidth={1}
                    opacity={0.35}
                  />
                ))}
            </svg>
          )}

          {/* active missions: waypoints already sent to bots */}
          {props.layers.waypoints &&
            props.bots
              .filter((b) => b.waypoints.length > 0 && b.position)
              .map((b) => (
                <svg
                  key={`wp-${b.id}`}
                  width={side}
                  height={side}
                  style={{ position: "absolute", inset: 0, pointerEvents: "none" }}
                >
                  <polyline
                    points={[b.position!, ...b.waypoints]
                      .map((p) => {
                        const q = mmToPx(p);
                        return `${q.left},${q.top}`;
                      })
                      .join(" ")}
                    fill="none"
                    stroke="var(--s-Programming)"
                    strokeWidth={1.5}
                    strokeDasharray="5 4"
                    opacity={0.8}
                  />
                  {b.waypoints.map((p, i) => {
                    const q = mmToPx(p);
                    return (
                      <rect
                        key={i}
                        x={q.left - 4}
                        y={q.top - 4}
                        width={8}
                        height={8}
                        fill="none"
                        stroke="var(--s-Programming)"
                        strokeWidth={1.5}
                        transform={`rotate(45 ${q.left} ${q.top})`}
                      />
                    );
                  })}
                </svg>
              ))}

          {/* pending (queued, not sent) waypoints */}
          {props.layers.waypoints &&
            props.pendingWaypoints.map((p, i) => {
              const q = mmToPx(p);
              return (
                <div
                  key={`pend-${i}`}
                  style={{
                    position: "absolute",
                    left: q.left,
                    top: q.top,
                    transform: "translate(-50%, -50%) rotate(45deg)",
                    width: 9,
                    height: 9,
                    border: "1.5px dashed var(--accent)",
                    pointerEvents: "none",
                  }}
                  title={`waypoint ${i + 1}`}
                />
              );
            })}

          {/* bots */}
          {props.bots
            .filter((b) => b.position)
            .map((b) => {
              const q = mmToPx(b.position!);
              const selected = props.selection.has(b.id);
              const ledColor = b.led
                ? `rgb(${b.led.red},${b.led.green},${b.led.blue})`
                : "var(--s-Inactive)";
              const batPct = Math.max(
                0,
                Math.min(100, ((b.battery - 2.0) / (4.2 - 2.0)) * 100),
              );
              return (
                <div
                  key={b.id}
                  id={`bot-${b.id}`}
                  onPointerDown={(e) => {
                    e.stopPropagation();
                    props.onSelect([b.id], e.shiftKey);
                  }}
                  style={{
                    position: "absolute",
                    left: q.left,
                    top: q.top,
                    width: 0,
                    height: 0,
                    cursor: "pointer",
                  }}
                  title={`${b.id} - ${b.state}${b.drivable ? "" : " (not drivable)"}`}
                >
                  {/* selection rectangle */}
                  {selected && (
                    <div
                      style={{
                        position: "absolute",
                        left: -BOT_R - 6,
                        top: -BOT_R - 6,
                        width: (BOT_R + 6) * 2,
                        height: (BOT_R + 6) * 2,
                        border: "1.5px solid var(--accent)",
                        borderRadius: 4,
                      }}
                    />
                  )}
                  {/* battery bar */}
                  {props.layers.batteryBars && (
                    <div
                      style={{
                        position: "absolute",
                        left: -BOT_R,
                        top: -BOT_R - 8,
                        width: BOT_R * 2,
                        height: 3,
                        background: "var(--elevated)",
                        borderRadius: 2,
                        overflow: "hidden",
                      }}
                    >
                      <div
                        style={{
                          width: `${batPct}%`,
                          height: "100%",
                          background:
                            batPct < 20
                              ? "var(--s-Stopping)"
                              : batPct < 45
                                ? "var(--s-Programming)"
                                : "var(--s-Running)",
                        }}
                      />
                    </div>
                  )}
                  {/* body: LED-colored circle */}
                  <div
                    style={{
                      position: "absolute",
                      left: -BOT_R,
                      top: -BOT_R,
                      width: BOT_R * 2,
                      height: BOT_R * 2,
                      borderRadius: "50%",
                      background: ledColor,
                      opacity: b.state === "Inactive" ? 0.35 : 1,
                      border: b.drivable
                        ? "2px solid rgba(255,255,255,.75)"
                        : "2px solid transparent",
                      animation:
                        b.state === "Programming"
                          ? "dbBlink 1.2s ease-in-out infinite"
                          : undefined,
                    }}
                  />
                  {/* heading pointer */}
                  {b.heading !== null && (
                    <div
                      style={{
                        position: "absolute",
                        left: 0,
                        top: 0,
                        transform: `rotate(${b.heading}deg)`,
                      }}
                    >
                      <div
                        style={{
                          position: "absolute",
                          left: -5,
                          top: -BOT_R - 7,
                          width: 0,
                          height: 0,
                          borderLeft: "5px solid transparent",
                          borderRight: "5px solid transparent",
                          borderBottom: `7px solid ${ledColor}`,
                        }}
                      />
                    </div>
                  )}
                  {/* state pip */}
                  <div
                    style={{
                      position: "absolute",
                      left: BOT_R - 5,
                      top: BOT_R - 5,
                      width: 8,
                      height: 8,
                      borderRadius: "50%",
                      background: `var(--s-${b.state})`,
                      border: "1.5px solid var(--canvas)",
                    }}
                  />
                  {/* label */}
                  {props.layers.labels && (
                    <div
                      style={{
                        position: "absolute",
                        left: -30,
                        top: BOT_R + 5,
                        width: 60,
                        textAlign: "center",
                        fontFamily: "var(--font-mono)",
                        fontSize: 9,
                        color: "var(--muted)",
                        pointerEvents: "none",
                      }}
                    >
                      {b.id.slice(-4)}
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
          {
            label: "+",
            fn: () => setCam((c) => ({ ...c, scale: Math.min(4, c.scale * 1.25) })),
          },
          {
            label: "−",
            fn: () => setCam((c) => ({ ...c, scale: Math.max(0.5, c.scale / 1.25) })),
          },
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
        drag = select &middot; shift = add &middot; &#8997; alt-click = waypoint
      </div>
    </div>
  );
};
