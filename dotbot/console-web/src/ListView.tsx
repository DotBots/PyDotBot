import React from "react";

import {
  appLabel,
  areaLabel,
  bootloaderLabel,
  calibrationDiffers,
  calibrationLabel,
  detailText,
  FleetContext,
  firmwareTooOld,
  headingLabel,
  positionLabel,
  reportsDetail,
  reportsLabel,
  warnings,
} from "./botFacts";
import { rowOpacity } from "./link";
import { store } from "./persisted";
import { UnifiedBot } from "./types";
import {
  Badge,
  BatteryCell,
  FilterBar,
  HeadingGlyph,
  LedDot,
  Pagination,
  ResetBadge,
  SortKey,
  stateColor,
  TooOld,
  useQueriedBots,
  useViewQuery,
} from "./viewChrome";

interface ListViewProps {
  bots: UnifiedBot[];
  selection: Set<string>;
  onSelect: (ids: string[], mode: "replace" | "toggle" | "add") => void;
  ctx: FleetContext;
}

const mono: React.CSSProperties = { fontFamily: "var(--font-mono)", fontSize: 12 };
const muted: React.CSSProperties = { ...mono, color: "var(--muted)" };
const dash = <span style={{ color: "var(--muted)" }}>—</span>;

interface Column {
  key: SortKey;
  label: string;
  /** Shown until the viewer hides it. */
  shown: boolean;
  cell: (b: UnifiedBot, ctx: FleetContext) => React.ReactNode;
}

export const COLUMNS: Column[] = [
  {
    key: "id",
    label: "ID",
    shown: true,
    cell: (b) => (
      <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
        <LedDot bot={b} />
        <ResetBadge bot={b} />
        <span style={mono}>{b.id}</span>
      </div>
    ),
  },
  {
    key: "state",
    label: "State",
    shown: true,
    cell: (b) => (
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span
          style={{ width: 9, height: 9, borderRadius: "50%", background: stateColor(b.state), display: "inline-block" }}
        />
        <span style={{ fontSize: 12 }}>{b.state ?? "No sandbox"}</span>
      </div>
    ),
  },
  {
    key: "reports",
    label: "Reports",
    shown: true,
    cell: (b, ctx) => (
      <span title={reportsDetail(b, ctx.now)} style={{ fontSize: 12 }}>
        {reportsLabel(b, ctx.now)}
      </span>
    ),
  },
  { key: "battery", label: "Battery", shown: true, cell: (b) => <BatteryCell bot={b} /> },
  {
    key: "image",
    label: "App",
    shown: true,
    cell: (b) => (
      <span title={appLabel(b) || "No device info reported for this bot"} style={{ ...muted, whiteSpace: "nowrap" }}>
        {appLabel(b) || dash}
      </span>
    ),
  },
  {
    key: "bootloader",
    label: "Bootloader",
    shown: true,
    cell: (b) => (
      <span style={{ display: "inline-flex", gap: 6, alignItems: "center", whiteSpace: "nowrap" }}>
        <span title="Sandbox firmware: the bootloader, and the net core when it differs" style={muted}>
          {bootloaderLabel(b) || dash}
        </span>
        {firmwareTooOld(b) && <TooOld />}
      </span>
    ),
  },
  {
    key: "calibration",
    label: "LH2 cal",
    shown: true,
    cell: (b, ctx) => (
      <span style={{ display: "inline-flex", gap: 6, alignItems: "center", whiteSpace: "nowrap" }}>
        <span style={muted}>{calibrationLabel(b) || dash}</span>
        {calibrationDiffers(b, ctx.calibrationId) && (
          <Badge tone="warn" title={`The controller serves ${ctx.calibrationId.slice(0, 8)}`}>
            differs
          </Badge>
        )}
      </span>
    ),
  },
  { key: "position", label: "Position", shown: true, cell: (b) => <span style={muted}>{positionLabel(b) || dash}</span> },
  {
    key: "heading",
    label: "Heading",
    shown: true,
    cell: (b) => (
      <span style={{ ...muted, display: "inline-flex", gap: 6, alignItems: "center" }}>
        <HeadingGlyph bot={b} />
        {headingLabel(b).split(" ")[0]}
      </span>
    ),
  },
  { key: "area", label: "Area", shown: true, cell: (b, ctx) => <span style={muted}>{areaLabel(b, ctx.site) || dash}</span> },
  { key: "fw", label: "Device", shown: false, cell: (b) => <span style={muted}>{b.deviceType}</span> },
];

