import React, { useState } from "react";

import { Badge } from "../shared/Badge";
import { FixThumb } from "./FixThumb";
import { Icon } from "./icons";
import { filtered, groupTitle, residuals, when } from "./library";
import type { Library, LibraryRow, Rect } from "./types";

const Row: React.FC<{
  row: LibraryRow;
  extent: [number, number];
  shown: boolean;
  picked: boolean;
  onPick: (row: LibraryRow, additive: boolean) => void;
}> = ({ row, extent, shown, picked, onPick }) => {
  const boxes = Object.fromEntries(row.stations.map((s) => [s.index, s.box])) as Record<number, Rect>;
  const own: [number, number] = row.in_frame ? extent : [row.fence[2], row.fence[3]];
  return (
    <div
      role="button"
      tabIndex={0}
      data-testid={`library-row-${row.id8}`}
      aria-current={shown}
      className={`crow${picked ? " pick" : shown ? " cur" : ""}`}
      title={`${row.id}\n${row.path}`}
      onClick={(e) => onPick(row, e.shiftKey)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onPick(row, e.shiftKey);
        }
      }}
    >
      <FixThumb boxes={boxes} extent={own} />
      <div className="ci">
        <div className="a">
          <span className="id">{row.id8}</span>
          <span className="tg">{row.tag || "no tag"}</span>
          <span className="sp" />
          {row.served && <Badge tone="ok">serving</Badge>}
          {shown && !row.served && <Badge>previewing</Badge>}
        </div>
        <div className="b">{row.in_frame ? row.reading : `own frame · ${row.fence[2]} × ${row.fence[3]} mm`}</div>
        <div className="c">
          measured {when(row.created_at)} UTC · residual {residuals(row)}
        </div>
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
  picked?: string[];
  onPick: (row: LibraryRow, additive: boolean) => void;
  onRetry?: () => void;
}> = ({ library, error, extent, shownId, picked = [], onPick, onRetry }) => {
  const [query, setQuery] = useState("");
  if (error)
    return (
      <div className="callout err" style={{ marginTop: 12 }} role="alert">
        <div className="h">
          <Icon name="err" size={14} /> The calibrations could not be read
        </div>
        {error}
        {onRetry && (
          <div className="acts">
            <button type="button" className="btn sm" onClick={onRetry}>
              Try again
            </button>
          </div>
        )}
      </div>
    );
  if (!library) return <div className="note" style={{ marginTop: 12 }}>Reading the calibrations…</div>;
  const view = filtered(library, query);
  const floor: [number, number] = extent ?? [1000, 1000];
  const row = (r: LibraryRow) => (
    <Row key={r.path} row={r} extent={floor} shown={r.id === shownId} picked={picked.includes(r.id)} onPick={onPick} />
  );
  const nothing = view.groups.length === 0 && view.not_placed.length === 0;
  return (
    <div data-testid="library">
      <label className="search">
        <Icon name="search" size={14} />
        <input aria-label="Search calibrations" placeholder="id, tag or what the boxes do" value={query} onChange={(e) => setQuery(e.target.value)} />
        {query && (
          <button type="button" className="btn xs ghost" onClick={() => setQuery("")} aria-label="Clear the search">
            <Icon name="x" size={11} />
          </button>
        )}
      </label>
      {library.count === 0 && (
        <div className="callout" style={{ marginTop: 12 }}>
          <div className="h">No calibration for this site yet</div>
          Spin robots in the console's Calibrate tab to measure the stations; the files it saves appear here.
        </div>
      )}
      {library.serving && !query && (
        <>
          <div className="grp">Serving now</div>
          {row(library.serving)}
        </>
      )}
      {view.groups.map((g) => (
        <React.Fragment key={g.spin}>
          <div data-testid="library-group" className="grp">
            {groupTitle(g)}
          </div>
          {g.rows.length > 1 && (
            <div className="grpnote">One measurement, so the stations are where they were; the files differ only in where each station is trusted.</div>
          )}
          {g.rows.filter((r) => query || !r.served).map(row)}
        </React.Fragment>
      ))}
      {view.not_placed.length > 0 && (
        <>
          <div data-testid="library-not-placed" className="grp">
            Not placed in this room yet · {view.not_placed.length} spin{view.not_placed.length === 1 ? "" : "s"}
          </div>
          <div className="grpnote">Each in its own frame, measured before this room's zero was set; reframe one into this room to use it.</div>
          {view.not_placed.map(row)}
        </>
      )}
      {nothing && library.count > 0 && <div className="note" style={{ marginTop: 12 }}>Nothing matches "{query}".</div>}
      <div className="note" style={{ marginTop: 14 }}>
        Click a file to preview it on the plan; the served one stays named in the top bar. Thumbnails show who gives the fix: a
        station's colour where its box decides, grey where the boxes do not.
      </div>
    </div>
  );
};
