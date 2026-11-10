import React from "react";

import { contours, fixImage, fogImage, handover, sample, type Boxes, type Coverage } from "./coverage";
import type { Point } from "./model";
import type { PlanPaint } from "./PlanCanvas";
import { candidates } from "./stationRule";
import type { CoverageMode } from "./StationsPanel";

// The Stations kind's layers on the plan: who gives the fix or the predicted
// error under the areas, the handover line and the next spins over them, the
// legend and the point readout beside them.

const images = new Map<string, ReturnType<typeof fixImage>>();
function fixImageCached(boxes: Boxes, extent: [number, number]) {
  const key = JSON.stringify([boxes, extent]);
  if (!images.has(key)) {
    if (images.size > 40) images.clear();
    images.set(key, fixImage(boxes, extent));
  }
  return images.get(key) ?? null;
}

const fogs = new Map<string, string | null>();
function fogImageCached(fog: NonNullable<Coverage["fog"]>, limit: number, light: boolean, id: string) {
  const key = `${id}:${fog.sigma.length}:${fog.sigma.slice(0, 50).join()}:${limit}:${light}:${fog.origin.join()}`;
  if (!fogs.has(key)) {
    if (fogs.size > 20) fogs.clear();
    fogs.set(key, fogImage(fog, limit, light));
  }
  return fogs.get(key) ?? null;
}

export function stationsUnderlay(mode: CoverageMode, coverage: Coverage | null, extent: [number, number], light: boolean, stale: boolean) {
  return (p: PlanPaint, boxes: Boxes) => {
    const [x0, y0] = p.px([0, 0]);
    if (mode === "fix") {
      const img = fixImageCached(boxes, extent);
      if (!img) return null;
      return (
        <image
          data-testid="fix-map"
          href={img.url}
          x={x0}
          y={y0}
          width={p.pxLen(img.w)}
          height={p.pxLen(img.h)}
          preserveAspectRatio="none"
          style={{ imageRendering: "pixelated", pointerEvents: "none" }}
        />
      );
    }
    const fog = coverage?.fog;
    if (!fog || !coverage) return null;
    const url = fogImageCached(fog, coverage.limit_mm, light, coverage.id);
    const [fx, fy] = p.px(fog.origin);
    const lines = [0.5, 1.0, 1.5, coverage.limit_mm].map((level, k) => ({
      level,
      limit: k === 3,
      segs: contours(fog, level),
    }));
    return (
      <g data-testid="error-fog" style={{ pointerEvents: "none" }} opacity={stale ? 0.45 : 1}>
        {url && <image href={url} x={fx} y={fy} width={p.pxLen(fog.cols * fog.cell_mm)} height={p.pxLen(fog.rows * fog.cell_mm)} preserveAspectRatio="none" />}
        {lines.map((l) =>
          l.segs.length ? (
            <g key={l.level} stroke={l.limit ? "var(--warn)" : "var(--muted)"} strokeWidth={(l.limit ? 1.6 : 1) * p.chrome} strokeDasharray={l.limit ? `${5 * p.chrome} ${3 * p.chrome}` : undefined} fill="none">
              {l.segs.map((s, i) => {
                const [a, b] = p.px([s[0], s[1]]);
                const [c, d] = p.px([s[2], s[3]]);
                return <line key={i} x1={a} y1={b} x2={c} y2={d} />;
              })}
              {(() => {
                const s = l.segs[Math.floor(l.segs.length / 2)];
                const [a, b] = p.px([s[0], s[1]]);
                return (
                  <text className="tl halo" x={a + 3 * p.chrome} y={b - 3 * p.chrome} fontSize={9.5 * p.label} strokeWidth={3 * p.chrome} fill={l.limit ? "var(--warn)" : "var(--muted)"}>
                    {l.limit ? `limit ${l.level} mm` : l.level.toFixed(1)}
                  </text>
                );
              })()}
            </g>
          ) : null,
        )}
      </g>
    );
  };
}

export function stationsOverlay(coverage: Coverage | null, showNext: boolean, probe: Point | null) {
  return (p: PlanPaint, boxes: Boxes) => {
    const line = boxes.length === 2 ? handover(boxes[0].rect, boxes[1].rect) : null;
    return (
      <g style={{ pointerEvents: "none" }}>
        {line &&
          (() => {
            const [a, b] = p.px(line.from);
            const [c, d] = p.px(line.to);
            const w = line.label.length * 6.2 + 14;
            return (
              <g data-testid="handover">
                <line x1={a} y1={b} x2={c} y2={d} stroke="var(--text)" strokeWidth={1.4 * p.chrome} strokeDasharray={`${5 * p.chrome} ${4 * p.chrome}`} />
                <rect x={a - (w / 2) * p.chrome} y={b + 10 * p.chrome} width={w * p.chrome} height={17 * p.chrome} rx={4 * p.chrome} fill="var(--surface)" stroke="var(--hairline)" strokeWidth={p.chrome} />
                <text x={a} y={b + 22 * p.chrome} fontSize={10.5 * p.label} textAnchor="middle" fill="var(--text)" fontFamily="var(--font-mono)" fontWeight={600}>
                  {line.label}
                </text>
              </g>
            );
          })()}
        {showNext &&
          coverage?.next.map((n, i) => {
            const [x, y] = p.px([n.x, n.y]);
            const r = p.pxLen(51.4);
            return (
              <g key={i} data-testid="next-spin">
                <circle cx={x} cy={y} r={Math.max(r, 12 * p.chrome)} fill="none" stroke="var(--text)" strokeWidth={1.3 * p.chrome} strokeDasharray={`${4 * p.chrome} ${3 * p.chrome}`} />
                <text x={x} y={y + 4 * p.chrome} fontSize={11 * p.label} textAnchor="middle" fill="var(--text)" fontFamily="var(--font-mono)" fontWeight={600}>
                  {i + 1}
                </text>
                {i === 0 && (
                  <text className="tl halo" x={x + Math.max(r, 12 * p.chrome) + 5 * p.chrome} y={y + 4 * p.chrome} fontSize={10 * p.label} strokeWidth={3 * p.chrome}>
                    spin here next
                  </text>
                )}
              </g>
            );
          })}
        {probe &&
          (() => {
            const [x, y] = p.px(probe);
            return (
              <g>
                <circle cx={x} cy={y} r={5 * p.chrome} fill="none" stroke="var(--accent)" strokeWidth={1.5 * p.chrome} />
                <circle cx={x} cy={y} r={1.5 * p.chrome} fill="var(--accent)" />
              </g>
            );
          })()}
      </g>
    );
  };
}

