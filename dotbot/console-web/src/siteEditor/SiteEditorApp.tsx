import React, { useEffect, useMemo, useState } from "react";

import { CalibrationChip } from "../shared/CalibrationChip";
import { ChipModel, configuredChip, servedChip } from "../shared/served";
import { fetchContext, fetchLibrary, fetchSite } from "./api";
import { LibraryPane } from "./LibraryPane";
import type { EditorContext, Library, LibraryRow, Rect, SitePayload } from "./types";

const label10 = {
  fontSize: 10,
  letterSpacing: ".5px",
  textTransform: "uppercase",
  color: "var(--muted)",
} as const;

/** The top bar's chip: the served id first, a preview as its second part. */
export function editorChip(context: EditorContext | null, shown: LibraryRow | null): ChipModel {
  const base =
    context?.mode === "controller"
      ? servedChip(context.served)
      : configuredChip(context?.configured?.id8 ? { ...context.configured, spec: context.configured.spec } : null);
  if (shown && shown.id8 !== base.id8) return { ...base, side: { kind: "preview", id8: shown.id8 } };
  return base;
}

/** Where the served calibration came from, in words. */
export function servedReason(context: EditorContext): string {
  if (context.mode !== "controller") {
    const c = context.configured;
    if (!c) return "No controller opened this editor, and the config names no calibration for this site.";
    return c.error
      ? `The config names ${c.spec} (${c.source}), which does not resolve: ${c.error}`
      : `No controller serves it here: the config names it (${c.source}).`;
  }
  const s = context.served;
  if (!s) return "The controller serves no calibration: robots keep whatever they hold.";
  const from = s.source === "the command line" ? "named on the controller's command line" : `named in ${s.source}`;
  const next = context.next_start;
  const restart = !next
    ? "A restart without --lh2-calibration serves none."
    : next.spec === s.spec || s.id.startsWith(next.spec)
      ? "A restart serves the same."
      : `A restart serves ${next.spec}, from ${next.source}.`;
  return `Loaded at start, ${from} (${s.spec}). ${restart}`;
}

const PlanPreview: React.FC<{ site: SitePayload | null; shown: LibraryRow | null }> = ({ site, shown }) => {
  const extent = site?.site.extent_mm;
  if (!extent) {
    return <div style={{ margin: "auto", color: "var(--muted)", fontSize: 12 }}>This site has no measured floor.</div>;
  }
  const [w, h] = extent;
  const pad = Math.max(w, h) * 0.06;
  const boxes: [number, Rect][] = (shown?.in_frame ? shown.stations : []).map((s) => [s.index, s.box]);
  return (
    <svg
      data-testid="plan-preview"
      viewBox={`${-pad} ${-pad} ${w + 2 * pad} ${h + 2 * pad}`}
      style={{ width: "100%", height: "100%" }}
    >
      <rect x={0} y={0} width={w} height={h} fill="var(--surface)" stroke="var(--muted)" strokeWidth={Math.max(w, h) / 500} />
      {site?.site.areas.map((a) => (
        <g key={a.name}>
          <rect x={a.x} y={a.y} width={a.w} height={a.h} fill="none" stroke="var(--muted)" strokeDasharray={`${w / 80} ${w / 120}`} strokeWidth={Math.max(w, h) / 700} />
          <text x={a.x + w / 80} y={a.y + h / 30} fontSize={Math.max(w, h) / 40} fill="var(--muted)">
            {a.name}
          </text>
        </g>
      ))}
      {boxes.map(([index, [x0, y0, x1, y1]], i) => {
        const inset = (i + 1) * Math.max(w, h) / 200;
        return (
          <rect
            key={index}
            x={x0 + inset}
            y={y0 + inset}
            width={Math.max(x1 - x0 - 2 * inset, 0)}
            height={Math.max(y1 - y0 - 2 * inset, 0)}
            fill="none"
            stroke={`var(--st-${index % 2})`}
            strokeWidth={Math.max(w, h) / 400}
          />
        );
      })}
    </svg>
  );
};

