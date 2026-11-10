import React, { useMemo, useRef, useState } from "react";

import { areaColor } from "../areaColor";
import { heldCalibrationId } from "../botFacts";
import type { UnifiedBot } from "../types";
import { fogImage, handover, type Boxes, type Coverage, type Geometry } from "./coverage";
import { Icon } from "./icons";
import type { Doc, Point } from "./model";
import type { CoverageMode } from "./StationsPanel";

// The room as a twin: the floor with its areas and origin, each station on a
// pole at its estimated height, coverage tinted on the floor with the
// handover line, the robots live. A parallel projection, so a millimetre on
// the floor is the same length everywhere along its axis and anything on the
// floor plane maps exactly; dragging orbits it.

const W = 900;
const H = 600;
const PAD = 56;

interface View {
  /** Turn of the floor about the vertical, radians. */
  phi: number;
  /** How flat the floor is drawn: the vertical scale of floor depth, 0.25 to 0.9. */
  tilt: number;
}
const HOME: View = { phi: Math.PI / 4, tilt: 0.5 };

type P3 = (x: number, y: number, z?: number) => Point;

/** The projection fitted to the floor and the stations. */
function fitted(view: View, extent: [number, number], geometry: Geometry | null): P3 {
  const c = Math.cos(view.phi);
  const s = Math.sin(view.phi);
  const raw = (x: number, y: number, z = 0): Point => [x * c - y * s, (x * s + y * c) * view.tilt - z];
  const pts: Point[] = [raw(0, 0), raw(extent[0], 0), raw(extent[0], extent[1]), raw(0, extent[1])];
  for (const st of Object.values(geometry?.stations ?? {})) {
    pts.push(raw(st.x_mm, st.y_mm, 0), raw(st.x_mm, st.y_mm, st.height_mm));
  }
  const xs = pts.map((p) => p[0]);
  const ys = pts.map((p) => p[1]);
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  const k = Math.min((W - 2 * PAD) / (Math.max(...xs) - minX || 1), (H - 2 * PAD - 30) / (Math.max(...ys) - minY || 1));
  const ox = (W - k * (Math.max(...xs) - minX)) / 2;
  const oy = (H - 30 - k * (Math.max(...ys) - minY)) / 2;
  return (x, y, z = 0) => {
    const [u, v] = raw(x, y, z);
    return [ox + (u - minX) * k, oy + (v - minY) * k];
  };
}