const HIDDEN_KEY = "dotbot.console.listHiddenColumns";

function loadHidden(): Set<string> {
  try {
    const raw = window.localStorage.getItem(HIDDEN_KEY);
    const parsed = raw ? JSON.parse(raw) : null;
    if (Array.isArray(parsed)) return new Set(parsed.filter((k) => typeof k === "string"));
  } catch {
    /* storage blocked or a hand-edited entry: fall back to the defaults */
  }
  return new Set(COLUMNS.filter((c) => !c.shown).map((c) => c.key));
}

const ColumnPicker: React.FC<{ hidden: Set<string>; toggle: (key: string) => void }> = ({ hidden, toggle }) => {
  const [open, setOpen] = React.useState(false);
  return (
    <div style={{ position: "relative" }} onClick={(e) => e.stopPropagation()}>
      <button
        onClick={() => setOpen((o) => !o)}
        style={{
          background: "var(--surface)",
          border: "1px solid var(--hairline)",
          borderRadius: 8,
          padding: "8px 12px",
          color: "var(--text)",
          fontSize: 12,
          cursor: "pointer",
        }}
      >
        Columns
      </button>
      {open && (
        <div
          role="menu"
          style={{
            position: "absolute",
            right: 0,
            top: "calc(100% + 4px)",
            zIndex: 5,
            background: "var(--surface)",
            border: "1px solid var(--hairline)",
            borderRadius: 8,
            padding: 6,
            minWidth: 150,
          }}
        >
          {COLUMNS.filter((c) => c.key !== "id").map((c) => (
            <label key={c.key} style={{ display: "flex", gap: 8, padding: "4px 6px", fontSize: 12, cursor: "pointer" }}>
              <input type="checkbox" checked={!hidden.has(c.key)} onChange={() => toggle(c.key)} />
              {c.label}
            </label>
          ))}
        </div>
      )}
    </div>
  );
};