export const StationsLegend: React.FC<{ mode: CoverageMode; coverage: Coverage | null; boxes: Boxes; showNext: boolean; stale: boolean }> = ({ mode, coverage, boxes, showNext, stale }) => (
  <div className="float legend" data-testid="legend">
    <div className="lh">
      {mode === "fix" ? "Who gives the fix" : "Predicted error"}
      <span className="cnd">{mode === "fix" ? "when every station sees the robot" : `the station the robot keeps, one standard deviation${stale ? " · updating…" : ""}`}</span>
    </div>
    <div className="rowset">
      {mode === "fix" ? (
        <>
          {boxes.map((b) => (
            <span className="row" key={b.index}>
              <span className="lsw" style={{ background: `color-mix(in srgb, var(--st-${b.index % 2}) 45%, transparent)` }} />S{b.index}
            </span>
          ))}
          <span className="row">
            <span className="lsw" style={{ background: "repeating-linear-gradient(135deg, color-mix(in srgb, var(--st-0) 60%, transparent) 0 4px, color-mix(in srgb, var(--st-1) 60%, transparent) 4px 8px)" }} />
            boxes do not decide
          </span>
          <span className="row">
            <span className="lsw" style={{ background: "repeating-linear-gradient(135deg, color-mix(in srgb, var(--muted) 40%, transparent) 0 3px, transparent 3px 7px)" }} />
            no fix
          </span>
        </>
      ) : (
        <>
          <span className="row">
            <span className="lsw" style={{ width: 70, background: "linear-gradient(90deg, color-mix(in srgb, var(--text) 8%, transparent), color-mix(in srgb, var(--text) 60%, transparent))" }} />
            <span className="mono">0 → {coverage?.limit_mm ?? 2} mm</span>
          </span>
          <span className="row" style={{ color: "var(--warn)" }}>
            <span style={{ width: 14, borderTop: "2px dashed var(--warn)" }} />
            limit {coverage?.limit_mm ?? 2} mm{coverage?.headline ? (coverage.headline.cells_over_limit ? ", passed" : ", not reached") : ""}
          </span>
          {showNext && (
            <span className="row">
              <span style={{ width: 11, height: 11, borderRadius: "50%", border: "1.5px dashed var(--text)" }} />
              spin here next
            </span>
          )}
        </>
      )}
    </div>
  </div>
);

/** The point inspector's card: what applies at one point of the floor. */
export const Readout: React.FC<{ at: Point; px: Point; boxes: Boxes; coverage: Coverage | null; area: string | null }> = ({ at, px, boxes, coverage, area }) => {
  const rects = Object.fromEntries(boxes.map((b) => [b.index, b.rect]));
  const who = candidates(rects, at[0], at[1]);
  const inside = boxes.filter((b) => at[0] >= b.rect[0] && at[0] <= b.rect[2] && at[1] >= b.rect[1] && at[1] <= b.rect[3]).map((b) => `S${b.index}`);
  const fog = coverage?.fog;
  const kept = fog ? sample(fog.sigma, fog, at[0], at[1]) : null;
  const alone = fog ? Object.entries(fog.own).map(([s, g]) => [s, sample(g, fog, at[0], at[1])] as const) : [];
  const left = px[0] > 360;
  return (
    <div className="readout" data-testid="readout" style={{ left: left ? px[0] - 300 : px[0] + 16, top: Math.max(8, px[1] - 20) }}>
      <div className="xy">
        {Math.round(at[0])}, {Math.round(at[1])} mm
      </div>
      <div className="r">
        <span>Area</span>
        <span>{area ?? "none"}</span>
      </div>
      <div className="r">
        <span>Station boxes</span>
        <span>{inside.join(", ") || "none"}</span>
      </div>
      <div className="r">
        <span>Who gives the fix</span>
        <span>{who.length === 0 ? "nobody" : who.map((s) => `S${s}`).join(" or ")}</span>
      </div>
      <div className="r">
        <span>Predicted error</span>
        <span>{kept !== null ? `≤ ${kept.toFixed(2)} mm` : "-"}</span>
      </div>
      {alone.length > 0 && (
        <div className="r">
          <span>Each alone</span>
          <span>{alone.map(([s, v]) => `S${s} ${v !== null ? v.toFixed(2) : "-"}`).join(" · ")}</span>
        </div>
      )}
      <div className="why">
        {who.length > 1
          ? "The boxes share a centre here: the station whose solve lands nearer it wins, so the stations' sub-mm disagreement decides, not the boxes."
          : who.length === 1
            ? `S${who[0]}'s solve is kept here: it is nearest its own box's centre${inside.length > 1 ? " of the boxes holding the robot" : ""}.`
            : "No station's box holds this point: a robot here has no fix."}
      </div>
    </div>
  );
};