/** The site editor page. */
export const SiteEditorApp: React.FC = () => {
  const theme = new URLSearchParams(window.location.search).get("theme") === "light" ? "light" : "dark";
  const [context, setContext] = useState<EditorContext | null>(null);
  const [site, setSite] = useState<SitePayload | null>(null);
  const [library, setLibrary] = useState<Library | null>(null);
  const [error, setError] = useState("");
  const [libraryError, setLibraryError] = useState("");
  const [previewId, setPreviewId] = useState<string | null>(null);

  useEffect(() => {
    fetchContext().then(setContext, (e: Error) => setError(e.message));
    fetchSite().then(setSite, (e: Error) => setError(e.message));
    fetchLibrary().then(setLibrary, (e: Error) => setLibraryError(e.message));
  }, []);

  const rows = useMemo(
    () => (library ? [...library.groups.flatMap((g) => g.rows), ...library.not_placed] : []),
    [library],
  );
  const servedId = context?.served?.id ?? context?.configured?.id ?? null;
  const shownId = previewId ?? servedId;
  const shown = rows.find((r) => r.id === shownId) ?? null;
  const chip = editorChip(context, previewId ? shown : null);

  return (
    <div
      data-theme={theme}
      style={{
        height: "100vh",
        display: "flex",
        flexDirection: "column",
        background: "var(--canvas)",
        color: "var(--text)",
        fontFamily: "var(--font-ui)",
        fontSize: 13,
      }}
    >
      <div
        style={{
          height: 44,
          flex: "none",
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "0 16px",
          background: "var(--surface)",
          borderBottom: "1px solid var(--hairline)",
          minWidth: 0,
        }}
      >
        <div style={{ fontWeight: 700, letterSpacing: ".3px", fontSize: 15 }}>DotBots</div>
        <div style={{ width: 1, height: 20, background: "var(--hairline)" }} />
        <span style={{ fontWeight: 600 }}>Site editor</span>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>{context?.site ?? site?.name ?? ""}</span>
        <CalibrationChip chip={chip} onClearSide={previewId ? () => setPreviewId(null) : undefined} />
        <div style={{ flex: 1 }} />
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)" }}>{window.location.host}</span>
      </div>
      {error && (
        <div role="alert" style={{ padding: "8px 16px", color: "var(--err)", fontSize: 12 }}>
          {error}
        </div>
      )}
      <div style={{ flex: 1, minHeight: 0, display: "flex" }}>
        <aside style={{ width: 320, flex: "none", borderRight: "1px solid var(--hairline)", background: "var(--surface)", overflowY: "auto" }}>
          <div style={{ padding: "10px 12px", borderBottom: "1px solid var(--hairline)", ...label10 }}>
            Calibrations{library ? ` · ${library.count}` : ""}
          </div>
          <LibraryPane
            library={library}
            error={libraryError}
            extent={site?.site.extent_mm ?? null}
            shownId={shownId}
            onPick={(row) => setPreviewId(row.id === servedId ? null : row.id)}
          />
        </aside>
        <main style={{ flex: 1, minWidth: 0, display: "flex", padding: 16 }}>
          <PlanPreview site={site} shown={shown} />
        </main>
        <aside style={{ width: 300, flex: "none", borderLeft: "1px solid var(--hairline)", background: "var(--surface)", padding: 12, overflowY: "auto" }}>
          <div style={label10}>Serving</div>
          {context && (
            <div data-testid="serving-card" style={{ marginTop: 6, display: "grid", gap: 6 }}>
              <div style={{ font: "600 13px var(--font-mono)" }}>
                {context.served?.id ?? context.configured?.id ?? "none"}
              </div>
              {(context.served?.tag || context.configured?.tag) && (
                <div style={{ fontSize: 12, color: "var(--muted)" }}>{context.served?.tag || context.configured?.tag}</div>
              )}
              <div style={{ fontSize: 12, lineHeight: 1.5 }}>{servedReason(context)}</div>
              {shown && (
                <div style={{ fontSize: 12, lineHeight: 1.5, marginTop: 6 }}>
                  <div style={label10}>{shown.id === servedId ? "Who gives the fix" : `Previewing ${shown.id8}`}</div>
                  {shown.reading}
                </div>
              )}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
};
