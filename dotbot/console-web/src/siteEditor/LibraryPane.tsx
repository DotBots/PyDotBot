import React, { useEffect, useRef, useState } from "react";

import { Badge } from "../shared/Badge";
import { FixThumb } from "./FixThumb";
import { Icon } from "./icons";
import { coverageText, filtered, groupTitle, nameOf, residuals, when } from "./library";
import type { Library, LibraryRow, Rect } from "./types";

export type LibraryAction = "preview" | "serve" | "push" | "compare" | "archive" | "restore" | "place";

type Filter = "room" | "free" | "archived";

const Row: React.FC<{
  row: LibraryRow;
  extent: [number, number];
  shown: boolean;
  picked: boolean;
  held: number | null;
  live: boolean;
  archived?: boolean;
  /** Show the date on the row: for rows outside a dated group. */
  dated?: boolean;
  onPick: (row: LibraryRow, additive: boolean) => void;
  onAction: (action: LibraryAction, row: LibraryRow) => void;
  onRename: (row: LibraryRow, tag: string) => Promise<void>;
}> = ({ row, extent, shown, picked, held, live, archived, dated, onPick, onAction, onRename }) => {
  const boxes = Object.fromEntries(row.stations.map((s) => [s.index, s.box])) as Record<number, Rect>;
  const own: [number, number] = row.in_frame ? extent : [row.fence[2], row.fence[3]];
  const [menu, setMenu] = useState<{ top?: number; bottom?: number; left: number } | null>(null);
  const [renaming, setRenaming] = useState<string | null>(null);
  const [problem, setProblem] = useState("");
  const input = useRef<HTMLInputElement | null>(null);
  useEffect(() => {
    if (renaming !== null) input.current?.select();
  }, [renaming !== null]);
  const item = (action: LibraryAction | "rename", icon: Parameters<typeof Icon>[0]["name"], text: string, disabled = false, title?: string) => (
    <button
      type="button"
      role="menuitem"
      className="mi"
      disabled={disabled}
      title={title}
      onClick={(e) => {
        e.stopPropagation();
        setMenu(null);
        if (action === "rename") setRenaming(row.tag);
        else onAction(action, row);
      }}
    >
      <Icon name={icon} /> {text}
    </button>
  );
  const rename = async () => {
    if (renaming === null) return;
    if (renaming.trim() === row.tag) return setRenaming(null);
    try {
      await onRename(row, renaming.trim());
      setRenaming(null);
      setProblem("");
    } catch (e) {
      setProblem((e as Error).message.replace(/^\d+: /, ""));
    }
  };
  const meta = [dated ? `measured ${when(row.created_at)}` : "", `fit ${residuals(row)}`, held !== null && held > 0 ? `on ${held} robot${held === 1 ? "" : "s"}` : ""].filter(Boolean).join(" · ");
  return (
    <div
      role="button"
      tabIndex={0}
      data-testid={`library-row-${row.id8}`}
      aria-current={shown}
      className={`crow${picked ? " pick" : shown ? " cur" : ""}`}
      title={`${row.id}\n${row.path}`}
      style={{ opacity: archived ? 0.75 : 1 }}
      onClick={(e) => renaming === null && (archived ? undefined : onPick(row, e.shiftKey))}
      onKeyDown={(e) => {
        if (renaming !== null) return;
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          if (!archived) onPick(row, e.shiftKey);
        }
      }}
    >
      <FixThumb boxes={boxes} extent={own} size={54} />
      <div className="ci">
        <div className="a">
          {renaming === null ? (
            <span className="tg nm" title={row.id}>
              {nameOf(row)}
            </span>
          ) : (
            <input
              ref={input}
              aria-label={`Name of ${row.id8}`}
              value={renaming}
              placeholder={`spin of ${when(row.created_at)}`}
              onClick={(e) => e.stopPropagation()}
              onChange={(e) => setRenaming(e.target.value)}
              onBlur={rename}
              onKeyDown={(e) => {
                e.stopPropagation();
                if (e.key === "Enter") rename();
                if (e.key === "Escape") setRenaming(null);
              }}
              style={{ flex: 1, minWidth: 0, font: "12px var(--font-ui)", background: "var(--canvas)", border: "1px solid var(--accent)", borderRadius: 5, padding: "1px 5px", color: "var(--text)" }}
            />
          )}
          <span className="sp" />
          {row.served && <Badge tone="ok">in use</Badge>}
          {shown && !row.served && <Badge>looking at</Badge>}
          {archived && <Badge>archived</Badge>}
          <button
            type="button"
            className="btn xs ghost"
            aria-label={`Actions for ${nameOf(row)}`}
            aria-expanded={!!menu}
            onClick={(e) => {
              e.stopPropagation();
              if (menu) return setMenu(null);
              // Fixed to the button, so the pane's scroll never clips it
              const b = (e.currentTarget as HTMLElement).getBoundingClientRect();
              const left = Math.max(8, Math.min(b.right - 250, window.innerWidth - 258));
              setMenu(b.bottom + 300 > window.innerHeight ? { bottom: window.innerHeight - b.top + 4, left } : { top: b.bottom + 4, left });
            }}
          >
            <Icon name="more" size={13} />
          </button>
        </div>
        <div className="b">{row.in_frame ? coverageText(row.reading) : `not in this room yet · ${row.fence[2]} × ${row.fence[3]} mm`}</div>
        <div className="c">
          {meta}
          <span className="id">{row.id8}</span>
        </div>
        {problem && <div className="fld-err">{problem}</div>}
      </div>
      {menu && (
        <>
          <div style={{ position: "fixed", inset: 0, zIndex: 40 }} onClick={(e) => (e.stopPropagation(), setMenu(null))} />
          <div className="pop menu" role="menu" style={{ ...menu, width: 250, zIndex: 41 }} onClick={(e) => e.stopPropagation()}>
            {archived ? (
              item("restore", "restore", "Bring back from the archive")
            ) : (
              <>
                {row.free && !row.in_frame && item("place", "pin", "Put in this room…")}
                {item("preview", "view", "Look at it on the plan")}
                {live && item("serve", "served", row.served ? "In use now" : "Use…", row.served || !row.in_frame, row.in_frame ? undefined : "Not in this room yet")}
                {live && item("push", "ext", "Send to robots…", !row.in_frame)}
                {item("compare", "compare", "Compare with the shown file")}
                {item("rename", "tag", "Rename")}
                {item("archive", "archive", "Archive", row.served, row.served ? "The file in use stays in the list" : undefined)}
                <div className="mtx">Renaming keeps the id, the file name and every robot holding it. Archiving moves the file into archived/, never deletes it.</div>
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
};

/** The Calibrations tab: this site's folder, the file in use first, then the
 * files in this room by measurement, then the spins not placed yet. */
export const LibraryPane: React.FC<{
  library: Library | null;
  error: string;
  extent: [number, number] | null;
  shownId: string | null;
  picked?: string[];
  live: boolean;
  /** How many robots report holding each id. */
  heldCount?: (id: string) => number | null;
  onPick: (row: LibraryRow, additive: boolean) => void;
  onAction: (action: LibraryAction, row: LibraryRow) => void;
  onRename: (row: LibraryRow, tag: string) => Promise<void>;
  onRetry?: () => void;
}> = ({ library, error, extent, shownId, picked = [], live, heldCount, onPick, onAction, onRename, onRetry }) => {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("room");
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
  const archived = (library.archived ?? []).filter((r) => !query || [r.id, r.tag, r.reading].some((f) => f.toLowerCase().includes(query.trim().toLowerCase())));
  const floor: [number, number] = extent ?? [1000, 1000];
  const row = (r: LibraryRow, isArchived = false, dated = false) => (
    <Row
      key={r.path}
      row={r}
      extent={floor}
      shown={r.id === shownId}
      picked={picked.includes(r.id)}
      held={heldCount ? heldCount(r.id) : null}
      live={live}
      archived={isArchived}
      dated={dated}
      onPick={onPick}
      onAction={onAction}
      onRename={onRename}
    />
  );
  const inRoom = view.groups.reduce((n, g) => n + g.rows.length, 0);
  const filters: { key: Filter; text: string }[] = [
    { key: "room", text: `This room ${inRoom}` },
    { key: "free", text: `Not in this room yet ${view.not_placed.length}` },
    { key: "archived", text: `Archived ${library.archived?.length ?? 0}` },
  ];
  return (
    <div data-testid="library">
      <label className="search">
        <Icon name="search" size={14} />
        <input aria-label="Search calibrations" placeholder="name, id or coverage" value={query} onChange={(e) => setQuery(e.target.value)} />
        {query && (
          <button type="button" className="btn xs ghost" onClick={() => setQuery("")} aria-label="Clear the search">
            <Icon name="x" size={11} />
          </button>
        )}
      </label>
      <div className="seg" style={{ display: "flex", marginTop: 8 }} role="tablist" aria-label="Which files">
        {filters.map((f) => (
          <button key={f.key} type="button" role="tab" aria-selected={filter === f.key} className={filter === f.key ? "on" : undefined} onClick={() => setFilter(f.key)} style={{ flex: 1, justifyContent: "center", padding: "4px 6px", fontSize: 11 }}>
            {f.text}
          </button>
        ))}
      </div>
      {library.count === 0 && filter !== "archived" && (
        <div className="callout" style={{ marginTop: 12 }}>
          <div className="h">No calibration for this room yet</div>
          Spin robots in the console's Localization tab to measure the stations; the files it saves appear here.
        </div>
      )}
      {filter === "room" && (
        <>
          {live && !library.serving && inRoom > 0 && !query && (
            <div className="callout" style={{ marginTop: 12 }} data-testid="library-serve-hint">
              <div className="h">None in use</div>
              Click a file to look at it on the plan, then Use this… in the top bar.
            </div>
          )}
          {library.serving && !query && (
            <>
              <div className="grp">In use</div>
              {row(library.serving, false, true)}
            </>
          )}
          {view.groups.map((g) => (
            <React.Fragment key={g.spin}>
              <div data-testid="library-group" className="grp">
                {groupTitle(g)}
              </div>
              {g.rows.length > 1 && <div className="grpnote">One measurement: the stations are where they were. The layouts differ only in where each station is used.</div>}
              {g.rows.filter((r) => query || !r.served).map((r) => row(r))}
            </React.Fragment>
          ))}
          {view.groups.length === 0 && library.count > 0 && <div className="note" style={{ marginTop: 12 }}>{query ? `Nothing in this room matches "${query}".` : "No file in this room yet."}</div>}
        </>
      )}
      {filter === "free" && (
        <>
          <div data-testid="library-not-placed" className="grp">
            Not in this room yet · {view.not_placed.length} spin{view.not_placed.length === 1 ? "" : "s"}
          </div>
          <div className="grpnote">Each was measured before this room's origin was set: put one in the room to use it.</div>
          {view.not_placed.map((r) => row(r, false, true))}
        </>
      )}
      {filter === "archived" && (
        <>
          <div className="grp">Archived · {archived.length}</div>
          <div className="grpnote">Out of the lists, still found by their full id or path; nothing is deleted.</div>
          {archived.map((r) => row(r, true, true))}
          {archived.length === 0 && <div className="note">Nothing archived.</div>}
        </>
      )}
      <div className="note" style={{ marginTop: 14 }}>
        Click a file to look at it on the plan; the one in use stays named in the top bar. Shift-click two to compare them. Thumbnails show coverage: a station's colour
        where it is used, grey where both could be.
      </div>
    </div>
  );
};