export const ListView: React.FC<ListViewProps> = ({ bots, selection, onSelect, ctx }) => {
  const { q, setQ } = useViewQuery();
  const { rows, total, pages } = useQueriedBots(bots, q, ctx);
  const [hidden, setHidden] = React.useState(loadHidden);
  const toggleColumn = (key: string) =>
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      store(HIDDEN_KEY, [...next]);
      return next;
    });
  const columns = COLUMNS.filter((c) => !hidden.has(c.key));
  // File-manager selection: click = single, shift+click = range from the
  // anchor (last plain/cmd click) in the current row order, cmd/ctrl = toggle.
  const anchorRef = React.useRef<string | null>(null);
  const rowClick = (e: React.MouseEvent, id: string) => {
    if (e.shiftKey && anchorRef.current) {
      const ids = rows.map((r) => r.id);
      const a = ids.indexOf(anchorRef.current);
      const b = ids.indexOf(id);
      if (a >= 0 && b >= 0) {
        onSelect(ids.slice(Math.min(a, b), Math.max(a, b) + 1), "add");
        return;
      }
    }
    if (e.metaKey || e.ctrlKey) {
      onSelect([id], "toggle");
      anchorRef.current = id;
      return;
    }
    // Plain click on the sole selected item deselects it.
    if (selection.has(id) && selection.size === 1) {
      onSelect([], "replace");
      anchorRef.current = null;
      return;
    }
    onSelect([id], "replace");
    anchorRef.current = id;
  };

  const sortBy = (key: SortKey) =>
    setQ((p) => ({
      ...p,
      sortKey: key,
      sortDir: p.sortKey === key ? ((p.sortDir * -1) as 1 | -1) : 1,
    }));
  const arrow = (key: SortKey) => (q.sortKey === key ? (q.sortDir === 1 ? " ↑" : " ↓") : "");

  const allVisibleSelected = rows.length > 0 && rows.every((b) => selection.has(b.id));
  const toggleAll = () => {
    if (allVisibleSelected) onSelect(rows.map((b) => b.id), "toggle"); // all off
    else onSelect(rows.filter((b) => !selection.has(b.id)).map((b) => b.id), "add");
  };

  const th: React.CSSProperties = {
    padding: "11px 12px",
    position: "sticky",
    top: 0,
    background: "var(--surface)",
    borderBottom: "1px solid var(--hairline)",
    fontSize: 10,
    letterSpacing: ".5px",
    textTransform: "uppercase",
    color: "var(--muted)",
    textAlign: "left",
    cursor: "pointer",
    userSelect: "none",
    whiteSpace: "nowrap",
  };
  const checkBox = (checked: boolean): React.CSSProperties => ({
    width: 15,
    height: 15,
    borderRadius: 4,
    border: "1px solid var(--hairline)",
    background: checked ? "var(--accent)" : "transparent",
    color: "#fff",
    fontSize: 10,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    cursor: "pointer",
  });

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        display: "flex",
        flexDirection: "column",
        gap: 12,
        padding: "14px 16px",
        paddingTop: 58, // clear the floating view switcher
        background: "var(--canvas)",
      }}
      onClick={() => onSelect([], "replace")}
    >
      <div onClick={(e) => e.stopPropagation()} style={{ display: "flex", gap: 12, alignItems: "center" }}>
        <div style={{ flex: 1 }}>
          <FilterBar q={q} setQ={setQ} total={total} />
        </div>
        <ColumnPicker hidden={hidden} toggle={toggleColumn} />
      </div>
      <div
        style={{
          flex: 1,
          overflow: "auto",
          border: "1px solid var(--hairline)",
          borderRadius: 10,
          background: "var(--surface)",
        }}
      >
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={{ ...th, width: 42, cursor: "default" }}>
                <div
                  onClick={(e) => {
                    e.stopPropagation();
                    toggleAll();
                  }}
                  style={checkBox(allVisibleSelected)}
                >
                  {allVisibleSelected ? "✓" : ""}
                </div>
              </th>
              {columns.map((c) => (
                <th
                  key={c.key}
                  style={th}
                  onClick={(e) => {
                    e.stopPropagation();
                    sortBy(c.key);
                  }}
                >
                  {c.label}
                  {arrow(c.key)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((b) => {
              const checked = selection.has(b.id);
              const warned = warnings(b, ctx).length > 0;
              return (
                <tr
                  key={b.id}
                  title={detailText(b, ctx)}
                  onClick={(e) => {
                    e.stopPropagation();
                    rowClick(e, b.id);
                  }}
                  data-link={b.link}
                  data-warned={warned || undefined}
                  style={{
                    cursor: "pointer",
                    opacity: rowOpacity(b),
                    background: checked ? "rgba(228,3,46,.07)" : "transparent",
                    borderLeft: checked ? "2px solid var(--accent)" : "2px solid transparent",
                  }}
                >
                  <td style={{ padding: "9px 12px" }}>
                    <div
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelect([b.id], "toggle");
                        anchorRef.current = b.id;
                      }}
                      style={checkBox(checked)}
                    >
                      {checked ? "✓" : ""}
                    </div>
                  </td>
                  {columns.map((c) => (
                    <td key={c.key} style={{ padding: "9px 12px", whiteSpace: "nowrap" }}>
                      {c.cell(b, ctx)}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div onClick={(e) => e.stopPropagation()}>
        <Pagination q={q} setQ={setQ} pages={pages} />
      </div>
    </div>
  );
};
