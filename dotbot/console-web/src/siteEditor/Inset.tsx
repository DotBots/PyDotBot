import React from "react";

import type { Boxes, Geometry } from "./coverage";

/** How the stations see the floor, in a small isometric sketch: the floor,
 * each station on a pole at its estimated height, and its rays to the corners
 * of its own coverage. Estimated from the homographies: it explains, it does
 * not measure. */
export const Inset: React.FC<{ geometry: Geometry; extent: [number, number]; boxes: Boxes; height?: number }> = ({ geometry, extent, boxes, height = 190 }) => {
  const pts = Object.entries(geometry.stations);
  if (!pts.length) return null;
  const [w, h] = extent;
  const all = [
    [0, 0, 0],
    [w, h, 0],
    ...pts.map(([, p]) => [p.x_mm, p.y_mm, p.height_mm]),
  ];
  // Isometric: x to the right and down, y to the left and down, z up
  const iso = (x: number, y: number, z: number): [number, number] => [(x - y) * 0.866, (x + y) * 0.5 - z];
  const xs = all.map(([x, y, z]) => iso(x, y, z)[0]);
  const ys = all.map(([x, y, z]) => iso(x, y, z)[1]);
  const pad = 24;
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  const spanX = Math.max(...xs) - minX || 1;
  const spanY = Math.max(...ys) - minY || 1;
  const width = 280;
  const k = Math.min((width - 2 * pad) / spanX, (height - 2 * pad) / spanY);
  const P = (x: number, y: number, z = 0) => {
    const [u, v] = iso(x, y, z);
    return [pad + (u - minX) * k, pad + (v - minY) * k] as [number, number];
  };
  const floor = [P(0, 0), P(w, 0), P(w, h), P(0, h)];
  const corners = (s: string) => {
    const r = boxes.find((b) => b.index === Number(s))?.rect;
    return r ? [P(r[0], r[1]), P(r[2], r[1]), P(r[2], r[3]), P(r[0], r[3])] : [];
  };
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="inset" role="img" aria-label="Where the stations stand, estimated" data-testid="inset" style={{ display: "block", width: "100%", height: "auto", borderRadius: 8, background: "var(--canvas)", border: "1px solid var(--hairline)" }}>
      <polygon points={floor.map((p) => p.join(",")).join(" ")} fill="color-mix(in srgb, var(--text) 6%, transparent)" stroke="var(--muted)" strokeWidth={1} />
      <text x={P(0, 0)[0]} y={P(0, 0)[1] - 6} fontSize={9} fill="var(--muted)" textAnchor="middle" fontFamily="var(--font-mono)">
        origin
      </text>
      {pts.map(([s, p]) => {
        const hue = `var(--st-${Number(s) % 2})`;
        const top = P(p.x_mm, p.y_mm, p.height_mm);
        const foot = P(p.x_mm, p.y_mm, 0);
        return (
          <g key={s}>
            {corners(s).length > 0 && <polygon points={corners(s).map((c) => c.join(",")).join(" ")} fill={hue} fillOpacity={0.14} stroke={hue} strokeOpacity={0.6} strokeWidth={0.8} />}
            {corners(s).map((c, i) => (
              <line key={i} x1={top[0]} y1={top[1]} x2={c[0]} y2={c[1]} stroke={hue} strokeOpacity={0.35} strokeWidth={1} />
            ))}
            <line x1={foot[0]} y1={foot[1]} x2={top[0]} y2={top[1]} stroke={hue} strokeDasharray="3 3" strokeWidth={1.2} />
            <ellipse cx={foot[0]} cy={foot[1]} rx={4} ry={2} fill="none" stroke={hue} />
            <circle cx={top[0]} cy={top[1]} r={4.5} fill={hue} />
            <text x={top[0] + (top[0] > width / 2 ? -8 : 8)} y={top[1] - 6} fontSize={10} fill={hue} fontFamily="var(--font-mono)" fontWeight={600} textAnchor={top[0] > width / 2 ? "end" : "start"}>
              S{s} ≈ {(p.height_mm / 1000).toFixed(1)} m
            </text>
          </g>
        );
      })}
    </svg>
  );
};