const poly = (ps: Point[]) => ps.map((p) => p.map((v) => Math.round(v * 10) / 10).join(",")).join(" ");
const rectPts = (r: [number, number, number, number], P: P3): Point[] => [P(r[0], r[1]), P(r[2], r[1]), P(r[2], r[3]), P(r[0], r[3])];

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
  light: boolean;
  /** Large: the whole canvas, labels bigger. */
  large?: boolean;
  selectedStation?: number | null;
  onSelectStation?: (index: number | null) => void;
}> = ({ doc, extent, geometry, boxes, coverage, mode, bots, shownName, shownId, stationFit, light, large, selectedStation, onSelectStation }) => {
  const [view, setView] = useState<View>(HOME);
  const drag = useRef<{ x: number; y: number; view: View } | null>(null);
  const P = useMemo(() => fitted(view, extent, geometry), [view, extent, geometry]);
  const [w, h] = extent;
  const floor = [P(0, 0), P(w, 0), P(w, h), P(0, h)];
  const stations = Object.entries(geometry?.stations ?? {}).map(([s, p]) => ({ index: Number(s), ...p }));
  const two = boxes.length === 2 ? boxes : null;
  const shared = !!two && two[0].rect.join() === two[1].rect.join();
  const line = two && !shared ? handover(two[0].rect, two[1].rect) : null;
  const overlap: [number, number, number, number] | null =
    two && !shared
      ? [Math.max(two[0].rect[0], two[1].rect[0]), Math.max(two[0].rect[1], two[1].rect[1]), Math.min(two[0].rect[2], two[1].rect[2]), Math.min(two[0].rect[3], two[1].rect[3])]
      : null;
  const fog = mode === "error" && coverage?.fog ? coverage.fog : null;
  const fogUrl = useMemo(() => (fog && coverage ? fogImage(fog, coverage.limit_mm, light) : null), [fog, coverage?.limit_mm, light]);
  // The floor plane is affine under the projection: an image laid on it is one matrix
  const fogMatrix = (() => {
    if (!fog) return null;
    const o = P(fog.origin[0], fog.origin[1]);
    const ex = P(fog.origin[0] + 1, fog.origin[1]);
    const ey = P(fog.origin[0], fog.origin[1] + 1);
    return `matrix(${ex[0] - o[0]} ${ex[1] - o[1]} ${ey[0] - o[0]} ${ey[1] - o[1]} ${o[0]} ${o[1]})`;
  })();
  const f = large ? 1.35 : 1;
  const apart = Object.entries(geometry?.apart_mm ?? {})[0];
  const have = (b: UnifiedBot) => !!shownId && heldCalibrationId(b).toLowerCase() === shownId.toLowerCase();

  const onDown = (e: React.PointerEvent<SVGSVGElement>) => {
    drag.current = { x: e.clientX, y: e.clientY, view };
    (e.currentTarget as SVGSVGElement).setPointerCapture(e.pointerId);
  };
  const onMove = (e: React.PointerEvent<SVGSVGElement>) => {
    if (!drag.current) return;
    const dx = e.clientX - drag.current.x;
    const dy = e.clientY - drag.current.y;
    setView({ phi: drag.current.view.phi + dx * 0.006, tilt: Math.max(0.25, Math.min(0.9, drag.current.view.tilt - dy * 0.003)) });
  };
  const onUp = () => {
    drag.current = null;
  };

  return (
    <div className={`room${large ? " large" : ""}`} data-testid="room-view">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={`The room: ${w} by ${h} mm, ${stations.length} station${stations.length === 1 ? "" : "s"}, ${bots.length} robot${bots.length === 1 ? "" : "s"}`}
        onPointerDown={onDown}
        onPointerMove={onMove}
        onPointerUp={onUp}
        onPointerCancel={onUp}
        onDoubleClick={() => setView(HOME)}
        style={{ cursor: drag.current ? "grabbing" : "grab", touchAction: "none" }}
      >
        <defs>
          <pattern id="room-hatch" patternUnits="userSpaceOnUse" width="7" height="7" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="7" stroke="var(--muted)" strokeWidth="1.2" opacity="0.55" />
          </pattern>
        </defs>
        {/* sight lines, behind everything */}
        {stations.map((st) => (
          <g key={`s-${st.index}`} stroke={`var(--st-${st.index % 2})`} strokeOpacity={selectedStation === st.index ? 0.6 : 0.18} strokeWidth={1}>
            {floor.map((c, i) => {
              const t = P(st.x_mm, st.y_mm, st.height_mm);
              return <line key={i} x1={t[0]} y1={t[1]} x2={c[0]} y2={c[1]} />;
            })}
          </g>
        ))}
        {/* the floor */}
        <polygon points={poly(floor)} fill="color-mix(in srgb, var(--text) 6%, transparent)" stroke="var(--muted)" strokeWidth={1.2} />
        {/* coverage */}
        {mode === "fix" &&
          boxes.map((b) => <polygon key={`c-${b.index}`} points={poly(rectPts(b.rect, P))} fill={`var(--st-${b.index % 2})`} fillOpacity={shared ? 0.14 : 0.22} stroke="none" data-testid={`room-cover-${b.index}`} />)}
        {mode === "fix" && overlap && overlap[2] > overlap[0] && overlap[3] > overlap[1] && <polygon points={poly(rectPts(overlap, P))} fill="url(#room-hatch)" stroke="none" />}
        {fogUrl && fog && fogMatrix && <image href={fogUrl} x={0} y={0} width={fog.cols * fog.cell_mm} height={fog.rows * fog.cell_mm} preserveAspectRatio="none" transform={fogMatrix} style={{ imageRendering: "pixelated" }} opacity={0.85} />}
        {/* areas */}
        {doc.areas.map((a) => {
          const col = areaColor({ ...a, role: a.role ?? undefined }, doc.areas.map((x) => ({ ...x, role: x.role ?? undefined })));
          const ps = rectPts([a.x, a.y, a.x + a.w, a.y + a.h], P);
          return (
            <g key={a.key}>
              <polygon points={poly(ps)} fill="none" stroke={col} strokeWidth={1.3} strokeDasharray="5 3" />
              <text x={ps[3][0] + 4} y={ps[3][1] - 4} fontSize={10.5 * f} fill={col} className="halo">
                {a.name}
              </text>
            </g>
          );
        })}
        {/* handover */}
        {mode === "fix" && line && (
          <g data-testid="room-handover">
            <line x1={P(...line.from)[0]} y1={P(...line.from)[1]} x2={P(...line.to)[0]} y2={P(...line.to)[1]} stroke="var(--text)" strokeWidth={1.8} strokeDasharray="7 4" />
            <text x={P(...line.from)[0] + 6} y={P(...line.from)[1] + 14 * f} fontSize={11 * f} fontWeight={700} fontFamily="var(--font-mono)" className="halo">
              {line.label.replace("handover ", "handover at ")}
            </text>
          </g>
        )}
        {/* origin and axes */}
        {(() => {
          const o = P(0, 0);
          const ax = P(Math.min(250, w / 3), 0);
          const ay = P(0, Math.min(250, h / 3));
          return (
            <g>
              <line x1={o[0]} y1={o[1]} x2={ax[0]} y2={ax[1]} stroke="var(--text)" strokeWidth={1.6} />
              <line x1={o[0]} y1={o[1]} x2={ay[0]} y2={ay[1]} stroke="var(--text)" strokeWidth={1.6} />
              <text x={ax[0] + 4} y={ax[1] + 4} fontSize={10 * f} className="halo">
                x
              </text>
              <text x={ay[0] - 10} y={ay[1] + 4} fontSize={10 * f} className="halo">
                y
              </text>
              <circle cx={o[0]} cy={o[1]} r={5} fill="var(--canvas)" stroke="var(--text)" strokeWidth={1.6} />
              <text x={o[0] + 8} y={o[1] - 8} fontSize={11 * f} fontWeight={700} className="halo">
                origin
              </text>
            </g>
          );
        })()}
        {/* floor dimensions, at the middles of the two front edges */}
        {(() => {
          const mx = P(w / 2, h);
          const my = P(0, h / 2);
          return (
            <g fontSize={10.5 * f} className="halo" fill="var(--muted)">
              <text x={mx[0]} y={mx[1] + 16 * f} textAnchor="middle">
                {(w / 1000).toFixed(2)} m
              </text>
              <text x={my[0] - 8} y={my[1] + 14 * f} textAnchor="end">
                {(h / 1000).toFixed(2)} m
              </text>
            </g>
          );
        })()}
        {/* robots */}
        {bots
          .filter((b) => b.position)
          .map((b) => {
            const p = P(b.position!.x, b.position!.y);
            const has = have(b);
            return (
              <g key={b.id} data-testid="room-robot">
                <circle cx={p[0]} cy={p[1]} r={4.5 * f} fill={has ? "var(--text)" : "var(--canvas)"} stroke="var(--text)" strokeWidth={1.4} />
                {bots.length <= 50 && (
                  <text x={p[0] + 7} y={p[1] + 4} fontSize={9 * f} fontFamily="var(--font-mono)" className="halo" fill="var(--muted)">
                    {b.id.slice(-4).toUpperCase()}
                  </text>
                )}
              </g>
            );
          })}
        {/* stations */}
        {stations.map((st) => {
          const foot = P(st.x_mm, st.y_mm, 0);
          const top = P(st.x_mm, st.y_mm, st.height_mm);
          const hue = `var(--st-${st.index % 2})`;
          const right = top[0] > W / 2;
          const fit = stationFit?.[st.index];
          const on = selectedStation === st.index;
          return (
            <g key={st.index} data-testid={`room-station-${st.index}`} onClick={(e) => (e.stopPropagation(), onSelectStation?.(on ? null : st.index))} style={{ cursor: onSelectStation ? "pointer" : undefined }}>
              <line x1={foot[0]} y1={foot[1]} x2={top[0]} y2={top[1]} stroke={hue} strokeDasharray="3 3" strokeWidth={1.4} />
              <ellipse cx={foot[0]} cy={foot[1]} rx={6} ry={3} fill="none" stroke={hue} />
              <circle cx={top[0]} cy={top[1]} r={on ? 8 : 6} fill={hue} stroke={on ? "var(--text)" : "none"} strokeWidth={1.5} />
              <g transform={`translate(${right ? top[0] - 12 : top[0] + 12}, ${top[1] - 8})`}>
                <rect x={right ? -132 * f : 0} y={-14 * f} width={132 * f} height={32 * f} rx={6} fill="var(--surface)" stroke={hue} />
                <text x={right ? -126 * f : 6 * f} y={0} fontSize={11 * f} fontWeight={700} fill={hue}>
                  S{st.index} · channel {st.index + 1}
                </text>
                <text x={right ? -126 * f : 6 * f} y={13 * f} fontSize={10 * f}>
                  {(st.height_mm / 1000).toFixed(1)} m up{fit !== undefined ? ` · fit ${fit.toFixed(2)} mm` : ""}
                </text>
              </g>
            </g>
          );
        })}
        {apart && stations.length === 2 && (
          <g>
            <line
              x1={P(stations[0].x_mm, stations[0].y_mm, stations[0].height_mm)[0]}
              y1={P(stations[0].x_mm, stations[0].y_mm, stations[0].height_mm)[1]}
              x2={P(stations[1].x_mm, stations[1].y_mm, stations[1].height_mm)[0]}
              y2={P(stations[1].x_mm, stations[1].y_mm, stations[1].height_mm)[1]}
              stroke="var(--muted)"
              strokeDasharray="2 5"
            />
            <text
              x={(P(stations[0].x_mm, stations[0].y_mm, stations[0].height_mm)[0] + P(stations[1].x_mm, stations[1].y_mm, stations[1].height_mm)[0]) / 2}
              y={(P(stations[0].x_mm, stations[0].y_mm, stations[0].height_mm)[1] + P(stations[1].x_mm, stations[1].y_mm, stations[1].height_mm)[1]) / 2 - 6}
              fontSize={10.5 * f}
              textAnchor="middle"
              fill="var(--muted)"
              className="halo"
            >
              {(apart[1] / 1000).toFixed(1)} m apart
            </text>
          </g>
        )}
      </svg>
      <div className="room-legend" data-testid="room-legend">
        {mode === "fix" ? (
          <>
            {boxes.map((b) => (
              <span key={b.index} className="row">
                <span className="lsw" style={{ background: `color-mix(in srgb, var(--st-${b.index % 2}) 45%, transparent)` }} />S{b.index} covers
              </span>
            ))}
            {shared ? <span className="row">both cover the whole floor, no handover</span> : line ? <span className="row">dashed: handover · hatched: both can</span> : null}
          </>
        ) : (
          <span className="row">accuracy: darker is worse, amber passes the {coverage?.limit_mm ?? 2} mm limit</span>
        )}
        <span className="sp" />
        <span className="row muted">
          {shownName ? `${shownName} · ` : ""}
          {stations.length ? "stations estimated from the calibration, about ±10 cm" : "no station geometry for this calibration"} · drag to orbit, double-click to reset
        </span>
        <button type="button" className="btn xs ghost" onClick={() => setView(HOME)} title="Reset the view" aria-label="Reset the view">
          <Icon name="fit" size={12} />
        </button>
      </div>
    </div>
  );
};
