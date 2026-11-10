import React, { useState } from "react";

import { Badge } from "../shared/Badge";
import { FixThumb } from "./FixThumb";
import { filtered, groupTitle, residuals, when } from "./library";
import type { Library, LibraryRow, Rect } from "./types";

const label10 = {
  fontSize: 10,
  letterSpacing: ".5px",
  textTransform: "uppercase",
  color: "var(--muted)",
} as const;

const Row: React.FC<{
  row: LibraryRow;
  extent: [number, number];
  shown: boolean;
  onPick: (row: LibraryRow) => void;
}> = ({ row, extent, shown, onPick }) => {
  const boxes = Object.fromEntries(row.stations.map((s) => [s.index, s.box])) as Record<number, Rect>;
  const own: [number, number] = row.in_frame ? extent : [row.fence[2], row.fence[3]];
  return (
    <div
      role="button"
      tabIndex={0}
      data-testid={`library-row-${row.id8}`}
      aria-current={shown}
      onClick={() => onPick(row)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onPick(row);
        }
      }}
      style={{
        display: "flex",
        gap: 9,
        padding: "8px 8px",
        borderRadius: 7,
        cursor: "pointer",
        background: shown ? "var(--elevated)" : "transparent",
        border: `1px solid ${shown ? "var(--accent)" : "transparent"}`,
      }}
    >
      <FixThumb boxes={boxes} extent={own} />
      <div style={{ minWidth: 0, display: "grid", gap: 2 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, minWidth: 0 }}>
          <span style={{ font: "600 12px var(--font-mono)" }}>{row.id8}</span>
          <span style={{ fontSize: 11.5, color: "var(--muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {row.tag || "(no tag)"}
          </span>
          {row.served && <Badge tone="ok">serving</Badge>}
          {shown && !row.served && <Badge>previewing</Badge>}
        </div>
        <div style={{ fontSize: 11.5, lineHeight: 1.4 }}>
          {row.in_frame ? row.reading : `${row.fence[2]} × ${row.fence[3]} mm · ${residuals(row)} · own frame`}
        </div>
        <div style={{ fontSize: 10.5, color: "var(--muted)" }}>measured {when(row.created_at)} UTC</div>
      </div>
    </div>
  );
};

/** The Calibrations tab: this site's folder, the served file first, then the
 * files in this room's frame by spin, then the spins not placed yet. */
export const LibraryPane: React.FC<{
  library: Library | null;
  error: string;
  extent: [number, number] | null;
  shownId: string | null;
  onPick: (row: LibraryRow) => void;
}> = ({ library, error, extent, shownId, onPick }) => {
  const [query, setQuery] = useState("");
  if (error) return <div style={{ padding: 12, fontSize: 12, color: "var(--err)" }}>{error}</div>;
  if (!library) return <div style={{ padding: 12, fontSize: 12, color: "var(--muted)" }}>Reading the calibrations…</div>;
  const view = filtered(library, query);
  const floor: [number, number] = extent ?? [1000, 1000];
  const row = (r: LibraryRow) => (
    <Row key={r.path} row={r} extent={floor} shown={r.id === shownId} onPick={onPick} />
  );
  return (
    <div data-testid="library" style={{ padding: 10, display: "grid", gap: 4 }}>
      <input
        aria-label="Search calibrations"
        placeholder="id, tag or what the boxes do"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        style={{
          font: "12px var(--font-ui)",
          padding: "6px 9px",
          borderRadius: 7,
          border: "1px solid var(--hairline)",
          background: "var(--canvas)",
          color: "var(--text)",
          marginBottom: 6,
        }}
      />
      {library.serving && (
        <>
          <div style={label10}>Serving now</div>
          {row(library.serving)}
        </>
      )}
      {view.groups.map((g) => (
        <React.Fragment key={g.spin}>
          <div data-testid="library-group" style={{ ...label10, marginTop: 10 }}>
            {groupTitle(g)}
          </div>
          {g.rows.length > 1 && (
            <div style={{ fontSize: 11, color: "var(--muted)", lineHeight: 1.5 }}>
              One measurement: the same homographies, so the stations are where they were. The
              files differ only in where each station is trusted.
            </div>
          )}
          {g.rows.filter((r) => !r.served).map(row)}
        </React.Fragment>
      ))}
      {view.not_placed.length > 0 && (
        <>
          <div data-testid="library-not-placed" style={{ ...label10, marginTop: 10 }}>
            Not placed in this room yet · {view.not_placed.length} spin{view.not_placed.length === 1 ? "" : "s"}
          </div>
          <div style={{ fontSize: 11, color: "var(--muted)", lineHeight: 1.5 }}>
            Each in its own frame; reframe one into this room to use it.
          </div>
          {view.not_placed.map(row)}
        </>
      )}
      <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 10, lineHeight: 1.5 }}>
        Click previews a file; the served one stays in the top bar. Thumbnails show who gives
        the fix by the robots' rule: a station's colour where its box decides, grey where the
        boxes do not.
      </div>
    </div>
  );
};
